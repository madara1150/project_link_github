import hashlib
import hmac
import json
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

_HANDLED_ACTIONS = frozenset({"opened", "edited", "synchronize", "closed", "reopened"})


class GithubWebhookController(http.Controller):

    @http.route(
        "/github/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def github_webhook(self, **kwargs):
        payload_bytes = request.httprequest.get_data()

        if not self._verify_signature(payload_bytes):
            _logger.warning("GitHub webhook: invalid signature")
            return request.make_json_response(
                {"error": "Invalid signature"}, status=401
            )

        try:
            payload = json.loads(payload_bytes)
        except json.JSONDecodeError:
            return request.make_json_response({"error": "Invalid JSON"}, status=400)

        event = request.httprequest.headers.get("X-GitHub-Event", "")
        if event != "pull_request":
            return request.make_json_response({"status": "ignored", "event": event})

        action = payload.get("action", "")
        if action not in _HANDLED_ACTIONS:
            return request.make_json_response({"status": "ignored", "action": action})

        pr_data = payload.get("pull_request", {})
        updated_ids = self._process_pull_request(pr_data)

        return request.make_json_response(
            {"status": "ok", "updated_task_ids": updated_ids}
        )

    def _verify_signature(self, payload_bytes):
        """ตรวจสอบ HMAC-SHA256 signature จาก GitHub"""
        secret = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("kmitl_project_github.webhook_secret", "")
        )
        if not secret:
            _logger.warning(
                "GitHub webhook secret not configured — skipping signature check"
            )
            return True

        signature_header = request.httprequest.headers.get(
            "X-Hub-Signature-256", ""
        )
        if not signature_header.startswith("sha256="):
            return False

        expected = hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()
        received = signature_header[len("sha256="):]
        return hmac.compare_digest(expected, received)

    def _process_pull_request(self, pr_data):
        """ค้นหา task จาก PR description แล้วอัปเดต GitHub fields

        Returns:
            list[int] - database IDs ของ task ที่ถูกอัปเดต
        """
        description = pr_data.get("body") or ""
        pr_url = pr_data.get("html_url", "")
        pr_number = pr_data.get("number", 0)
        pr_state = pr_data.get("state", "open")

        if pr_state == "closed" and pr_data.get("merged_at"):
            pr_state = "merged"

        prefix = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("kmitl_project_github.task_prefix", "task")
        )

        # Match "task-211" or "TASK-211" → task database id = 211
        pattern = rf"(?i)\b{re.escape(prefix)}-(\d+)\b"
        matches = re.findall(pattern, description)
        if not matches:
            _logger.info(
                "GitHub webhook: no task reference found in PR #%s", pr_number
            )
            return []
        _logger.info(
                "=====================================> Math ========>#%s", pr_number
            )
        task_ids = list({int(m) for m in matches})
        tasks = request.env["project.task"].sudo().browse(task_ids).exists()
        _logger.info(
                "=====================================> PROJECT มีไหม ========>#%s", tasks
            )

        if not tasks:
            _logger.info(
                "GitHub webhook: tasks not found for IDs %s (PR #%s)",
                task_ids,
                pr_number,
            )
            return []
        _logger.info(
                "=====================================> github_pr_url มีไหม ========>#%s", pr_url
            )
        _logger.info(
                "=====================================> description มีไหม ========>#%s", description
            )
        _logger.info(
                "=====================================> github_pr_number มีไหม ========>#%s", pr_number
            )
        _logger.info(
                "=====================================> pr_state มีไหม ========>#%s", pr_state
            )
        tasks.write(
            {
                "github_pr_url": pr_url,
                "github_pr_description": description,
                "github_pr_number": pr_number,
                "github_pr_state": pr_state,
            }
        )
        _logger.info(
            "GitHub webhook: updated task(s) %s from PR #%s (%s)",
            tasks.ids,
            pr_number,
            pr_url,
        )
        return tasks.ids
