import httpx
from core.logger import logger
from core.messages import TOOL_GITHUB_ERROR, INTERNAL_ERROR
from mcp_server import mcp
from mcp_server.tools.common import require_token, build_github_headers, check_and_mark_call


def _github_err(context: str, exc: Exception) -> str:
    """Log and return a user-friendly error string for GitHub failures."""
    if isinstance(exc, httpx.HTTPStatusError):
        msg = f"{context}: GitHub API returned {exc.response.status_code}"
        logger.error(f"[GITHUB] {msg} — {exc.response.text[:120]}")
    elif isinstance(exc, RuntimeError):
        msg = str(exc)
        logger.warning(f"[GITHUB] {context}: {msg}")
    else:
        msg = TOOL_GITHUB_ERROR.format(str(exc))
        logger.error(f"[GITHUB] Unexpected error in {context}: {exc}", exc_info=True)
    return msg



@mcp.tool
async def github_list_repos(max_results: int = 10, user_id: str = "") -> list[dict]:
    """List the authenticated user's GitHub repositories."""
    try:
        token = await require_token(user_id, "github")
        max_results = min(max_results, 30)
        logger.info(f"Listing GitHub repositories (max_results: {max_results})")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.github.com/user/repos",
                headers=build_github_headers(token),
                params={"per_page": max_results, "sort": "updated"},
            )
            response.raise_for_status()
            repos = response.json()

        results = [
            {
                "name": repo["name"],
                "full_name": repo["full_name"],
                "private": repo["private"],
                "html_url": repo["html_url"],
                "description": repo["description"],
            }
            for repo in repos
        ]
        logger.success(f"Retrieved {len(results)} GitHub repositories")
        return results
    except Exception as exc:
        err_msg = _github_err("github_list_repos", exc)
        return [{"error": err_msg}]


@mcp.tool
async def github_list_issues(
    repo_full_name: str,
    state: str = "open",
    max_results: int = 5,
    user_id: str = "",
) -> list[dict]:
    """List issues in a specific GitHub repository."""
    try:
        token = await require_token(user_id, "github")
        max_results = min(max_results, 30)
        logger.info(f"Listing issues for repo '{repo_full_name}' (state: '{state}', max_results: {max_results})")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/issues",
                headers=build_github_headers(token),
                params={"state": state, "per_page": max_results},
            )
            response.raise_for_status()
            issues = response.json()

        results = [
            {
                "number": issue["number"],
                "title": issue["title"],
                "state": issue["state"],
                "html_url": issue["html_url"],
                "is_pull_request": "pull_request" in issue,
            }
            for issue in issues
        ]
        logger.success(f"Retrieved {len(results)} issues for '{repo_full_name}'")
        return results
    except Exception as exc:
        err_msg = _github_err("github_list_issues", exc)
        return [{"error": err_msg}]


@mcp.tool
async def github_list_pull_requests(
    repo_full_name: str,
    state: str = "open",
    max_results: int = 5,
    user_id: str = "",
) -> list[dict]:
    """List pull requests in a specific GitHub repository."""
    try:
        token = await require_token(user_id, "github")
        max_results = min(max_results, 30)
        logger.info(f"Listing pull requests for repo '{repo_full_name}' (state: '{state}', max_results: {max_results})")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/pulls",
                headers=build_github_headers(token),
                params={"state": state, "per_page": max_results},
            )
            response.raise_for_status()
            prs = response.json()

        results = [
            {
                "number": pr["number"],
                "title": pr["title"],
                "state": pr["state"],
                "html_url": pr["html_url"],
                "user": pr["user"]["login"],
            }
            for pr in prs
        ]
        logger.success(f"Retrieved {len(results)} PRs for '{repo_full_name}'")
        return results
    except Exception as exc:
        err_msg = _github_err("github_list_pull_requests", exc)
        return [{"error": err_msg}]


@mcp.tool
async def github_whoami(user_id: str = "") -> dict:
    """Fetch the authenticated GitHub user's profile to verify the token."""
    try:
        token = await require_token(user_id, "github")
        logger.info("Fetching authenticated GitHub user profile")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.github.com/user",
                headers=build_github_headers(token),
            )
            response.raise_for_status()
            data = response.json()

        login = data.get("login")
        logger.success(f"GitHub user profile loaded: '@{login}'")
        return {
            "login": login,
            "name": data.get("name"),
            "email": data.get("email"),
            "public_repos": data.get("public_repos"),
            "avatar_url": data.get("avatar_url"),
        }
    except Exception as exc:
        err_msg = _github_err("github_whoami", exc)
        return {"error": err_msg}


@mcp.tool
async def github_create_issue(
    repo_full_name: str,
    title: str,
    body: str = "",
    labels: list[str] = None,
    user_id: str = "",
) -> dict:
    """Create a new issue in a GitHub repository."""
    if check_and_mark_call("github_create_issue", {"repo": repo_full_name, "title": title}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(user_id, "github")
        logger.info(f"Creating issue in '{repo_full_name}': '{title}'")

        payload = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://api.github.com/repos/{repo_full_name}/issues",
                headers=build_github_headers(token),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            logger.success(f"Issue #{data.get('number')} created in '{repo_full_name}'")
            return {
                "status": "created",
                "number": data.get("number"),
                "title": data.get("title"),
                "html_url": data.get("html_url"),
                "state": data.get("state"),
            }
    except Exception as exc:
        err_msg = _github_err("github_create_issue", exc)
        return {"error": err_msg}


@mcp.tool
async def github_comment_on_issue(
    repo_full_name: str,
    issue_number: int,
    body: str,
    user_id: str = "",
) -> dict:
    """Post a comment on a GitHub issue or pull request."""
    if check_and_mark_call("github_comment_on_issue", {"repo": repo_full_name, "issue": issue_number}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(user_id, "github")
        logger.info(f"Adding comment to #{issue_number} in '{repo_full_name}'")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://api.github.com/repos/{repo_full_name}/issues/{issue_number}/comments",
                headers=build_github_headers(token),
                json={"body": body},
            )
            response.raise_for_status()
            data = response.json()
            logger.success(f"Comment posted on #{issue_number} in '{repo_full_name}'")
            return {
                "status": "commented",
                "id": data.get("id"),
                "html_url": data.get("html_url"),
            }
    except Exception as exc:
        err_msg = _github_err("github_comment_on_issue", exc)
        return {"error": err_msg}


@mcp.tool
async def github_close_issue(
    repo_full_name: str,
    issue_number: int,
    user_id: str = "",
) -> dict:
    """Close an open issue in a GitHub repository."""
    if check_and_mark_call("github_close_issue", {"repo": repo_full_name, "issue": issue_number}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(user_id, "github")
        logger.info(f"Closing issue #{issue_number} in '{repo_full_name}'")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.patch(
                f"https://api.github.com/repos/{repo_full_name}/issues/{issue_number}",
                headers=build_github_headers(token),
                json={"state": "closed"},
            )
            response.raise_for_status()
            data = response.json()
            logger.success(f"Issue #{issue_number} closed in '{repo_full_name}'")
            return {
                "status": "closed",
                "number": data.get("number"),
                "state": data.get("state"),
                "html_url": data.get("html_url"),
            }
    except Exception as exc:
        err_msg = _github_err("github_close_issue", exc)
        return {"error": err_msg}


@mcp.tool
async def github_create_pr(
    repo_full_name: str,
    title: str,
    head: str,
    base: str = "main",
    body: str = "",
    user_id: str = "",
) -> dict:
    """Create a pull request in a GitHub repository."""
    if check_and_mark_call("github_create_pr", {"repo": repo_full_name, "title": title, "head": head}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(user_id, "github")
        logger.info(f"Creating PR '{title}' ({head} -> {base}) in '{repo_full_name}'")

        payload = {
            "title": title,
            "head": head,
            "base": base,
            "body": body,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://api.github.com/repos/{repo_full_name}/pulls",
                headers=build_github_headers(token),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            logger.success(f"PR #{data.get('number')} created in '{repo_full_name}'")
            return {
                "status": "created",
                "number": data.get("number"),
                "title": data.get("title"),
                "html_url": data.get("html_url"),
                "state": data.get("state"),
            }
    except Exception as exc:
        err_msg = _github_err("github_create_pr", exc)
        return {"error": err_msg}


@mcp.tool
async def github_get_issue(
    repo_full_name: str,
    issue_number: int,
    user_id: str = "",
) -> dict:
    """Fetch full details and comments of a specific GitHub issue."""
    try:
        token = await require_token(user_id, "github")
        logger.info(f"Fetching issue #{issue_number} from '{repo_full_name}'")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/issues/{issue_number}",
                headers=build_github_headers(token),
            )
            resp.raise_for_status()
            data = resp.json()

            comments_resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/issues/{issue_number}/comments",
                headers=build_github_headers(token),
                params={"per_page": 10},
            )
            comments = []
            if comments_resp.status_code == 200:
                for c in comments_resp.json():
                    comments.append({
                        "user": c.get("user", {}).get("login"),
                        "body": c.get("body"),
                        "created_at": c.get("created_at"),
                    })

            title = data.get("title")
            logger.success(f"Loaded issue #{issue_number}: '{title}'")

            return {
                "number": data.get("number"),
                "title": title,
                "state": data.get("state"),
                "user": data.get("user", {}).get("login"),
                "body": data.get("body") or "(no description provided)",
                "labels": [label.get("name") for label in data.get("labels", [])],
                "comments_count": data.get("comments", 0),
                "recent_comments": comments,
                "html_url": data.get("html_url"),
            }
    except Exception as exc:
        err_msg = _github_err("github_get_issue", exc)
        return {"error": err_msg}


@mcp.tool
async def github_get_pr(
    repo_full_name: str,
    pr_number: int,
    user_id: str = "",
) -> dict:
    """Fetch full details and review summary of a specific GitHub Pull Request."""
    try:
        token = await require_token(user_id, "github")
        logger.info(f"Fetching PR #{pr_number} from '{repo_full_name}'")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}",
                headers=build_github_headers(token),
            )
            resp.raise_for_status()
            data = resp.json()

            title = data.get("title")
            logger.success(f"Loaded PR #{pr_number}: '{title}'")

            return {
                "number": data.get("number"),
                "title": title,
                "state": data.get("state"),
                "user": data.get("user", {}).get("login"),
                "body": data.get("body") or "(no description provided)",
                "head": data.get("head", {}).get("ref"),
                "base": data.get("base", {}).get("ref"),
                "merged": data.get("merged", False),
                "mergeable": data.get("mergeable"),
                "additions": data.get("additions"),
                "deletions": data.get("deletions"),
                "changed_files": data.get("changed_files"),
                "html_url": data.get("html_url"),
            }
    except Exception as exc:
        err_msg = _github_err("github_get_pr", exc)
        return {"error": err_msg}


@mcp.tool
async def github_get_file_contents(
    repo_full_name: str,
    path: str,
    ref: str = "main",
    user_id: str = "",
) -> dict:
    """Fetch the contents of a file from a GitHub repository."""
    import base64
    try:
        token = await require_token(user_id, "github")
        logger.info(f"Fetching file '{path}' (ref: '{ref}') from '{repo_full_name}'")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/contents/{path}",
                headers=build_github_headers(token),
                params={"ref": ref},
            )
            resp.raise_for_status()
            data = resp.json()

            raw_content = data.get("content", "")
            encoding = data.get("encoding", "")

            decoded_text = ""
            if encoding == "base64" and raw_content:
                try:
                    decoded_text = base64.b64decode(raw_content).decode("utf-8", errors="replace")
                except Exception:
                    decoded_text = "(Binary file content)"
            else:
                decoded_text = raw_content

            logger.success(f"Loaded file '{path}' ({data.get('size')} bytes)")
            return {
                "name": data.get("name"),
                "path": data.get("path"),
                "size": data.get("size"),
                "content": decoded_text,
                "html_url": data.get("html_url"),
            }
    except Exception as exc:
        err_msg = _github_err("github_get_file_contents", exc)
        return {"error": err_msg}



