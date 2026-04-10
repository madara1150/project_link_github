{
    "name": "Project GitHub Integration",
    "summary": "เชื่อม GitHub Pull Request กับ project.task อัตโนมัติผ่าน Webhook",
    "version": "16.0.2.0.0",
    "category": "Project Management",
    "author": "Aginix Technologies",
    "website": "https://github.com/madara1150/project_link_github",
    "license": "LGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        'project_key'
    ],
    "assets": {
        "web.assets_backend": [
            "project_github/static/src/js/github_login_widget.js",
        ],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/project_task_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
        "views/github_repository_views.xml",
    ],
}
