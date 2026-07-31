def require_token(token_store_module) -> dict:
    """Loads the valid token and raises a standard error if missing."""
    token = token_store_module.get_valid_token()
    if token is None:
        name = "Google" if "google" in token_store_module.__name__ else "GitHub"
        raise RuntimeError(
            f"No {name} token found. Run `python -m oauth.{name.lower()}.auth` first."
        )
    return token

def build_github_headers(token: dict) -> dict:
    """Builds the standard headers needed for GitHub API requests."""
    return {
        "Authorization": f"Bearer {token['access_token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
