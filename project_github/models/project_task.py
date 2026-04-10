import re

import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError


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

    @api.depends("github_pr_description")
    def _compute_github_pr_description_html(self):
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
            for task in self:
                desc = task.github_pr_description or ""
                task.github_pr_description_html = (
                    '<div style="white-space:pre-wrap;word-wrap:break-word">'
                    +desc
                    +"</div>"
                )

    @api.depends("github_pr_url")
    def _compute_github_can_manage_pr_labels(self):
        for task in self:
            task.github_can_manage_pr_labels = bool(
                task.github_pr_url and self._github_current_user_can_manage_repo(task)
            )

    def _parse_github_pr_url(self, pr_url):
        """Return (repo_full_name, pr_number) from a GitHub PR URL."""
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
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {token}",
        }

    def _github_current_user_can_manage_repo(self, task):
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
            return bool(permissions.get("push") or permissions.get("admin"))
        except requests.RequestException:
            return False

    def _github_ensure_label(self, repo_full_name, label_name, color, description):
        token = self.env.user.sudo().github_access_token
        if not token:
            raise UserError(_("GitHub account not connected."))
        url = f"https://api.github.com/repos/{repo_full_name}/labels/{label_name}"
        headers = self._github_headers(token)
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 404:
                requests.post(
                    f"https://api.github.com/repos/{repo_full_name}/labels",
                    headers=headers,
                    json={
                        "name": label_name,
                        "color": color,
                        "description": description,
                    },
                    timeout=10,
                ).raise_for_status()
            else:
                resp.raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_("Unable to verify or create GitHub label: %s") % exc)

    def _github_add_label_to_pr(self, repo_full_name, pr_number, label_name):
        token = self.env.user.sudo().github_access_token
        if not token:
            raise UserError(_("GitHub account not connected."))
        url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/labels"
        headers = self._github_headers(token)
        try:
            requests.post(
                url,
                headers=headers,
                json=[label_name],
                timeout=10,
            ).raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_("Unable to add GitHub label '%s': %s") % (label_name, exc))

    def _github_remove_label_from_pr(self, repo_full_name, pr_number, label_name):
        token = self.env.user.sudo().github_access_token
        if not token:
            raise UserError(_("GitHub account not connected."))
        url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/labels/{label_name}"
        try:
            resp = requests.delete(
                url,
                headers=self._github_headers(token),
                timeout=10,
            )
            if resp.status_code not in (200, 204, 404):
                raise requests.RequestException(resp.text)
        except requests.RequestException as exc:
            raise UserError(_("Unable to remove GitHub label '%s': %s") % (label_name, exc))

    def _github_update_pr_labels(self, label_to_add, label_to_remove):
        self.ensure_one()
        repo_full_name, pr_number = self._parse_github_pr_url(self.github_pr_url)
        if not repo_full_name or not pr_number:
            raise UserError(_("Invalid GitHub PR URL."))
        if not self._github_current_user_can_manage_repo(self):
            raise UserError(_("You do not have permission to modify labels on this GitHub repository."))

        label_def = {
            "ok-to-merge": {
                "color": "0e8a16",
                "description": "Approved for merge",
            },
            "fix": {
                "color": "b60205",
                "description": "Changes requested before merge",
            },
        }.get(label_to_add)
        self._github_ensure_label(
            repo_full_name,
            label_to_add,
            label_def["color"],
            label_def["description"],
        )
        self._github_add_label_to_pr(repo_full_name, pr_number, label_to_add)
        self._github_remove_label_from_pr(repo_full_name, pr_number, label_to_remove)

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
