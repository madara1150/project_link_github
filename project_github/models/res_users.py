import logging

from odoo import api, fields, models
from odoo.addons import base
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

# Make github_access_token a private field — cannot be read via RPC by non-admin users
base.models.res_users.USER_PRIVATE_FIELDS.append('github_access_token')


class ResUsers(models.Model):
    _inherit = 'res.users'

    github_access_token = fields.Char(
        string='GitHub Access Token',
        copy=False,
        prefetch=False,
        groups='base.group_system',
    )
    github_login = fields.Char(
        string='GitHub Username',
        copy=False,
    )
    github_avatar_url = fields.Char(
        string='GitHub Avatar URL',
        copy=False,
    )
    github_connected = fields.Boolean(
        string='GitHub Connected',
        compute='_compute_github_connected',
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['github_login', 'github_connected', 'github_avatar_url']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['github_login', 'github_avatar_url']

    @api.depends('github_access_token')
    def _compute_github_connected(self):
        """Return True when the user has a stored GitHub access token.

        sudo() is required because github_access_token is restricted to
        base.group_system — regular users cannot read their own token directly.
        The computed field is readable by the user themselves via SELF_READABLE_FIELDS.
        """
        for user in self:
            user.github_connected = bool(user.sudo().github_access_token)

    def action_github_disconnect(self):
        """Clear all stored GitHub credentials for this user.

        Security: a user may only disconnect their own account unless they
        are an administrator. Clears token, login, and avatar in a single write
        so the user record is never left in a partial state.
        """
        self.ensure_one()
        if self.env.uid != self.id and not self.env.user._is_admin():
            raise AccessError("You can only disconnect your own GitHub account.")
        self.sudo().write({
            'github_access_token': False,
            'github_login': False,
            'github_avatar_url': False,
        })
        _logger.info("GitHub: user %s disconnected their GitHub account.", self.login)
