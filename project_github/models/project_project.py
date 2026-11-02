import logging

import requests

from odoo import fields, models, _
from odoo.exceptions import UserError

from ..utils import fetch_user_repos

_logger = logging.getLogger(__name__)


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

        Raises UserError if the current user has not connected their GitHub account
        or if GitHub cannot be reached.
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
        try:
            repos_data = fetch_user_repos(token)
        except requests.RequestException as exc:
            _logger.exception("GitHub: repository sync failed: %s", exc)
            raise UserError(
                _("Cannot read your repositories from GitHub. "
                  "Reconnect your GitHub account and try again.")
            )
        self.env["github.repository"].sudo()._sync_from_api(user, repos_data)

        # Step 3 — build wizard with pre-selected repos
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
            "repository_ids": [(6, 0, self.github_repository_ids.ids)],
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("Select GitHub Repositories"),
            "res_model": "github.repo.selector",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }
