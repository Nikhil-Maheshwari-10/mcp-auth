import requests
from mcp_server import mcp
from mcp_server.tools.common import require_token, build_github_headers
from oauth.github import token_store

@mcp.tool
def github_list_repos(max_results: int = 10) -> list[dict]:
    """List the authenticated user's GitHub repositories (including private ones).

    Args:
        max_results: Number of repos to return (default 10, max 30).

    Returns:
        A list of dicts, each with: name, full_name, private, html_url, description.

    Requires 'repo' scope.
    """
    token = require_token(token_store)
    max_results = min(max_results, 30)

    response = requests.get(
        "https://api.github.com/user/repos",
        headers=build_github_headers(token),
        params={"per_page": max_results, "sort": "updated"},
        timeout=10,
    )
    response.raise_for_status()

    return [
        {
            "name": repo["name"],
            "full_name": repo["full_name"],
            "private": repo["private"],
            "html_url": repo["html_url"],
            "description": repo["description"],
        }
        for repo in response.json()
    ]

@mcp.tool
def github_list_issues(repo_full_name: str, state: str = "open", max_results: int = 5) -> list[dict]:
    """List issues in a specific GitHub repository.

    Args:
        repo_full_name: The owner and name of the repo (e.g., "Nikhil-Maheshwari-10/mcp-auth").
        state: State of issues to return ("open", "closed", or "all"). Default is "open".
        max_results: Number of issues to return (default 5, max 30).

    Returns:
        A list of dicts with issue details.
    """
    token = require_token(token_store)
    max_results = min(max_results, 30)

    response = requests.get(
        f"https://api.github.com/repos/{repo_full_name}/issues",
        headers=build_github_headers(token),
        params={"state": state, "per_page": max_results},
        timeout=10,
    )
    response.raise_for_status()

    # The GitHub API returns PRs as issues too. We filter them out here if needed,
    # but returning both is usually fine.
    return [
        {
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "html_url": issue["html_url"],
            "is_pull_request": "pull_request" in issue,
        }
        for issue in response.json()
    ]

@mcp.tool
def github_list_pull_requests(repo_full_name: str, state: str = "open", max_results: int = 5) -> list[dict]:
    """List pull requests in a specific GitHub repository.

    Args:
        repo_full_name: The owner and name of the repo (e.g., "Nikhil-Maheshwari-10/mcp-auth").
        state: State of PRs to return ("open", "closed", or "all"). Default is "open".
        max_results: Number of PRs to return (default 5, max 30).

    Returns:
        A list of dicts with PR details.
    """
    token = require_token(token_store)
    max_results = min(max_results, 30)

    response = requests.get(
        f"https://api.github.com/repos/{repo_full_name}/pulls",
        headers=build_github_headers(token),
        params={"state": state, "per_page": max_results},
        timeout=10,
    )
    response.raise_for_status()

    return [
        {
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],
            "html_url": pr["html_url"],
            "user": pr["user"]["login"],
        }
        for pr in response.json()
    ]

@mcp.tool
def github_whoami() -> dict:
    """Fetch the authenticated GitHub user's profile to verify the token.

    Makes a GET request to GitHub's /user endpoint using the stored
    access_token. Returns the user's login, name, email, and public repos count.

    Raises an error if not authenticated or if the token is invalid/revoked.
    """
    token = require_token(token_store)

    response = requests.get(
        "https://api.github.com/user",
        headers=build_github_headers(token),
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    # Return a focused subset — the full response has 30+ fields.
    return {
        "login": data.get("login"),
        "name": data.get("name"),
        "email": data.get("email"),
        "public_repos": data.get("public_repos"),
        "avatar_url": data.get("avatar_url"),
    }
