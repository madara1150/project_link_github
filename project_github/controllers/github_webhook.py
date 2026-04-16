import hashlib
import hmac
import json
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# PR actions that are meaningful to sync to Odoo tasks.
# Other actions (labeled, assigned, review_requested, …) are ignored.
_HANDLED_ACTIONS = frozenset({"opened", "edited", "synchronize", "closed", "reopened"})


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
        pr_data = payload.get("pull_request", {})
        repo_full_name = payload.get("repository", {}).get("full_name", "")
        updated_ids = self._process_pull_request(pr_data, repo_full_name)

        return request.make_json_response({"status": "ok", "updated_task_ids": updated_ids})

    def _verify_signature(self, payload_bytes):
        """Verify the HMAC-SHA256 signature sent in the X-Hub-Signature-256 header.

        GitHub computes the signature using the webhook secret configured in the
        repo/org settings. We compare using hmac.compare_digest() to prevent
        timing-based attacks.

        Returns True (and logs a warning) when no secret is configured so that
        development environments work without a secret — do NOT do this in production.
        """
        secret = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("kmitl_project_github.webhook_secret", "")
        )
        if not secret:
            _logger.warning(
                "GitHub webhook secret not configured — skipping signature check. "
                "Set it in Settings → GitHub Integration for production use."
            )
            return True

        signature_header = request.httprequest.headers.get("X-Hub-Signature-256", "")
        if not signature_header.startswith("sha256="):
            return False

        expected = hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()
        received = signature_header[len("sha256="):]

        # Constant-time comparison prevents timing oracle attacks
        return hmac.compare_digest(expected, received)

    def _process_pull_request(self, pr_data, repo_full_name):
        """Parse a PR payload and update matching Odoo tasks.

        Two matching strategies are tried in order:
          1. Per-project  — repo is linked to an Odoo project with a prefix;
                            scans PR body for `{prefix}-{task_number}` patterns
                            and resolves them as `{project.key}-{number}` task keys.
          2. Global prefix (fallback) — legacy mode; scans PR body for
                            `{global_prefix}-{database_id}` and browses tasks by ID.

        Args:
            pr_data       (dict): The `pull_request` object from the GitHub payload.
            repo_full_name (str): `owner/repo` string from the payload.

        Returns:
            list[int]: Database IDs of all tasks that were updated.
        """
        description = pr_data.get("body") or ""
        pr_url = pr_data.get("html_url", "")
        pr_number = pr_data.get("number", 0)
        pr_state = pr_data.get("state", "open")

        # GitHub marks a PR as 'closed' even when merged; check merged_at to distinguish
        if pr_state == "closed" and pr_data.get("merged_at"):
            pr_state = "merged"

        labels = pr_data.get("labels", [])
        label_names = [label.get("name") for label in labels if label.get("name")]

        pr_vals = {
            "github_pr_url": pr_url,
            "github_pr_description": description,
            "github_pr_number": pr_number,
            "github_pr_state": pr_state,
            "github_pr_labels": ", ".join(label_names),
        }

        # --- Strategy 1: per-project matching ---
        linked_repos = (
            request.env["github.repository"]
            .sudo()
            .search([
                ("full_name", "=", repo_full_name),
                ("project_id", "!=", False),
            ])
        )
        if linked_repos:
            return self._match_by_project(linked_repos, description, pr_number, pr_vals)

        # --- Strategy 2: fallback global prefix ---
        return self._match_by_global_prefix(description, pr_number, pr_vals)

    def _match_by_project(self, linked_repos, description, pr_number, pr_vals):
        """Match tasks via per-project prefix and Odoo task key.

        For each repo→project pair, the method:
          - Reads the project's github_task_prefix (e.g. "PROJ")
          - Scans the PR body for `PROJ-{number}` (case-insensitive, word-boundary)
          - Resolves task keys as `{project.key}-{number}` (e.g. "PROJ-42")
          - Writes pr_vals to all matched tasks

        Args:
            linked_repos  (Recordset): github.repository records linked to a project.
            description   (str): PR body text.
            pr_number     (int): PR number (for logging).
            pr_vals       (dict): Field values to write on matched tasks.

        Returns:
            list[int]: Database IDs of updated tasks (may contain duplicates if
                       multiple repos share a project — deduplicated by caller if needed).
        """
        all_updated = []
        Task = request.env["project.task"].sudo()

        for repo in linked_repos:
            project = repo.project_id
            prefix = project.github_task_prefix
            if not prefix:
                _logger.info(
                    "GitHub webhook: project '%s' has no github_task_prefix, skipping",
                    project.display_name,
                )
                continue

            # Regex: case-insensitive, whole-word match for e.g. "PROJ-42"
            pattern = rf"(?i)\b{re.escape(prefix)}-(\d+)\b"
            matches = re.findall(pattern, description)
            if not matches:
                continue

            # Build task keys: project.key + extracted number (deduplicated)
            task_keys = [f"{project.key}-{m}" for m in set(matches)]
            tasks = Task.search([("key", "in", task_keys)])

            if not tasks:
                _logger.info(
                    "GitHub webhook: no tasks found for keys %s (PR #%s)",
                    task_keys, pr_number,
                )
                continue

            tasks.write(pr_vals)
            _logger.info(
                "GitHub webhook: updated task(s) %s (keys %s) from PR #%s",
                tasks.ids, task_keys, pr_number,
            )
            all_updated.extend(tasks.ids)

        return all_updated

    def _match_by_global_prefix(self, description, pr_number, pr_vals):
        """Legacy fallback: match tasks using a global prefix and task database ID.

        Scans the PR body for `{global_prefix}-{id}` patterns and browses
        project.task by database ID. This mode is used when the repository has
        not been linked to any Odoo project via github.repository.

        Args:
            description (str): PR body text.
            pr_number   (int): PR number (for logging).
            pr_vals     (dict): Field values to write on matched tasks.

        Returns:
            list[int]: Database IDs of updated tasks.
        """
        prefix = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("kmitl_project_github.task_prefix", "task")
        )

        # Regex: case-insensitive, whole-word match for e.g. "task-7"
        pattern = rf"(?i)\b{re.escape(prefix)}-(\d+)\b"
        matches = re.findall(pattern, description)
        if not matches:
            _logger.info("GitHub webhook: no task reference found in PR #%s", pr_number)
            return []

        task_ids = list({int(m) for m in matches})
        tasks = request.env["project.task"].sudo().browse(task_ids).exists()

        if not tasks:
            _logger.info(
                "GitHub webhook: tasks not found for IDs %s (PR #%s)",
                task_ids, pr_number,
            )
            return []

        tasks.write(pr_vals)
        _logger.info(
            "GitHub webhook: updated task(s) %s from PR #%s (fallback global prefix)",
            tasks.ids, pr_number,
        )
        return tasks.ids
