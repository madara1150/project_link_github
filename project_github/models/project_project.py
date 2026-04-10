import logging

import requests

from odoo import fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GITHUB_REPOS_URL = "https://api.github.com/user/repos"
_GITHUB_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class ProjectProject(models.Model):
    _inherit = "project.project"

    github_task_prefix = fields.Char(
        string="GitHub Task Prefix",
        help="Prefix ที่ใช้ค้นหา task ใน PR description เช่น 'ok' จะ match กับ ok-1, ok-2",
    )
    github_repository_ids = fields.One2many(
        "github.repository",
        "project_id",
        string="Tracked GitHub Repositories",
    )

    def action_sync_and_link_repos(self):
        """Sync repos from GitHub then open the selector wizard."""
        self.ensure_one()
        user = self.env.user
        token = user.sudo().github_access_token
        if not token:
            raise UserError(
                _("Your GitHub account is not connected. "
                  "Connect it from your profile settings.")
            )

        # Fetch and sync repos
        repos_data = self._fetch_github_repos(token)
        self.env["github.repository"].sudo()._sync_from_api(user, repos_data)

        # Pre-select repos already linked to this project
        already_linked = self.env["github.repository"].search([
            ("project_id", "=", self.id),
        ])
        # Show repos belonging to current user that are either unlinked or linked to this project
        available_repos = self.env["github.repository"].search([
            ("user_id", "=", user.id),
            "|",
            ("project_id", "=", False),
            ("project_id", "=", self.id),
        ])

        wizard = self.env["github.repo.selector"].create({
            "project_id": self.id,
            "available_repo_ids": [(6, 0, available_repos.ids)],
            "repository_ids": [(6, 0, already_linked.ids)],
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("Select GitHub Repositories"),
            "res_model": "github.repo.selector",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    @staticmethod
    def _fetch_github_repos(token):
        """Paginate through all repos accessible by the authenticated user."""
        repos = []
        page = 1
        headers = {**_GITHUB_API_HEADERS, "Authorization": f"Bearer {token}"}
        while True:
            try:
                resp = requests.get(
                    GITHUB_REPOS_URL,
                    params={"per_page": 100, "page": page, "sort": "updated"},
                    headers=headers,
                    timeout=15,
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                _logger.exception(
                    "GitHub: repo list page %s failed: %s", page, exc
                )
                break
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
        return repos
