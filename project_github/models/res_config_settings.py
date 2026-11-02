from odoo import fields, models

from ..utils import (
    PARAM_CLIENT_ID,
    PARAM_CLIENT_SECRET,
    PARAM_TASK_PREFIX,
    PARAM_WEBHOOK_SECRET,
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    github_webhook_secret = fields.Char(
        string="GitHub Webhook Secret",
        config_parameter=PARAM_WEBHOOK_SECRET,
        help="Secret token สำหรับ verify HMAC-SHA256 signature จาก GitHub webhook",
    )
    github_task_prefix = fields.Char(
        string="Task Reference Prefix",
        config_parameter=PARAM_TASK_PREFIX,
        default="task",
        help='Prefix ที่ใช้ค้นหา task ใน PR description เช่น "task" จะ match กับ task-211',
    )
    github_client_id = fields.Char(
        string="GitHub OAuth App Client ID",
        config_parameter=PARAM_CLIENT_ID,
        help="Client ID จาก GitHub OAuth App (Settings → Developer settings → OAuth Apps)",
    )
    github_client_secret = fields.Char(
        string="GitHub OAuth App Client Secret",
        config_parameter=PARAM_CLIENT_SECRET,
        help="Client Secret จาก GitHub OAuth App — เก็บเป็นความลับ ห้ามเผยแพร่",
    )
