from odoo import api, fields, models


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
                    + desc
                    + "</div>"
                )
