import hmac
import json
import logging
import secrets

import requests
import werkzeug.urls

from odoo import http
from odoo.http import request

from ..utils import (
    PARAM_CLIENT_ID,
    PARAM_CLIENT_SECRET,
    fetch_user_repos,
    github_request,
)

_logger = logging.getLogger(__name__)

GITHUB_AUTHORIZE_URL = 'https://github.com/login/oauth/authorize'
GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token'

# Redirect destination after OAuth completes
_PREFS_URL = '/web'


class GithubOAuthError(Exception):
    """OAuth failure carrying a message that is safe to show to the user."""


class GithubOAuthController(http.Controller):

    @http.route(
        '/github/oauth/authorize',
        type='http',
        auth='user',
        methods=['GET'],
        website=False,
    )
    def github_authorize(self, **kwargs):
        """Generate the GitHub authorization URL and redirect the user there."""
        client_id = request.env['ir.config_parameter'].sudo().get_param(PARAM_CLIENT_ID)
        if not client_id:
            return request.make_response(
                'GitHub OAuth is not configured. '
                'Please ask your administrator to enter the Client ID in Settings → GitHub Integration.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=503,
            )

        # Generate a CSRF state token and store it in the server-side session
        state_token = secrets.token_urlsafe(32)
        request.session['github_oauth_state'] = state_token
        request.session.modified = True  # ensure session is persisted before redirect
        state = json.dumps({'s': state_token, 'd': request.session.db})

        # Store redirect_uri in session so the callback uses the exact same value
        redirect_uri = self._callback_url()
        request.session['github_oauth_redirect_uri'] = redirect_uri

        params = werkzeug.urls.url_encode({
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'scope': 'repo read:user',
            'state': state,
        })
        return request.redirect(GITHUB_AUTHORIZE_URL + '?' + params, local=False)

    @http.route(
        '/github/oauth/callback',
        type='http',
        auth='user',
        methods=['GET'],
        csrf=False,   # GitHub GET redirect — Odoo CSRF token cannot be present
        website=False,
    )
    def github_callback(self, code=None, state=None, error=None, **kwargs):
        """Handle the GitHub OAuth callback and persist the access token.

        GitHub redirects the user here after they approve (or deny) authorization.
        Steps performed on success:
          1. Validate the `state` parameter against the session (CSRF protection)
          2. Exchange the one-time `code` for a long-lived access token
          3. Fetch the GitHub user profile (login + avatar)
          4. Save token, login, and avatar on the current Odoo user record
          5. Store a success/error notification in the session for the JS layer

        On any failure the user is redirected to _PREFS_URL with a danger
        notification queued in the session.
        """
        try:
            self._validate_callback(code, state, error)
            access_token = self._exchange_code_for_token(code)
            github_user = self._fetch_github_user(access_token)
        except GithubOAuthError as exc:
            _logger.warning("GitHub OAuth: %s (uid=%s)", exc, request.env.uid)
            request.session['github_notification'] = {
                'type': 'danger',
                'title': 'GitHub Connection Failed',
                'message': str(exc),
            }
            return request.redirect(_PREFS_URL, local=False)

        github_login = github_user['login']
        request.env.user.sudo().write({
            'github_access_token': access_token,
            'github_login': github_login,
            'github_avatar_url': github_user.get('avatar_url', ''),
        })
        _logger.info(
            "GitHub OAuth: Odoo user '%s' connected GitHub account '%s'.",
            request.env.user.login,
            github_login,
        )

        request.session['github_notification'] = {
            'type': 'success',
            'title': 'GitHub Connected',
            'message': f'Successfully connected as {github_login}.',
        }
        return request.redirect(_PREFS_URL, local=False)

    def _callback_url(self):
        """Return the callback URL for the host seen by the browser (supports ngrok, proxies, etc.)."""
        return request.httprequest.host_url.rstrip('/') + '/github/oauth/callback'

    def _validate_callback(self, code, state, error):
        """Check the GitHub redirect parameters, raising GithubOAuthError if invalid."""
        # User denied authorization on GitHub
        if error:
            raise GithubOAuthError('GitHub authorization was denied.')

        # Validate state (CSRF protection)
        try:
            state_data = json.loads(state or '{}')
        except (ValueError, TypeError):
            raise GithubOAuthError('Invalid OAuth state parameter. Please try again.')

        stored_state = request.session.pop('github_oauth_state', None)
        received_state = state_data.get('s', '')
        if not stored_state or not hmac.compare_digest(
            stored_state.encode(),
            received_state.encode(),
        ):
            raise GithubOAuthError(
                'OAuth state mismatch — possible session timeout or CSRF attempt. Please try again.'
            )

        if state_data.get('d') != request.session.db:
            raise GithubOAuthError('Database mismatch in OAuth state. Please try again.')

        if not code:
            raise GithubOAuthError('No authorization code received from GitHub.')

    def _exchange_code_for_token(self, code):
        """Exchange the one-time authorization code for an access token."""
        icp = request.env['ir.config_parameter'].sudo()
        # Use the same redirect_uri that was sent in the authorize step
        redirect_uri = request.session.pop('github_oauth_redirect_uri', None) or self._callback_url()

        try:
            token_resp = requests.post(
                GITHUB_TOKEN_URL,
                data={
                    'client_id': icp.get_param(PARAM_CLIENT_ID),
                    'client_secret': icp.get_param(PARAM_CLIENT_SECRET),
                    'code': code,
                    'redirect_uri': redirect_uri,
                },
                headers={'Accept': 'application/json'},
                timeout=10,
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
        except (requests.RequestException, ValueError) as exc:
            _logger.exception("GitHub OAuth: token exchange failed: %s", exc)
            raise GithubOAuthError(
                'Cannot get an access token from GitHub. Check Client ID and Secret in Settings.'
            )

        access_token = token_data.get('access_token')
        if not access_token:
            err_desc = token_data.get('error_description') or token_data.get('error', 'unknown error')
            raise GithubOAuthError(f'GitHub denied the request: {err_desc}')
        return access_token

    def _fetch_github_user(self, access_token):
        """Return the GitHub profile of the token owner."""
        try:
            user_resp = github_request('GET', '/user', access_token, timeout=10)
            user_resp.raise_for_status()
            github_user = user_resp.json()
        except (requests.RequestException, ValueError) as exc:
            _logger.exception("GitHub OAuth: user info fetch failed: %s", exc)
            raise GithubOAuthError('Failed to fetch GitHub user profile. Please try again.')

        if not github_user.get('login'):
            raise GithubOAuthError('GitHub returned an empty username. Please try again.')
        return github_user

    # -------------------------------------------------------------------------
    # Notification relay (read pending OAuth result from session)
    # -------------------------------------------------------------------------

    @http.route(
        '/github/notification',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def get_notification(self, **kwargs):
        """Pop and return any pending GitHub OAuth notification stored in the session."""
        return request.session.pop('github_notification', None)

    # -------------------------------------------------------------------------
    # Repository Sync API
    # -------------------------------------------------------------------------

    @http.route(
        '/github/repos/sync',
        type='json',
        auth='user',
        methods=['POST'],
    )
    def sync_repos(self, **kwargs):
        """Fetch all repos from GitHub and upsert into github.repository records."""
        token = request.env.user.sudo().github_access_token
        if not token:
            return {'error': 'not_connected'}

        try:
            repos = fetch_user_repos(token)
        except requests.RequestException as exc:
            _logger.exception("GitHub: repository sync failed: %s", exc)
            return {'error': 'github_unavailable'}

        request.env['github.repository'].sudo()._sync_from_api(request.env.user, repos)
        return {'synced': len(repos)}
