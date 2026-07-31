"""
Shared PKCE helpers: generate code_verifier and code_challenge (RFC 7636).
Used by both google/auth.py and github/auth.py.
"""

import base64
import hashlib
import secrets


def generate_code_verifier(length: int = 64) -> str:
    """Return a cryptographically random URL-safe string (43–128 chars per RFC 7636).

    Uses `secrets.token_bytes` so the output is suitable for use as a
    code_verifier — it is never predictable, even if the process start
    time is known.
    """
    # token_bytes(n) gives n random bytes; base64url without padding gives
    # ceil(n * 4/3) characters. 64 bytes → 86 chars, well within [43, 128].
    return base64.urlsafe_b64encode(secrets.token_bytes(length)).rstrip(b"=").decode()


def generate_code_challenge(code_verifier: str) -> str:
    """Derive the S256 code_challenge from *code_verifier* (RFC 7636 §4.2).

    Algorithm:
        code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))

    The result is sent to the authorization endpoint; the verifier is sent
    later during token exchange so the server can verify they match.
    """
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
