"""
oauth/google — Core Google OAuth2 business logic.

Contains pure functions for building auth URLs, exchanging authorization codes,
and detecting missing consent scopes. Has no dependency on FastAPI or HTTP request
objects — import and call from api/auth/google.py (routes) or tests.
"""
