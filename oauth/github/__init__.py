"""
oauth/github — Core GitHub OAuth2 business logic.

Contains pure functions for building auth URLs and exchanging authorization codes.
Has no dependency on FastAPI or HTTP request objects — import and call from
api/auth/github.py (routes) or tests.
"""
