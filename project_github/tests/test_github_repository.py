from unittest.mock import MagicMock, patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

GITHUB_REQUEST = "odoo.addons.project_github.models.github_repository.github_request"


@tagged("post_install", "-at_install")
class TestGithubRepository(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = new_test_user(cls.env, login="repo_owner", groups="base.group_user")
        cls.other = new_test_user(cls.env, login="repo_other", groups="base.group_user")
        cls.owner.sudo().github_access_token = "owner-token"
        cls.repo = cls.env["github.repository"].create({
            "github_id": 1,
            "full_name": "acme/shop",
            "user_id": cls.owner.id,
        })

    def test_sync_upserts_by_github_id(self):
        Repository = self.env["github.repository"]
        Repository._sync_from_api(self.owner, [
            {"id": 1, "name": "shop", "full_name": "acme/shop", "updated_at": "2026-01-15T10:30:00Z"},
            {"id": 2, "name": "blog", "full_name": "acme/blog", "description": None},
        ])
        repos = Repository.search([("user_id", "=", self.owner.id)])
        self.assertEqual(len(repos), 2)
        self.assertEqual(self.repo.name, "shop")
        self.assertEqual(str(self.repo.updated_at), "2026-01-15 10:30:00")

    def test_owner_can_push_description(self):
        with patch(GITHUB_REQUEST, return_value=MagicMock(status_code=200, ok=True)) as github_request:
            self.repo.with_user(self.owner).action_push_description_to_github()
        self.assertEqual(github_request.call_args.args[:3], ("PATCH", "/repos/acme/shop", "owner-token"))

    def test_other_user_cannot_use_owner_token(self):
        with patch(GITHUB_REQUEST) as github_request, self.assertRaises(AccessError):
            self.repo.with_user(self.other).action_push_description_to_github()
        github_request.assert_not_called()
