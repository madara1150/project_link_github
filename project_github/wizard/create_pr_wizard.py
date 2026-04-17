import logging
import re

import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CreatePRWizard(models.TransientModel):
    _name = "github.create.pr.wizard"
    _description = "Create GitHub Branch and Pull Request"

    task_id = fields.Many2one(
        "project.task",
        string="Task",
        required=True,
        readonly=True,
    )
    repository_id = fields.Many2one(
        "github.repository",
        string="Repository",
        required=True,
        help="GitHub repository to create the branch and PR in.",
    )
    available_repository_ids = fields.Many2many(
        "github.repository",
        "create_pr_wizard_avail_repo_rel",
        string="Available Repositories",
    )
    base_branch = fields.Selection(
        selection=[("main", "main"), ("16.0", "16.0")],
        string="Base Branch",
        required=True,
        default="main",
        help="Branch to create the new branch from. Only 'main' and '16.0' are allowed.",
    )
    branch_name = fields.Char(
        string="Branch Name",
        required=True,
        help="Name of the new branch to create on GitHub.",
    )
    pr_title = fields.Char(
        string="PR Title",
        required=True,
        help="Title of the Pull Request.",
    )
    pr_body = fields.Text(
        string="PR Description",
        help="Body of the Pull Request. The task reference is included automatically for webhook linking.",
    )

    # ------------------------------------------------------------------
    # Defaults / onchange
    # ------------------------------------------------------------------

    @api.onchange("task_id")
    def _onchange_task_id(self):
        """Auto-fill branch name, PR title, and PR body when task changes."""
        task = self.task_id
        if not task:
            return
        self.pr_title = task.name or ""
        self.branch_name = self._make_branch_name(task)
        self.pr_body = self._make_pr_body(task)

    @staticmethod
    def _make_branch_name(task):
        """Generate a URL-safe branch name from the task key and name.

        Format: feat/{task.key}-{slug}
        Example: feat/PROJ-42-fix-login-bug
        """
        slug = re.sub(r"[^a-z0-9]+", "-", (task.name or "").lower()).strip("-")[:50]
        if hasattr(task, "key") and task.key:
            return f"feat/{task.key}-{slug}"
        return f"feat/{slug}"

    @staticmethod
    def _make_pr_body(task):
        """Generate PR body with a task reference for webhook auto-linking.

        The webhook parser searches PR bodies for patterns like '{prefix}-{number}'.
        Including the task key here ensures the PR is linked back to the task
        automatically when the webhook fires.
        """
        key = task.key if hasattr(task, "key") and task.key else ""
        lines = ["## Related Tasks"]
        if key:
            lines.append(key)
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # GitHub API helpers
    # ------------------------------------------------------------------

    def _github_headers(self, token):
        """Return standard GitHub API v2022-11-28 auth headers."""
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
        }

    def _get_base_sha(self, token, full_name, base_branch):
        """Return the commit SHA at the tip of base_branch.

        Raises UserError if the branch is not found or the request fails.
        """
        url = f"https://api.github.com/repos/{full_name}/git/ref/heads/{base_branch}"
        try:
            resp = requests.get(url, headers=self._github_headers(token), timeout=10)
            if resp.status_code == 404:
                raise UserError(
                    _("Branch '%s' was not found in repository '%s'.")
                    % (base_branch, full_name)
                )
            resp.raise_for_status()
            return resp.json()["object"]["sha"]
        except requests.RequestException as exc:
            raise UserError(_("Failed to fetch base branch SHA: %s") % exc)

    def _create_github_branch(self, token, full_name, branch_name, sha):
        """Create a new branch on GitHub from the given SHA.

        Raises UserError on conflict (branch already exists) or other errors.
        """
        url = f"https://api.github.com/repos/{full_name}/git/refs"
        try:
            resp = requests.post(
                url,
                headers=self._github_headers(token),
                json={"ref": f"refs/heads/{branch_name}", "sha": sha},
                timeout=10,
            )
            if resp.status_code == 422:
                raise UserError(
                    _("Branch '%s' already exists in repository '%s'.")
                    % (branch_name, full_name)
                )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_("Failed to create branch '%s': %s") % (branch_name, exc))

    def _create_github_pr(self, token, full_name, title, body, head, base):
        """Create a Pull Request on GitHub and return the PR response dict.

        Raises UserError if the API call fails.
        """
        url = f"https://api.github.com/repos/{full_name}/pulls"
        try:
            resp = requests.post(
                url,
                headers=self._github_headers(token),
                json={"title": title, "body": body or "", "head": head, "base": base},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise UserError(_("Failed to create Pull Request: %s") % exc)

    # ------------------------------------------------------------------
    # Main action
    # ------------------------------------------------------------------

    def action_create_pr(self):
        """Create a GitHub branch and Pull Request, then link them to the task.

        Steps:
          1. Validate inputs (token, repo, branch name)
          2. Get SHA of the base branch tip
          3. Create the new branch from that SHA
          4. Create the PR targeting the base branch
          5. Write PR URL, number, and state back to the Odoo task
        """
        self.ensure_one()

        # Step 1 — validate
        token = self.env.user.sudo().github_access_token
        if not token:
            raise UserError(
                _("Your GitHub account is not connected. "
                  "Connect it from your profile settings.")
            )
        if not self.repository_id:
            raise UserError(_("Please select a repository."))
        if not self.branch_name or not self.branch_name.strip():
            raise UserError(_("Branch name cannot be empty."))

        full_name = self.repository_id.full_name
        branch_name = self.branch_name.strip()
        base = self.base_branch

        # Step 2 — get base branch SHA
        sha = self._get_base_sha(token, full_name, base)

        # Step 3 — create branch
        self._create_github_branch(token, full_name, branch_name, sha)

        # Step 4 — create PR
        pr_data = self._create_github_pr(
            token,
            full_name,
            title=self.pr_title or self.task_id.name,
            body=self.pr_body or "",
            head=branch_name,
            base=base,
        )

        # Step 5 — write back to task
        self.task_id.write({
            "github_pr_url": pr_data.get("html_url"),
            "github_pr_number": pr_data.get("number"),
            "github_pr_state": "open",
        })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Pull Request Created"),
                "message": _("Branch '%s' and PR #%s created successfully.")
                % (branch_name, pr_data.get("number")),
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
