import httpx
from core.logger import logger
from core.messages import TOOL_GITHUB_ERROR, INTERNAL_ERROR
from tools.common import require_token, build_github_headers, check_and_mark_call, check_account_ambiguity


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



async def github_list_repos(max_results: int = 10, account_username: str = "", workspace_id: str = "", user_id: str = "") -> list[dict]:
    """List the authenticated user's GitHub repositories."""
    ambiguity = await check_account_ambiguity(account_username, provider="github")
    if ambiguity:
        return [{"clarification_needed": ambiguity}]
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
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


async def github_list_issues(
    repo_full_name: str,
    state: str = "open",
    max_results: int = 5,
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> list[dict]:
    """List issues in a specific GitHub repository."""
    ambiguity = await check_account_ambiguity(account_username, provider="github")
    if ambiguity:
        return [{"clarification_needed": ambiguity}]
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
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


async def github_list_pull_requests(
    repo_full_name: str,
    state: str = "open",
    max_results: int = 5,
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> list[dict]:
    """List pull requests in a specific GitHub repository."""
    ambiguity = await check_account_ambiguity(account_username, provider="github")
    if ambiguity:
        return [{"clarification_needed": ambiguity}]
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
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


async def github_whoami(account_username: str = "", workspace_id: str = "", user_id: str = "") -> dict:
    """Fetch the authenticated GitHub user's profile to verify the token."""
    ambiguity = await check_account_ambiguity(account_username, provider="github")
    if ambiguity:
        return {"clarification_needed": ambiguity}
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
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


async def github_create_issue(
    repo_full_name: str,
    title: str,
    body: str = "",
    labels: list[str] = None,
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> dict:
    """Create a new issue in a GitHub repository."""
    if check_and_mark_call("github_create_issue", {"repo": repo_full_name, "title": title}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
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


async def github_comment_on_issue(
    repo_full_name: str,
    issue_number: int,
    body: str,
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> dict:
    """Post a comment on a GitHub issue or pull request."""
    if check_and_mark_call("github_comment_on_issue", {"repo": repo_full_name, "issue": issue_number}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
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


async def github_close_issue(
    repo_full_name: str,
    issue_number: int,
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> dict:
    """Close an open issue in a GitHub repository."""
    if check_and_mark_call("github_close_issue", {"repo": repo_full_name, "issue": issue_number}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
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


async def github_create_pr(
    repo_full_name: str,
    title: str,
    head: str,
    base: str = "main",
    body: str = "",
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> dict:
    """Create a pull request in a GitHub repository."""
    if check_and_mark_call("github_create_pr", {"repo": repo_full_name, "title": title, "head": head}):
        return {"status": "skipped", "reason": "duplicate call blocked"}
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
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


async def github_get_issue(
    repo_full_name: str,
    issue_number: int,
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> dict:
    """Fetch full details and comments of a specific GitHub issue."""
    ambiguity = await check_account_ambiguity(account_username, provider="github")
    if ambiguity:
        return {"clarification_needed": ambiguity}
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
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


async def github_get_pr(
    repo_full_name: str,
    pr_number: int,
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> dict:
    """Fetch full details and review summary of a specific GitHub Pull Request."""
    ambiguity = await check_account_ambiguity(account_username, provider="github")
    if ambiguity:
        return {"clarification_needed": ambiguity}
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
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


async def github_get_file_contents(
    repo_full_name: str,
    path: str,
    ref: str = "main",
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> dict:
    """Fetch the contents of a file OR list contents of a directory from a GitHub repository.

    If the path points to a directory, returns a directory listing (name, type, path, size).
    If the path points to a file, returns the decoded file content.
    """
    ambiguity = await check_account_ambiguity(account_username, provider="github")
    if ambiguity:
        return {"clarification_needed": ambiguity}
    import base64
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
        logger.info(f"Fetching '{path}' (ref: '{ref}') from '{repo_full_name}'")

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/contents/{path}",
                headers=build_github_headers(token),
                params={"ref": ref},
            )
            resp.raise_for_status()
            data = resp.json()

        # Directory: GitHub returns a list of entries
        if isinstance(data, list):
            entries = [
                {
                    "name": entry.get("name"),
                    "type": entry.get("type"),   # "file" or "dir"
                    "path": entry.get("path"),
                    "size": entry.get("size"),
                }
                for entry in data
            ]
            logger.success(f"Listed directory '{path}' ({len(entries)} entries)")
            return {
                "type": "directory",
                "path": path,
                "entries": entries,
            }

        # File: decode base64 content
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
            "type": "file",
            "name": data.get("name"),
            "path": data.get("path"),
            "size": data.get("size"),
            "content": decoded_text,
            "html_url": data.get("html_url"),
        }
    except Exception as exc:
        err_msg = _github_err("github_get_file_contents", exc)
        return {"error": err_msg}


async def github_get_repo_tree(
    repo_full_name: str,
    branch: str = "main",
    path_filter: str = "",
    max_files: int = 200,
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> dict:
    """Get the full recursive file tree of a GitHub repository in a single API call.

    Use this for:
    - Repo summary / architecture review (see all files at once)
    - Finding which files exist before deciding what to read
    - Exploring a subdirectory recursively (set path_filter e.g. 'app/' or 'src/')

    Unlike github_get_file_contents which shows one directory level, this returns
    ALL files and directories recursively using GitHub's Git Trees API.

    Args:
        repo_full_name: e.g. 'owner/repo'
        branch: branch or commit SHA (default: 'main')
        path_filter: optional prefix to scope results, e.g. 'app/' or 'src/utils'
        max_files: cap on returned entries (default 200, max 500)
    """
    ambiguity = await check_account_ambiguity(account_username, provider="github")
    if ambiguity:
        return {"clarification_needed": ambiguity}
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
        max_files = min(max_files, 500)
        logger.info(f"Fetching repo tree for '{repo_full_name}' (branch: '{branch}', filter: '{path_filter}')")

        async with httpx.AsyncClient(timeout=20.0) as client:
            # Step 1: resolve branch → commit SHA → tree SHA
            branch_resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/branches/{branch}",
                headers=build_github_headers(token),
            )
            branch_resp.raise_for_status()
            tree_sha = branch_resp.json()["commit"]["commit"]["tree"]["sha"]

            # Step 2: fetch full recursive tree
            tree_resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/git/trees/{tree_sha}",
                headers=build_github_headers(token),
                params={"recursive": "1"},
            )
            tree_resp.raise_for_status()
            tree_data = tree_resp.json()

        all_entries = tree_data.get("tree", [])
        truncated = tree_data.get("truncated", False)

        # Filter by path prefix if requested
        if path_filter:
            prefix = path_filter.rstrip("/")
            all_entries = [
                e for e in all_entries
                if e.get("path", "").startswith(prefix)
            ]

        # Cap and format
        entries = [
            {
                "path": e.get("path"),
                "type": "dir" if e.get("type") == "tree" else "file",
                "size": e.get("size"),  # None for directories
            }
            for e in all_entries[:max_files]
        ]

        logger.success(
            f"Repo tree for '{repo_full_name}': {len(entries)} entries"
            + (f" (filtered to '{path_filter}')" if path_filter else "")
            + (" [GitHub truncated large repo]" if truncated else "")
        )

        return {
            "repo": repo_full_name,
            "branch": branch,
            "total_entries": len(entries),
            "truncated": truncated or len(all_entries) > max_files,
            "tree": entries,
        }
    except Exception as exc:
        err_msg = _github_err("github_get_repo_tree", exc)
        return {"error": err_msg}


async def github_list_branches(
    repo_full_name: str,
    max_results: int = 30,
    account_username: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> dict:
    """List branches in a specific GitHub repository, sorted by most recently committed (newest first).

    Use this before creating a pull request to show the user which branches exist and
    suggest recently active branches as the likely head (source) branch.
    """
    ambiguity = await check_account_ambiguity(account_username, provider="github")
    if ambiguity:
        return {"clarification_needed": ambiguity}
    try:
        token = await require_token(workspace_id or user_id, "github", account_email=account_username)
        logger.info(f"Listing branches for repo '{repo_full_name}'")

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{repo_full_name}/branches",
                headers=build_github_headers(token),
                params={"per_page": min(max_results, 100)},
            )
            resp.raise_for_status()
            branches_data = resp.json()

            # Fetch commit date for each branch to enable sorting by recency
            branches = []
            for b in branches_data:
                sha = b.get("commit", {}).get("sha", "")
                committed_date = None
                if sha:
                    try:
                        commit_resp = await client.get(
                            f"https://api.github.com/repos/{repo_full_name}/commits/{sha}",
                            headers=build_github_headers(token),
                        )
                        if commit_resp.status_code == 200:
                            commit_data = commit_resp.json()
                            committed_date = (
                                commit_data.get("commit", {})
                                .get("committer", {})
                                .get("date")
                            )
                    except Exception:
                        pass

                branches.append({
                    "name": b.get("name"),
                    "protected": b.get("protected", False),
                    "sha": sha,
                    "last_committed": committed_date,
                })

            # Sort by most recently committed first (None values go to end)
            branches.sort(
                key=lambda x: x.get("last_committed") or "",
                reverse=True,
            )

            logger.success(f"Found {len(branches)} branches for '{repo_full_name}' (sorted by recency)")

            return {
                "repo": repo_full_name,
                "count": len(branches),
                "branches": branches,
                "note": "Branches are sorted by most recently committed first. The top branches are most likely candidates for a pull request head branch.",
            }
    except Exception as exc:
        err_msg = _github_err("github_list_branches", exc)
        return {"error": err_msg}

