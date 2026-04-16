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
        """Sync the user's GitHub repositories then open the repo-selector wizard.

        Flow:
          1. Fetch all accessible repos from GitHub API (paginated)
          2. Upsert into github.repository records for the current user
          3. Open the github.repo.selector wizard pre-filled with:
               - available_repo_ids: repos owned by this user (unlinked OR already
                 linked to this project) so the user sees the full selectable list
               - repository_ids: repos currently linked to this project (pre-checked)

        Raises UserError if the current user has not connected their GitHub account.
        """
        self.ensure_one()
        user = self.env.user
        token = user.sudo().github_access_token
        if not token:
            raise UserError(
                _("Your GitHub account is not connected. "
                  "Connect it from your profile settings.")
            )

        # Step 1 & 2 — fetch from GitHub and upsert local records
        repos_data = self._fetch_github_repos(token)
        self.env["github.repository"].sudo()._sync_from_api(user, repos_data)

        # Step 3 — build wizard with pre-selected repos
        already_linked = self.env["github.repository"].search([
            ("project_id", "=", self.id),
        ])
        # Include unlinked repos and repos already tied to this project
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
        """Fetch every repository accessible by the authenticated user (paginated).

        Note: This method contains the same pagination logic as
        GithubOAuthController._fetch_all_repos(). They are kept separate because
        one runs in a controller context (request.env) and the other in a model
        context (self.env), which makes sharing a utility non-trivial in Odoo.

        Args:
            token (str): GitHub access token.

        Returns:
            list[dict]: Raw GitHub API repository objects.
        """
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
                _logger.exception("GitHub: repo list page %s failed: %s", page, exc)
                break  # Return whatever was fetched so far
            batch = resp.json()
            if not batch:
                break  # Empty page = no more results
            repos.extend(batch)
            page += 1
        return repos
