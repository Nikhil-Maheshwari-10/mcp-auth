import httpx
from mcp_server import mcp
from mcp_server.tools.common import require_token, build_github_headers


@mcp.tool
async def github_list_repos(max_results: int = 10, user_id: str = "") -> list[dict]:
    """List the authenticated user's GitHub repositories (including private ones).

    Args:
        max_results: Number of repos to return (default 10, max 30).
        user_id: The UUID of the user whose repos to fetch (optional if set in context).

    Returns:
        A list of dicts, each with: name, full_name, private, html_url, description.
    """
    token = await require_token(user_id, "github")
    max_results = min(max_results, 30)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.github.com/user/repos",
            headers=build_github_headers(token),
            params={"per_page": max_results, "sort": "updated"},
        )
        response.raise_for_status()
        repos = response.json()

    return [
        {
            "name": repo["name"],
            "full_name": repo["full_name"],
            "private": repo["private"],
            "html_url": repo["html_url"],
            "description": repo["description"],
        }
        for repo in repos
    ]


@mcp.tool
async def github_list_issues(
    repo_full_name: str,
    state: str = "open",
    max_results: int = 5,
    user_id: str = "",
) -> list[dict]:
    """List issues in a specific GitHub repository.

    Args:
        repo_full_name: The owner and name of the repo (e.g., "owner/repo").
        state: State of issues to return ("open", "closed", or "all"). Default is "open".
        max_results: Number of issues to return (default 5, max 30).
        user_id: The UUID of the user (optional if set in context).

    Returns:
        A list of dicts with issue details.
    """
    token = await require_token(user_id, "github")
    max_results = min(max_results, 30)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"https://api.github.com/repos/{repo_full_name}/issues",
            headers=build_github_headers(token),
            params={"state": state, "per_page": max_results},
        )
        response.raise_for_status()
        issues = response.json()

    return [
        {
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "html_url": issue["html_url"],
            "is_pull_request": "pull_request" in issue,
        }
        for issue in issues
    ]


@mcp.tool
async def github_list_pull_requests(
    repo_full_name: str,
    state: str = "open",
    max_results: int = 5,
    user_id: str = "",
) -> list[dict]:
    """List pull requests in a specific GitHub repository.

    Args:
        repo_full_name: The owner and name of the repo (e.g., "owner/repo").
        state: State of PRs to return ("open", "closed", or "all"). Default is "open".
        max_results: Number of PRs to return (default 5, max 30).
        user_id: The UUID of the user (optional if set in context).

    Returns:
        A list of dicts with PR details.
    """
    token = await require_token(user_id, "github")
    max_results = min(max_results, 30)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"https://api.github.com/repos/{repo_full_name}/pulls",
            headers=build_github_headers(token),
            params={"state": state, "per_page": max_results},
        )
        response.raise_for_status()
        prs = response.json()

    return [
        {
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],
            "html_url": pr["html_url"],
            "user": pr["user"]["login"],
        }
        for pr in prs
    ]


@mcp.tool
async def github_whoami(user_id: str = "") -> dict:
    """Fetch the authenticated GitHub user's profile to verify the token.

    Args:
        user_id: The UUID of the user (optional if set in context).

    Returns:
        User's GitHub profile info (login, name, email, public_repos, avatar_url).
    """
    token = await require_token(user_id, "github")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.github.com/user",
            headers=build_github_headers(token),
        )
        response.raise_for_status()
        data = response.json()

    return {
        "login": data.get("login"),
        "name": data.get("name"),
        "email": data.get("email"),
        "public_repos": data.get("public_repos"),
        "avatar_url": data.get("avatar_url"),
    }
