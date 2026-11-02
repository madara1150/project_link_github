import hashlib
import hmac
import json

from odoo.tests.common import HttpCase, tagged

from ..utils import PARAM_TASK_PREFIX, PARAM_WEBHOOK_SECRET

SECRET = "test-webhook-secret"


@tagged("post_install", "-at_install")
class TestGithubWebhook(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.task = cls.env["project.task"].create({"name": "Checkout"})
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param(PARAM_WEBHOOK_SECRET, SECRET)
        params.set_param(PARAM_TASK_PREFIX, "task")

    def _deliver(self, payload, event="pull_request", secret=SECRET):
        body = json.dumps(payload).encode()
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return self.url_open(
            "/github/webhook",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": event,
                "X-Hub-Signature-256": f"sha256={digest}",
            },
        )

    def _payload(self, action="opened", **pull_request):
        return {
            "action": action,
            "repository": {"full_name": "acme/unlinked"},
            "pull_request": {
                "body": f"task-{self.task.id}",
                "html_url": "https://github.com/acme/unlinked/pull/3",
                "number": 3,
                "state": "open",
                **pull_request,
            },
        }

    def test_valid_delivery_updates_task(self):
        response = self._deliver(self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_task_ids"], [self.task.id])
        self.assertEqual(self.task.github_pr_number, 3)

    def test_label_changes_are_synced(self):
        self._deliver(self._payload(action="labeled", labels=[{"name": "ok-to-merge"}]))
        self.assertEqual(self.task.github_pr_labels, "ok-to-merge")

    def test_forged_signature_is_rejected(self):
        response = self._deliver(self._payload(), secret="wrong-secret")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(self.task.github_pr_number)

    def test_rejected_without_configured_secret(self):
        self.env["ir.config_parameter"].sudo().set_param(PARAM_WEBHOOK_SECRET, False)
        response = self._deliver(self._payload())
        self.assertEqual(response.status_code, 401)
        self.assertFalse(self.task.github_pr_number)

    def test_other_events_are_ignored(self):
        response = self._deliver({"zen": "Keep it logically awesome."}, event="ping")
        self.assertEqual(response.json(), {"status": "ignored", "event": "ping"})
