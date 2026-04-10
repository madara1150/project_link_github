from odoo import fields, models


class GithubRepoSelector(models.TransientModel):
    _name = "github.repo.selector"
    _description = "GitHub Repository Selector Wizard"

    project_id = fields.Many2one(
        "project.project",
        string="Project",
        required=True,
        readonly=True,
    )
    available_repo_ids = fields.Many2many(
        "github.repository",
        "github_repo_selector_available_rel",
        string="Available Repositories",
    )
    repository_ids = fields.Many2many(
        "github.repository",
        "github_repo_selector_selected_rel",
        string="Repositories",
        domain="[('id', 'in', available_repo_ids)]",
    )

    def action_confirm(self):
        """Link selected repos to the project; unlink deselected ones."""
        self.ensure_one()
        project = self.project_id
        selected = self.repository_ids

        # Repos previously linked to this project but now deselected → clear project_id
        previously_linked = self.env["github.repository"].search([
            ("project_id", "=", project.id),
        ])
        to_unlink = previously_linked - selected
        if to_unlink:
            to_unlink.write({"project_id": False})

        # Newly selected repos → set project_id
        to_link = selected.filtered(lambda r: r.project_id != project)
        if to_link:
            to_link.write({"project_id": project.id})

        return {"type": "ir.actions.act_window_close"}
