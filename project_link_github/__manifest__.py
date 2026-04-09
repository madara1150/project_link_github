{
    "name": "Project GitHub Integration",
    "summary": "เชื่อม GitHub Pull Request กับ project.task อัตโนมัติผ่าน Webhook",
    "version": "16.0.1.0.0",
    "category": "Project Management",
    "author": "KMITL",
    "website": "",
    "license": "LGPL-3",
    "application": False,
    "installable": True,
    "depends": [
        "project",
        "project_task_pull_request",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/project_task_views.xml",
        "views/res_config_settings_views.xml",
    ],
}
