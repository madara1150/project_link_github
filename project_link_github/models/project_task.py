from odoo import fields, models


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
