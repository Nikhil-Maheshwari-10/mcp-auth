"""
oauth.common — utilities that are genuinely identical across all providers.

Contains RFC 7636 PKCE helpers (pkce.py) so that each provider's auth.py
can import them without duplicating the generation logic.
"""
