from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    github_webhook_secret = fields.Char(
        string="GitHub Webhook Secret",
        config_parameter="kmitl_project_github.webhook_secret",
        help="Secret token สำหรับ verify HMAC-SHA256 signature จาก GitHub webhook",
    )
    github_task_prefix = fields.Char(
        string="Task Reference Prefix",
        config_parameter="kmitl_project_github.task_prefix",
        default="task",
        help='Prefix ที่ใช้ค้นหา task ใน PR description เช่น "task" จะ match กับ task-211',
    )
