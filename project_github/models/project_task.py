import html
import logging
import re

import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

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
        string="GitHub PR Description",
        compute="_compute_github_pr_description_html",
        sanitize=False,
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
        """Convert raw PR description (Markdown) to HTML for display.

        Primary path  : uses the `markdown` library with nl2br, fenced_code,
                        and tables extensions.
        Fallback path : if `markdown` is not installed, wraps the plain text
                        in a pre-wrap <div>. HTML characters are escaped to
                        prevent XSS.
        """
        try:
            import markdown as md_lib
            for task in self:
                if task.github_pr_description:
                    task.github_pr_description_html = md_lib.markdown(
                        task.github_pr_description,
                        extensions=["nl2br", "fenced_code", "tables"],
                    )
                else:
                    task.github_pr_description_html = False
        except ImportError:
            _logger.warning(
                "project_github: 'markdown' library not installed — "
                "PR descriptions will render as plain text. "
                "Install it with: pip install markdown"
            )
            for task in self:
                desc = task.github_pr_description or ""
                # html.escape() prevents XSS when raw PR content contains HTML/JS
                safe_desc = html.escape(desc)
                task.github_pr_description_html = (
                    f'<div style="white-space:pre-wrap;word-wrap:break-word">{safe_desc}</div>'
                )

    @api.depends("github_pr_url")
    def _compute_github_can_manage_pr_labels(self):
        """Check whether the current user has push/admin access to the linked repo."""
        for task in self:
            task.github_can_manage_pr_labels = bool(
                task.github_pr_url and self._github_current_user_can_manage_repo(task)
            )

    @api.depends()
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

    def _github_headers(self, token):
        """Return standard GitHub API headers with the given Bearer token."""
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
        }

    def _github_current_user_can_manage_repo(self, task):
        """Return True if the current Odoo user has push or admin access on GitHub.

        Calls GET /repos/{full_name} and inspects the `permissions` object
        returned by the API. Returns False on any error (no token, network
        failure, 403, etc.) so callers can treat the result as a simple bool.
        """
        token = self.env.user.sudo().github_access_token
        if not token:
            return False

        repo_full_name, _ = self._parse_github_pr_url(task.github_pr_url)
        if not repo_full_name:
            return False

        try:
            resp = requests.get(
                f"https://api.github.com/repos/{repo_full_name}",
                headers=self._github_headers(token),
                timeout=10,
            )
            if resp.status_code != 200:
                return False
            permissions = resp.json().get("permissions", {})
            # 'push' covers write access; 'admin' is a superset
            return bool(permissions.get("push") or permissions.get("admin"))
        except requests.RequestException:
            return False

    # ------------------------------------------------------------------
    # GitHub label management
    # ------------------------------------------------------------------

    def _github_ensure_label(self, repo_full_name, label_name, color, description):
        """Ensure a label exists on the GitHub repo, creating it if absent.

        Flow:
          1. GET  /repos/{repo}/labels/{name}  — check existence
          2. If 404 → POST /repos/{repo}/labels — create with given color/description
          3. Any other HTTP error → raise UserError

        This prevents failure when _github_add_label_to_pr() is called for a
        label that hasn't been created on the repo yet.
        """
        token = self.env.user.sudo().github_access_token
        if not token:
            raise UserError(_("GitHub account not connected."))

        url = f"https://api.github.com/repos/{repo_full_name}/labels/{label_name}"
        headers = self._github_headers(token)
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 404:
                # Label does not exist yet — create it
                requests.post(
                    f"https://api.github.com/repos/{repo_full_name}/labels",
                    headers=headers,
                    json={"name": label_name, "color": color, "description": description},
                    timeout=10,
                ).raise_for_status()
            else:
                resp.raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_("Unable to verify or create GitHub label: %s") % exc)

    def _github_add_label_to_pr(self, repo_full_name, pr_number, label_name):
        """Add a label to a GitHub pull request."""
        token = self.env.user.sudo().github_access_token
        if not token:
            raise UserError(_("GitHub account not connected."))

        url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/labels"
        try:
            requests.post(
                url,
                headers=self._github_headers(token),
                json=[label_name],
                timeout=10,
            ).raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_("Unable to add GitHub label '%s': %s") % (label_name, exc))

    def _github_remove_label_from_pr(self, repo_full_name, pr_number, label_name):
        """Remove a label from a GitHub pull request.

        A 404 response is treated as success because the label may have been
        removed manually on GitHub already.
        """
        token = self.env.user.sudo().github_access_token
        if not token:
            raise UserError(_("GitHub account not connected."))

        url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/labels/{label_name}"
        try:
            resp = requests.delete(url, headers=self._github_headers(token), timeout=10)
            # 200/204 = removed successfully; 404 = already absent — all acceptable
            if resp.status_code not in (200, 204, 404):
                raise requests.RequestException(resp.text)
        except requests.RequestException as exc:
            raise UserError(_("Unable to remove GitHub label '%s': %s") % (label_name, exc))

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
        if not self._github_current_user_can_manage_repo(self):
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
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("GitHub PR Updated"),
                "message": _("Label 'ok-to-merge' has been applied."),
                "type": "success",
            },
        }

    def action_github_mark_fix(self):
        self._github_update_pr_labels("fix", "ok-to-merge")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("GitHub PR Updated"),
                "message": _("Label 'fix' has been applied."),
                "type": "warning",
            },
        }

    # ------------------------------------------------------------------
    # Comment sync
    # ------------------------------------------------------------------

    def message_post(self, *, body='', subject=None, message_type='notification',
                     subtype_xmlid=None, subtype_id=False, parent_id=False,
                     attachments=None, **kwargs):
        """Override to mirror Odoo chatter messages to the linked GitHub PR.

        super() is called first so the message is always saved in Odoo,
        even if the GitHub sync step later fails (which only logs a warning).
        """
        message = super().message_post(
            body=body, subject=subject, message_type=message_type,
            subtype_xmlid=subtype_xmlid, subtype_id=subtype_id,
            parent_id=parent_id, attachments=attachments, **kwargs
        )
        if self.github_sync_comments and self.github_pr_url and body:
            self._github_post_comment_to_pr(body)
        return message

    def _github_post_comment_to_pr(self, comment_body):
        """Post comment_body to the linked GitHub PR's comment thread.

        Silently returns (with a warning log) if the user has no GitHub
        token or the PR URL is invalid — the Odoo message is already saved
        so failing here should not disrupt the user's workflow.
        """
        self.ensure_one()
        token = self.env.user.sudo().github_access_token
        if not token:
            return

        repo_full_name, pr_number = self._parse_github_pr_url(self.github_pr_url)
        if not repo_full_name or not pr_number:
            return

        url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/comments"
        try:
            requests.post(
                url,
                headers=self._github_headers(token),
                json={"body": comment_body},
                timeout=10,
            ).raise_for_status()
        except requests.RequestException as exc:
            # Non-fatal: log and continue — the Odoo message is already posted
            _logger.warning("Failed to post comment to GitHub PR %s#%s: %s", repo_full_name, pr_number, exc)
