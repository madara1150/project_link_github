import logging
from datetime import datetime

import requests
from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GITHUB_API_REPO = 'https://api.github.com/repos/{full_name}'
_GITHUB_HEADERS = {
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
}


class GithubRepository(models.Model):
    _name = 'github.repository'
    _description = 'GitHub Repository'
    _order = 'updated_at desc'
    _rec_name = 'full_name'

    # --- GitHub Data ---
    github_id = fields.Integer(string='GitHub Repo ID', readonly=True, index=True)
    name = fields.Char(string='Repository Name', readonly=True)
    full_name = fields.Char(string='Full Name', readonly=True, help='e.g. owner/repo-name')
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

    def _github_headers(self, token):
        return {**_GITHUB_HEADERS, 'Authorization': f'Bearer {token}'}

    def _parse_github_datetime(self, dt_str):
        """Parse GitHub ISO datetime string to Odoo format."""
        if not dt_str:
            return False
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

    def _sync_from_api(self, user, repos_data):
        """Upsert github.repository records from a list of GitHub API repo dicts."""
        existing = self.search([('user_id', '=', user.id)])
        existing_by_github_id = {r.github_id: r for r in existing}

        for repo in repos_data:
            github_id = repo.get('id')
            if not github_id:
                continue
            vals = {
                'github_id': github_id,
                'name': repo.get('name', ''),
                'full_name': repo.get('full_name', ''),
                'description': repo.get('description') or '',
                'private': repo.get('private', False),
                'html_url': repo.get('html_url', ''),
                'default_branch': repo.get('default_branch', 'main'),
                'updated_at': self._parse_github_datetime(repo.get('updated_at')),
                'user_id': user.id,
            }
            if github_id in existing_by_github_id:
                existing_by_github_id[github_id].write(vals)
            else:
                self.create(vals)

    def action_push_description_to_github(self):
        """Push the description field to GitHub via PATCH /repos/{full_name}."""
        self.ensure_one()
        token = self.user_id.sudo().github_access_token
        if not token:
            raise UserError(_("Your GitHub account is not connected. Connect it from your profile settings."))

        url = GITHUB_API_REPO.format(full_name=self.full_name)
        try:
            resp = requests.patch(
                url,
                json={'description': self.description or ''},
                headers=self._github_headers(token),
                timeout=15,
            )
            resp.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code
            if status == 403:
                raise UserError(_(
                    "GitHub returned 403 Forbidden. "
                    "The token may lack 'repo' scope or you don't have admin access to this repository."
                ))
            if status == 404:
                raise UserError(_("Repository '%s' not found on GitHub.", self.full_name))
            raise UserError(_("GitHub API error (%s): %s", status, exc))
        except requests.RequestException as exc:
            raise UserError(_("Network error contacting GitHub: %s", exc))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _("Description updated on GitHub."),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_sync_this_repo(self):
        """Re-fetch this specific repo from the GitHub API and refresh fields."""
        self.ensure_one()
        token = self.user_id.sudo().github_access_token
        if not token:
            raise UserError(_("GitHub account not connected."))

        url = GITHUB_API_REPO.format(full_name=self.full_name)
        try:
            resp = requests.get(url, headers=self._github_headers(token), timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_("GitHub API error: %s", exc))

        data = resp.json()
        self.write({
            'name': data.get('name', self.name),
            'description': data.get('description') or '',
            'private': data.get('private', self.private),
            'html_url': data.get('html_url', self.html_url),
            'default_branch': data.get('default_branch', self.default_branch),
            'updated_at': self._parse_github_datetime(data.get('updated_at')),
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Refreshed'),
                'message': _("Repository data refreshed from GitHub."),
                'type': 'success',
                'sticky': False,
            },
        }

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
