from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase, tagged

from ..models.project_task import _render_pr_description
from ..utils import PARAM_TASK_PREFIX

GITHUB_REQUEST = "odoo.addons.project_github.models.project_task.github_request"
MARKDOWN = "odoo.addons.project_github.models.project_task.markdown"


def pull_request(body, **overrides):
    return {
        "body": body,
        "html_url": "https://github.com/acme/shop/pull/7",
        "number": 7,
        "state": "open",
        "labels": [{"name": "bug"}, {"name": "fix"}],
        **overrides,
    }


@tagged("post_install", "-at_install")
class TestProjectTaskGithub(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({
            "name": "Shop",
            "github_task_prefix": "ok",
        })
        cls.task = cls.env["project.task"].create({
            "name": "Checkout",
            "project_id": cls.project.id,
        })
        cls.repo = cls.env["github.repository"].create({
            "github_id": 1,
            "name": "shop",
            "full_name": "acme/shop",
            "project_id": cls.project.id,
        })
        cls.env.user.sudo().github_access_token = "test-token"

    def _reference(self):
        """Return how a PR body refers to the task of the linked project."""
        return "OK-" + self.task.key.split("-")[-1]

    def test_match_by_project_prefix(self):
        body = f"Fixes {self._reference()} and {self._reference().lower()}"
        tasks = self.env["project.task"]._github_sync_pull_request(pull_request(body), "acme/shop")
        self.assertEqual(tasks, self.task)
        self.assertEqual(self.task.github_pr_number, 7)
        self.assertEqual(self.task.github_pr_state, "open")
        self.assertEqual(self.task.github_pr_labels, "bug, fix")

    def test_no_partial_word_match(self):
        body = f"not{self._reference()}"
        tasks = self.env["project.task"]._github_sync_pull_request(pull_request(body), "acme/shop")
        self.assertFalse(tasks)
        self.assertFalse(self.task.github_pr_url)

    def test_fallback_on_global_prefix(self):
        self.env["ir.config_parameter"].sudo().set_param(PARAM_TASK_PREFIX, "task")
        body = f"task-{self.task.id} task-999999999"
        tasks = self.env["project.task"]._github_sync_pull_request(pull_request(body), "acme/unlinked")
        self.assertEqual(tasks, self.task)

    def test_merged_state(self):
        data = pull_request(self._reference(), state="closed", merged_at="2026-01-01T00:00:00Z")
        self.env["project.task"]._github_sync_pull_request(data, "acme/shop")
        self.assertEqual(self.task.github_pr_state, "merged")

    def test_markdown_output_is_sanitized(self):
        unsafe_html = '<strong>bold</strong><script>alert(1)</script><img src="x" onerror="alert(1)">'
        with patch(MARKDOWN) as markdown:
            markdown.markdown.return_value = unsafe_html
            rendered = str(_render_pr_description("**bold**"))
        self.assertIn("<strong>bold</strong>", rendered)
        self.assertNotIn("<script", rendered)
        self.assertNotIn("onerror", rendered)

    def test_plain_text_fallback_is_escaped(self):
        with patch(MARKDOWN, None):
            rendered = str(_render_pr_description("<script>alert(1)</script>"))
        self.assertNotIn("<script", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_manage_access_is_checked_once_per_repo(self):
        tasks = self.task | self.task.copy()
        tasks.github_pr_url = "https://github.com/acme/shop/pull/7"
        response = MagicMock(status_code=200)
        response.json.return_value = {"permissions": {"push": True}}
        with patch(GITHUB_REQUEST, return_value=response) as github_request:
            self.assertTrue(all(tasks.mapped("github_can_manage_pr_labels")))
        github_request.assert_called_once()

    def test_comment_is_mirrored_as_plain_text(self):
        self.task.write({
            "github_pr_url": "https://github.com/acme/shop/pull/7",
            "github_sync_comments": True,
        })
        with patch(GITHUB_REQUEST) as github_request:
            self.task.message_post(body="<p>Looks good</p>", message_type="comment")
        github_request.assert_called_once()
        self.assertEqual(github_request.call_args.kwargs["json"], {"body": "Looks good"})

    def test_notification_is_not_mirrored(self):
        self.task.write({
            "github_pr_url": "https://github.com/acme/shop/pull/7",
            "github_sync_comments": True,
        })
        with patch(GITHUB_REQUEST) as github_request:
            self.task.message_post(body="<p>Stage changed</p>")
        github_request.assert_not_called()
