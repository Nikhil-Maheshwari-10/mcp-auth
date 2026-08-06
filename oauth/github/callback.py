"""
Local listener that receives the OAuth redirect and extracts the authorization code.

Starts a temporary HTTP server on localhost:8080 (or whatever port is in
GITHUB_REDIRECT_URI). Handles exactly one request — the browser redirect from
GitHub — extracts `code` and `state` from the query string, then shuts down.

Called by auth.py immediately after opening the browser authorization URL.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles a single GET request from the OAuth redirect."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        self.server.auth_code = params.get("code", [None])[0]
        self.server.state = params.get("state", [None])[0]
        self.server.error = params.get("error", [None])[0]

        if self.server.auth_code:
            body = b"<h2>Authentication successful. You can close this tab.</h2>"
        else:
            body = b"<h2>Authentication failed. Check the terminal for details.</h2>"

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass


def wait_for_callback(port: int = 8080, timeout: int = 120) -> tuple[str, str]:
    """Start a local server and block until the OAuth redirect arrives.

    Args:
        port:    Must match the port in GITHUB_REDIRECT_URI.
        timeout: Seconds to wait before giving up (default 2 minutes).

    Returns:
        (code, state) — both strings, both non-empty on success.

    Raises:
        RuntimeError: If GitHub returned an error or the timeout expired.
    """
    server = HTTPServer(("localhost", port), _CallbackHandler)
    server.auth_code = None
    server.state = None
    server.error = None
    server.timeout = timeout

    server.handle_request()
    server.server_close()

    if server.error:
        raise RuntimeError(f"GitHub returned an OAuth error: {server.error}")
    if not server.auth_code:
        raise RuntimeError("Callback timed out or no code was received.")

    return server.auth_code, server.state

