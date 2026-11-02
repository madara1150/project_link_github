import logging
from datetime import datetime

import requests
from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from ..utils import github_request, notification_action

_logger = logging.getLogger(__name__)


class GithubRepository(models.Model):
    _name = 'github.repository'
    _description = 'GitHub Repository'
    _order = 'updated_at desc'
    _rec_name = 'full_name'

    # --- GitHub Data ---
    github_id = fields.Integer(string='GitHub Repo ID', readonly=True, index=True)
    name = fields.Char(string='Repository Name', readonly=True)
    full_name = fields.Char(string='Full Name', readonly=True, index=True, help='e.g. owner/repo-name')
    description = fields.Text(string='Description')
    private = fields.Boolean(string='Private', readonly=True)
    html_url = fields.Char(string='GitHub URL', readonly=True)
    default_branch = fields.Char(string='Default Branch', readonly=True)
    updated_at = fields.Datetime(string='Last Updated on GitHub', readonly=True)

    # --- Odoo Relations ---
    user_id = fields.Many2one(
        'res.users',
        string='Owner (Odoo User)',
        required=True,
        ondelete='cascade',
        index=True,
        default=lambda self: self.env.user,
    )
    project_id = fields.Many2one(
        'project.project',
        string='Linked Odoo Project',
        ondelete='set null',
    )

    _sql_constraints = [
        (
            'uniq_github_id_user',
            'UNIQUE(github_id, user_id)',
            'Each GitHub repository can only be linked once per user.',
        ),
    ]

    def _parse_github_datetime(self, dt_str):
        """Convert a GitHub ISO 8601 datetime string to Odoo's datetime format.

        GitHub returns timestamps like '2024-01-15T10:30:00Z'. Python's
        fromisoformat() doesn't accept the trailing 'Z' before 3.11, so
        we normalise it to '+00:00' first.

        Returns False for absent or empty values (safe to pass to Datetime fields).
        """
        if not dt_str:
            return False
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

    def _prepare_vals_from_api(self, repo):
        """Map a raw GitHub API repository object to field values."""
        return {
            'name': repo.get('name', ''),
            'full_name': repo.get('full_name', ''),
            'description': repo.get('description') or '',
            'private': repo.get('private', False),
            'html_url': repo.get('html_url', ''),
            'default_branch': repo.get('default_branch', 'main'),
            'updated_at': self._parse_github_datetime(repo.get('updated_at')),
        }

    def _sync_from_api(self, user, repos_data):
        """Upsert github.repository records from a GitHub API repo list.

        Fetches all existing records for the user once, then for each repo
        in repos_data either updates the existing record (matched by github_id)
        or creates a new one. This avoids N+1 queries during bulk sync.

        Args:
            user       (res.users): The Odoo user who owns the repositories.
            repos_data (list[dict]): Raw GitHub API repository objects.
        """
        existing = self.search([('user_id', '=', user.id)])
        # Index existing records by GitHub repo ID for O(1) lookup
        existing_by_github_id = {r.github_id: r for r in existing}

        for repo in repos_data:
            github_id = repo.get('id')
            if not github_id:
                continue
            vals = self._prepare_vals_from_api(repo)
            if github_id in existing_by_github_id:
                existing_by_github_id[github_id].write(vals)
            else:
                self.create({**vals, 'github_id': github_id, 'user_id': user.id})

    def _github_repo_request(self, method, **kwargs):
        """Call /repos/{full_name} with the token of the repository owner.

        github.repository records are readable by every internal user, so only
        the owner may act on them; otherwise anyone could borrow the owner's
        token by opening their record.

        Raises:
            AccessError: If the current user does not own this record.
            UserError:   With an actionable message for common failures:
                403 — token lacks 'repo' scope or user is not an admin of the repo
                404 — repository no longer exists on GitHub
        """
        self.ensure_one()
        if self.user_id != self.env.user:
            raise AccessError(_("Only the owner of this record can use it to call GitHub."))

        token = self.user_id.sudo().github_access_token
        if not token:
            raise UserError(_("Your GitHub account is not connected. Connect it from your profile settings."))

        try:
            resp = github_request(method, f'/repos/{self.full_name}', token, **kwargs)
        except requests.RequestException as exc:
            raise UserError(_("Network error contacting GitHub: %s", exc))

        if resp.status_code == 403:
            raise UserError(_(
                "GitHub returned 403 Forbidden. "
                "The token may lack 'repo' scope or you don't have admin access to this repository."
            ))
        if resp.status_code == 404:
            raise UserError(_("Repository '%s' not found on GitHub.", self.full_name))
        if not resp.ok:
            raise UserError(_("GitHub API error (%s): %s", resp.status_code, resp.reason))
        return resp

    def action_push_description_to_github(self):
        """Push the local description field to GitHub via PATCH /repos/{full_name}."""
        self._github_repo_request('PATCH', json={'description': self.description or ''})
        return notification_action(_('Success'), _("Description updated on GitHub."))

    def action_sync_this_repo(self):
        """Re-fetch this specific repo from the GitHub API and refresh fields."""
        resp = self._github_repo_request('GET')
        self.write(self._prepare_vals_from_api(resp.json()))
        return notification_action(_('Refreshed'), _("Repository data refreshed from GitHub."))

    def action_open_on_github(self):
        """Open the repository on GitHub in a new browser tab."""
        self.ensure_one()
        if not self.html_url:
            raise UserError(_("No GitHub URL stored for this repository."))
        return {
            'type': 'ir.actions.act_url',
            'url': self.html_url,
            'target': 'new',
        }
