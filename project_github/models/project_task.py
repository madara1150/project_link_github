import logging
import re

import requests
from markupsafe import Markup
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, html_sanitize

from ..utils import PARAM_TASK_PREFIX, github_request, notification_action

try:
    import markdown
except ImportError:
    markdown = None

_logger = logging.getLogger(__name__)

if markdown is None:
    _logger.warning(
        "project_github: 'markdown' library not installed — "
        "PR descriptions will render as plain text. "
        "Install it with: pip install markdown"
    )

# -----------------------------------------------------------------------
# Label definitions used when creating/adding labels on GitHub PRs.
# key   = label name passed to _github_update_pr_labels()
# value = dict with 'color' (hex, no #) and 'description' for the label
# -----------------------------------------------------------------------
_PR_LABEL_DEFINITIONS = {
    "ok-to-merge": {
        "color": "0e8a16",
        "description": "Approved for merge",
    },
    "fix": {
        "color": "b60205",
        "description": "Changes requested before merge",
    },
}


def _render_pr_description(description):
    """Convert a raw PR description (Markdown) to HTML that is safe to display.

    The description is written by anyone able to open a PR and the target field
    has sanitize=False, so the Markdown output must be sanitized here: Markdown
    lets raw HTML through. If `markdown` is not installed, the text is escaped
    instead.
    """
    if not description:
        return False
    if markdown is None:
        return Markup('<div style="white-space:pre-wrap;word-wrap:break-word">%s</div>') % description
    return html_sanitize(
        markdown.markdown(description, extensions=["nl2br", "fenced_code", "tables"])
    )


def _find_task_numbers(prefix, text):
    """Return the numbers referenced as `{prefix}-{number}` in text.

    The match is case-insensitive and on whole words, e.g. "PROJ-42".
    """
    pattern = rf"(?i)\b{re.escape(prefix)}-(\d+)\b"
    return {int(number) for number in re.findall(pattern, text)}


class ProjectTask(models.Model):
    _inherit = "project.task"

    github_pr_url = fields.Char(
        string="GitHub PR URL",
        tracking=True,
        help="URL ของ Pull Request บน GitHub (อัปเดตอัตโนมัติจาก webhook)",
    )
    github_pr_description = fields.Text(
        string="GitHub PR Description",
        readonly=True,
        help="Description จาก GitHub PR (อัปเดตอัตโนมัติจาก webhook)",
    )
    github_pr_description_html = fields.Html(
        string="GitHub PR Description (Rendered)",
        compute="_compute_github_pr_description_html",
        sanitize=False,  # sanitized by _render_pr_description()
    )
    github_pr_number = fields.Integer(
        string="GitHub PR Number",
        readonly=True,
    )
    github_pr_state = fields.Selection(
        selection=[
            ("open", "Open"),
            ("closed", "Closed"),
            ("merged", "Merged"),
        ],
        string="GitHub PR State",
        readonly=True,
    )
    github_pr_labels = fields.Text(
        string="GitHub PR Labels",
        readonly=True,
        help="Labels on the linked GitHub pull request.",
    )
    github_can_manage_pr_labels = fields.Boolean(
        string="Can Manage GitHub Labels",
        compute="_compute_github_can_manage_pr_labels",
        store=False,
    )
    github_sync_comments = fields.Boolean(
        string="Sync Comments to GitHub PR",
        help="If checked, comments posted in this task will also be posted to the linked GitHub PR.",
    )
    github_user_connected = fields.Boolean(
        string="GitHub User Connected",
        compute="_compute_github_user_connected",
        store=False,
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends("github_pr_description")
    def _compute_github_pr_description_html(self):
        for task in self:
            task.github_pr_description_html = _render_pr_description(task.github_pr_description)

    @api.depends("github_pr_url")
    @api.depends_context("uid")
    def _compute_github_can_manage_pr_labels(self):
        """Check whether the current user has push/admin access to the linked repo.

        Each repository is only checked once, whatever the number of tasks.
        """
        access_by_repo = {}
        for task in self:
            repo_full_name = self._parse_github_pr_url(task.github_pr_url)[0]
            if repo_full_name and repo_full_name not in access_by_repo:
                access_by_repo[repo_full_name] = self._github_can_manage_repo(repo_full_name)
            task.github_can_manage_pr_labels = access_by_repo.get(repo_full_name, False)

    @api.depends_context("uid")
    def _compute_github_user_connected(self):
        for task in self:
            task.github_user_connected = self.env.user.github_connected

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------

    def _parse_github_pr_url(self, pr_url):
        """Parse a GitHub PR URL and return (repo_full_name, pr_number).

        Returns (False, False) if the URL is absent or does not match the
        expected pattern: https://github.com/{owner}/{repo}/pull/{number}
        """
        if not pr_url:
            return False, False
        match = re.search(
            r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)(?:/|$)",
            pr_url,
        )
        if not match:
            return False, False
        return (
            f"{match.group('owner')}/{match.group('repo')}",
            int(match.group('number')),
        )

    def _github_token(self):
        """Return the current user's GitHub token, which only sudo() can read."""
        return self.env.user.sudo().github_access_token

    def _github_can_manage_repo(self, repo_full_name):
        """Return True if the current Odoo user has push or admin access on GitHub.

        Calls GET /repos/{full_name} and inspects the `permissions` object
        returned by the API. Returns False on any error (no token, network
        failure, 403, etc.) so callers can treat the result as a simple bool.
        """
        token = self._github_token()
        if not token:
            return False

        try:
            resp = github_request("GET", f"/repos/{repo_full_name}", token, timeout=10)
        except requests.RequestException:
            return False
        if resp.status_code != 200:
            return False
        permissions = resp.json().get("permissions", {})
        # 'push' covers write access; 'admin' is a superset
        return bool(permissions.get("push") or permissions.get("admin"))

    # ------------------------------------------------------------------
    # Pull request sync (called by the webhook controller)
    # ------------------------------------------------------------------

    @api.model
    def _github_prepare_pr_vals(self, pr_data):
        """Map the `pull_request` object of a GitHub payload to field values."""
        pr_state = pr_data.get("state", "open")
        # GitHub marks a PR as 'closed' even when merged; check merged_at to distinguish
        if pr_state == "closed" and pr_data.get("merged_at"):
            pr_state = "merged"

        label_names = [label["name"] for label in pr_data.get("labels", []) if label.get("name")]
        return {
            "github_pr_url": pr_data.get("html_url", ""),
            "github_pr_description": pr_data.get("body") or "",
            "github_pr_number": pr_data.get("number", 0),
            "github_pr_state": pr_state,
            "github_pr_labels": ", ".join(label_names),
        }

    @api.model
    def _github_sync_pull_request(self, pr_data, repo_full_name):
        """Parse a PR payload and update matching Odoo tasks.

        Two matching strategies are tried in order:
          1. Per-project  — repo is linked to an Odoo project with a prefix;
                            scans PR body for `{prefix}-{task_number}` patterns
                            and resolves them as `{project.key}-{number}` task keys.
          2. Global prefix (fallback) — legacy mode; scans PR body for
                            `{global_prefix}-{database_id}` and browses tasks by ID.

        Args:
            pr_data        (dict): The `pull_request` object from the GitHub payload.
            repo_full_name (str): `owner/repo` string from the payload.

        Returns:
            project.task: The tasks that were updated.
        """
        description = pr_data.get("body") or ""
        linked_repos = self.env["github.repository"].search([
            ("full_name", "=", repo_full_name),
            ("project_id", "!=", False),
        ])
        if linked_repos:
            tasks = self._github_match_by_project(linked_repos, description)
        else:
            tasks = self._github_match_by_global_prefix(description)

        pr_number = pr_data.get("number", 0)
        if not tasks:
            _logger.info("GitHub webhook: no task found for PR #%s", pr_number)
            return tasks

        tasks.write(self._github_prepare_pr_vals(pr_data))
        _logger.info("GitHub webhook: updated task(s) %s from PR #%s", tasks.ids, pr_number)
        return tasks

    @api.model
    def _github_match_by_project(self, linked_repos, description):
        """Match tasks via per-project prefix and Odoo task key.

        For each repo→project pair, the method:
          - Reads the project's github_task_prefix (e.g. "PROJ")
          - Scans the PR body for `PROJ-{number}`
          - Resolves task keys as `{project.key}-{number}` (e.g. "PROJ-42")

        Args:
            linked_repos (Recordset): github.repository records linked to a project.
            description  (str): PR body text.

        Returns:
            project.task: The matching tasks.
        """
        task_keys = set()
        for project in linked_repos.project_id:
            prefix = project.github_task_prefix
            if not prefix or not project.key:
                _logger.info(
                    "GitHub webhook: project '%s' has no prefix or key, skipping",
                    project.display_name,
                )
                continue
            numbers = _find_task_numbers(prefix, description)
            task_keys.update(f"{project.key}-{number}" for number in numbers)

        if not task_keys:
            return self.browse()
        return self.search([("key", "in", list(task_keys))])

    @api.model
    def _github_match_by_global_prefix(self, description):
        """Legacy fallback: match tasks using a global prefix and task database ID.

        Scans the PR body for `{global_prefix}-{id}` patterns and browses
        project.task by database ID. This mode is used when the repository has
        not been linked to any Odoo project via github.repository.

        Args:
            description (str): PR body text.

        Returns:
            project.task: The matching tasks.
        """
        prefix = self.env["ir.config_parameter"].sudo().get_param(PARAM_TASK_PREFIX, "task")
        return self.browse(_find_task_numbers(prefix, description)).exists()

    # ------------------------------------------------------------------
    # GitHub label management
    # ------------------------------------------------------------------

    def _github_label_request(self, method, path, allowed_statuses=(), **kwargs):
        """Call a label endpoint and return the response.

        Raises:
            UserError: If the user has no token, GitHub cannot be reached, or
                       GitHub answers with an error not in allowed_statuses.
        """
        token = self._github_token()
        if not token:
            raise UserError(_("GitHub account not connected."))
        try:
            resp = github_request(method, path, token, timeout=10, **kwargs)
        except requests.RequestException as exc:
            raise UserError(_("Unable to update GitHub labels: %s", exc))
        if not resp.ok and resp.status_code not in allowed_statuses:
            raise UserError(_("Unable to update GitHub labels: %s", resp.reason))
        return resp

    def _github_ensure_label(self, repo_full_name, label_name, color, description):
        """Ensure a label exists on the GitHub repo, creating it if absent.

        Flow:
          1. GET  /repos/{repo}/labels/{name}  — check existence
          2. If 404 → POST /repos/{repo}/labels — create with given color/description
          3. Any other HTTP error → raise UserError

        This prevents failure when _github_add_label_to_pr() is called for a
        label that hasn't been created on the repo yet.
        """
        labels_path = f"/repos/{repo_full_name}/labels"
        resp = self._github_label_request("GET", f"{labels_path}/{label_name}", allowed_statuses=(404,))
        if resp.status_code == 404:
            # Label does not exist yet — create it
            self._github_label_request(
                "POST",
                labels_path,
                json={"name": label_name, "color": color, "description": description},
            )

    def _github_add_label_to_pr(self, repo_full_name, pr_number, label_name):
        """Add a label to a GitHub pull request."""
        self._github_label_request(
            "POST",
            f"/repos/{repo_full_name}/issues/{pr_number}/labels",
            json=[label_name],
        )

    def _github_remove_label_from_pr(self, repo_full_name, pr_number, label_name):
        """Remove a label from a GitHub pull request.

        A 404 response is treated as success because the label may have been
        removed manually on GitHub already.
        """
        self._github_label_request(
            "DELETE",
            f"/repos/{repo_full_name}/issues/{pr_number}/labels/{label_name}",
            allowed_statuses=(404,),
        )

    def _github_update_pr_labels(self, label_to_add, label_to_remove):
        """Apply a label swap on the linked GitHub PR.

        Flow (each step raises UserError on failure):
          1. Validate PR URL and user permissions
          2. Look up label definition from _PR_LABEL_DEFINITIONS
          3. Ensure the label exists on the repo (create if missing)
          4. Add label_to_add to the PR
          5. Remove label_to_remove from the PR (404 = already absent, OK)

        Args:
            label_to_add    (str): Key in _PR_LABEL_DEFINITIONS to apply.
            label_to_remove (str): Label name to remove (may not exist on PR).
        """
        self.ensure_one()

        # Step 1 — validate PR URL and permissions
        repo_full_name, pr_number = self._parse_github_pr_url(self.github_pr_url)
        if not repo_full_name or not pr_number:
            raise UserError(_("Invalid GitHub PR URL."))
        if not self._github_can_manage_repo(repo_full_name):
            raise UserError(_("You do not have permission to modify labels on this GitHub repository."))

        # Step 2 — look up label definition (color + description for creation)
        label_def = _PR_LABEL_DEFINITIONS.get(label_to_add)
        if not label_def:
            raise UserError(_("Unknown PR label '%s'. Add it to _PR_LABEL_DEFINITIONS.") % label_to_add)

        # Step 3 — ensure the label exists on the repo before adding it to the PR
        self._github_ensure_label(
            repo_full_name,
            label_to_add,
            label_def["color"],
            label_def["description"],
        )

        # Step 4 — add the new label
        self._github_add_label_to_pr(repo_full_name, pr_number, label_to_add)

        # Step 5 — remove the old label (silently ignores 404)
        self._github_remove_label_from_pr(repo_full_name, pr_number, label_to_remove)

    # ------------------------------------------------------------------
    # Public actions (called from buttons in the view)
    # ------------------------------------------------------------------

    def action_github_mark_ok_to_merge(self):
        self._github_update_pr_labels("ok-to-merge", "fix")
        return notification_action(
            _("GitHub PR Updated"),
            _("Label 'ok-to-merge' has been applied."),
        )

    def action_github_mark_fix(self):
        self._github_update_pr_labels("fix", "ok-to-merge")
        return notification_action(
            _("GitHub PR Updated"),
            _("Label 'fix' has been applied."),
            "warning",
        )

    # ------------------------------------------------------------------
    # Comment sync
    # ------------------------------------------------------------------

    def message_post(self, **kwargs):
        """Override to mirror chatter comments to the linked GitHub PR.

        super() is called first so the message is always saved in Odoo,
        even if the GitHub sync step later fails (which only logs a warning).
        Only comments written by users are mirrored, not system notifications.
        """
        message = super().message_post(**kwargs)
        body = kwargs.get("body")
        if (
            kwargs.get("message_type") == "comment"
            and body
            and self.github_sync_comments
            and self.github_pr_url
        ):
            # Chatter bodies are HTML; GitHub expects Markdown
            self._github_post_comment_to_pr(html2plaintext(body))
        return message

    def _github_post_comment_to_pr(self, comment_body):
        """Post comment_body to the linked GitHub PR's comment thread.

        Silently returns (with a warning log) if the user has no GitHub
        token or the PR URL is invalid — the Odoo message is already saved
        so failing here should not disrupt the user's workflow.
        """
        self.ensure_one()
        token = self._github_token()
        if not token:
            return

        repo_full_name, pr_number = self._parse_github_pr_url(self.github_pr_url)
        if not repo_full_name or not pr_number:
            return

        try:
            github_request(
                "POST",
                f"/repos/{repo_full_name}/issues/{pr_number}/comments",
                token,
                timeout=10,
                json={"body": comment_body},
            ).raise_for_status()
        except requests.RequestException as exc:
            # Non-fatal: log and continue — the Odoo message is already posted
            _logger.warning("Failed to post comment to GitHub PR %s#%s: %s", repo_full_name, pr_number, exc)
