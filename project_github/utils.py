"""Helpers shared by the models and controllers of this module."""
import requests

GITHUB_API_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_PAGE_SIZE = 100

# The prefix predates the rename to project_github. It is kept so that existing
# databases keep their settings without a migration script.
PARAM_WEBHOOK_SECRET = "kmitl_project_github.webhook_secret"
PARAM_TASK_PREFIX = "kmitl_project_github.task_prefix"
PARAM_CLIENT_ID = "kmitl_project_github.client_id"
PARAM_CLIENT_SECRET = "kmitl_project_github.client_secret"


def github_headers(token=None):
    """Return the standard GitHub API headers, with a Bearer token if given."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_request(method, path, token, timeout=15, **kwargs):
    """Call the GitHub REST API and return the raw response.

    Args:
        method (str): HTTP verb, e.g. "GET".
        path   (str): API path starting with a slash, e.g. "/user/repos".
        token  (str): GitHub access token.

    Raises:
        requests.RequestException: On network failure. HTTP error statuses are
            not raised here; callers decide which ones are acceptable.
    """
    return requests.request(
        method,
        f"{GITHUB_API_URL}{path}",
        headers=github_headers(token),
        timeout=timeout,
        **kwargs,
    )


def fetch_user_repos(token):
    """Fetch every repository accessible by the authenticated user (paginated).

    Raises:
        requests.RequestException: If any page fails, so that callers never
            mistake an expired token for an account without repositories.
    """
    repos = []
    page = 1
    while True:
        resp = github_request(
            "GET",
            "/user/repos",
            token,
            params={"per_page": GITHUB_PAGE_SIZE, "page": page, "sort": "updated"},
        )
        resp.raise_for_status()
        batch = resp.json()
        repos.extend(batch)
        if len(batch) < GITHUB_PAGE_SIZE:
            return repos
        page += 1


def notification_action(title, message, notification_type="success"):
    """Return a client action that displays a toast notification."""
    return {
        "type": "ir.actions.client",
        "tag": "display_notification",
        "params": {
            "title": title,
            "message": message,
            "type": notification_type,
            "sticky": False,
        },
    }
