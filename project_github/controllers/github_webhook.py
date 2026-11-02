import hashlib
import hmac
import json
import logging

from odoo import SUPERUSER_ID, http
from odoo.http import request

from ..utils import PARAM_WEBHOOK_SECRET

_logger = logging.getLogger(__name__)

# PR actions that are meaningful to sync to Odoo tasks.
# Other actions (assigned, review_requested, …) are ignored.
_HANDLED_ACTIONS = frozenset({
    "opened",
    "edited",
    "synchronize",
    "closed",
    "reopened",
    "labeled",
    "unlabeled",
})


class GithubWebhookController(http.Controller):

    @http.route(
        "/github/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,  # GitHub sends no Odoo CSRF token
    )
    def github_webhook(self, **kwargs):
        """Entry point for all GitHub webhook deliveries.

        Flow:
          1. Verify HMAC-SHA256 signature (reject with 401 if invalid)
          2. Parse JSON payload
          3. Ignore non pull_request events and unhandled actions
          4. Delegate PR processing and return updated task IDs
        """
        payload_bytes = request.httprequest.get_data()

        # --- Signature verification ---
        if not self._verify_signature(payload_bytes):
            _logger.warning("GitHub webhook: invalid signature — request rejected")
            return request.make_json_response({"error": "Invalid signature"}, status=401)

        try:
            payload = json.loads(payload_bytes)
        except json.JSONDecodeError:
            return request.make_json_response({"error": "Invalid JSON"}, status=400)

        # --- Filter by event type ---
        event = request.httprequest.headers.get("X-GitHub-Event", "")
        if event != "pull_request":
            return request.make_json_response({"status": "ignored", "event": event})

        action = payload.get("action", "")
        if action not in _HANDLED_ACTIONS:
            return request.make_json_response({"status": "ignored", "action": action})

        # --- Process the pull request ---
        # Run as OdooBot so that chatter entries are not authored by the public user
        tasks = request.env["project.task"].with_user(SUPERUSER_ID)._github_sync_pull_request(
            payload.get("pull_request", {}),
            payload.get("repository", {}).get("full_name", ""),
        )
        return request.make_json_response({"status": "ok", "updated_task_ids": tasks.ids})

    def _verify_signature(self, payload_bytes):
        """Verify the HMAC-SHA256 signature sent in the X-Hub-Signature-256 header.

        GitHub computes the signature using the webhook secret configured in the
        repo/org settings. We compare using hmac.compare_digest() to prevent
        timing-based attacks.

        Fails closed: this endpoint is public and writes to tasks with sudo, so
        every delivery is rejected until a secret has been configured.
        """
        secret = request.env["ir.config_parameter"].sudo().get_param(PARAM_WEBHOOK_SECRET)
        if not secret:
            _logger.error(
                "GitHub webhook secret not configured — rejecting delivery. "
                "Set it in Settings → GitHub Integration."
            )
            return False

        signature_header = request.httprequest.headers.get("X-Hub-Signature-256", "")
        if not signature_header.startswith("sha256="):
            return False

        expected = hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()
        received = signature_header[len("sha256="):]

        # Constant-time comparison prevents timing oracle attacks
        return hmac.compare_digest(expected, received)
