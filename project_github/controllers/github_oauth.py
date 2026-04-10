import hmac
import json
import logging
import secrets

import requests
import werkzeug.urls

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

GITHUB_AUTHORIZE_URL = 'https://github.com/login/oauth/authorize'
GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token'
GITHUB_USER_URL = 'https://api.github.com/user'
GITHUB_REPOS_URL = 'https://api.github.com/user/repos'

_GITHUB_API_HEADERS = {
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
}

# Redirect destination after OAuth completes
_PREFS_URL = '/web'


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
        icp = request.env['ir.config_parameter'].sudo()
        client_id = icp.get_param('kmitl_project_github.client_id')
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

        # Use the actual host from the browser request (supports ngrok, proxies, etc.)
        host_url = request.httprequest.host_url.rstrip('/')
        redirect_uri = host_url + '/github/oauth/callback'
        # Store redirect_uri in session so the callback uses the exact same value
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
        """Handle the GitHub OAuth callback, exchange code for token, save to user."""

        def _redirect_error(msg):
            _logger.warning("GitHub OAuth: %s (uid=%s)", msg, request.env.uid)
            request.session['github_notification'] = {
                'type': 'danger',
                'title': 'GitHub Connection Failed',
                'message': msg,
            }
            return request.redirect(_PREFS_URL, local=False)

        # User denied authorization on GitHub
        if error:
            return _redirect_error('GitHub authorization was denied.')

        # Validate state (CSRF protection)
        try:
            state_data = json.loads(state or '{}')
        except (ValueError, TypeError):
            return _redirect_error('Invalid OAuth state parameter. Please try again.')

        stored_state = request.session.pop('github_oauth_state', None)
        received_state = state_data.get('s', '')
        if not stored_state or not hmac.compare_digest(
            stored_state.encode(),
            received_state.encode(),
        ):
            return _redirect_error(
                'OAuth state mismatch — possible session timeout or CSRF attempt. Please try again.'
            )

        if state_data.get('d') != request.session.db:
            return _redirect_error('Database mismatch in OAuth state. Please try again.')

        if not code:
            return _redirect_error('No authorization code received from GitHub.')

        # Exchange authorization code for access token
        icp = request.env['ir.config_parameter'].sudo()
        client_id = icp.get_param('kmitl_project_github.client_id')
        client_secret = icp.get_param('kmitl_project_github.client_secret')
        # Use the same redirect_uri that was sent in the authorize step
        redirect_uri = request.session.pop('github_oauth_redirect_uri', None) or (
            request.httprequest.host_url.rstrip('/') + '/github/oauth/callback'
        )

        try:
            token_resp = requests.post(
                GITHUB_TOKEN_URL,
                data={
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'code': code,
                    'redirect_uri': redirect_uri,
                },
                headers={'Accept': 'application/json'},
                timeout=10,
            )
        except requests.RequestException as exc:
            _logger.exception("GitHub OAuth: cannot reach token endpoint: %s", exc)
            return _redirect_error(f'Cannot reach GitHub: {exc}')

        if not token_resp.ok:
            _logger.warning(
                "GitHub OAuth: token endpoint returned HTTP %s — %s",
                token_resp.status_code, token_resp.text[:300],
            )
            return _redirect_error(
                f'GitHub returned HTTP {token_resp.status_code}. '
                f'Check Client ID and Secret in Settings. Detail: {token_resp.text[:300]}'
            )

        token_data = token_resp.json()
        access_token = token_data.get('access_token')
        if not access_token:
            err_desc = token_data.get('error_description') or token_data.get('error', 'unknown error')
            _logger.warning("GitHub OAuth: no access_token in response — %s", err_desc)
            return _redirect_error(f'GitHub denied the request: {err_desc}')

        # Fetch GitHub user profile
        try:
            user_resp = requests.get(
                GITHUB_USER_URL,
                headers={**_GITHUB_API_HEADERS, 'Authorization': f'Bearer {access_token}'},
                timeout=10,
            )
            user_resp.raise_for_status()
            github_user = user_resp.json()
        except requests.RequestException as exc:
            _logger.exception("GitHub OAuth: user info fetch failed: %s", exc)
            return _redirect_error('Failed to fetch GitHub user profile. Please try again.')

        github_login = github_user.get('login')
        if not github_login:
            return _redirect_error('GitHub returned an empty username. Please try again.')

        # Persist token, GitHub username, and avatar URL on the current Odoo user
        try:
            request.env.user.sudo().write({
                'github_access_token': access_token,
                'github_login': github_login,
                'github_avatar_url': github_user.get('avatar_url', ''),
            })
        except Exception as exc:
            _logger.exception(
                "GitHub OAuth: failed to save token for user %s: %s",
                request.env.user.login, exc,
            )
            return _redirect_error('Failed to save GitHub token. Please contact your administrator.')

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
    # Repository Sync API (called from front-end buttons)
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

        repos = self._fetch_all_repos(token)
        request.env['github.repository'].sudo()._sync_from_api(request.env.user, repos)
        return {'synced': len(repos)}

    def _fetch_all_repos(self, token):
        """Paginate through all repos accessible by the authenticated user."""
        repos = []
        page = 1
        headers = {**_GITHUB_API_HEADERS, 'Authorization': f'Bearer {token}'}
        while True:
            try:
                resp = requests.get(
                    GITHUB_REPOS_URL,
                    params={'per_page': 100, 'page': page, 'sort': 'updated'},
                    headers=headers,
                    timeout=15,
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                _logger.exception("GitHub: repo list page %s failed: %s", page, exc)
                break
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
        return repos
