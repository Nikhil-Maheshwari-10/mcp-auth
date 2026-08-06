"""
core/exceptions.py
Structured application exception hierarchy for mcp-auth.

Modeled after kt-assistant/app/core/exceptions.py.

All exceptions inherit from AppException (which extends HTTPException) so
FastAPI's default handler and our custom global handler both work seamlessly.
The global handler logs all AppExceptions uniformly and returns a consistent
JSON error shape: {"error": "<message>"}.

Usage:
    from core.exceptions import NotFoundException, BadRequestException, ...
    raise NotFoundException("Session '123' not found.")

Registration in main.py:
    from core.exceptions import AppException, app_exception_handler
    app.add_exception_handler(AppException, app_exception_handler)
"""

from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from core.messages import FRIENDLY_HTTP_MESSAGES


# ---------------------------------------------------------------------------
# Exception Hierarchy
# ---------------------------------------------------------------------------

class AppException(HTTPException):
    """Base application exception — maps to a specific HTTP status code."""
    def __init__(self, message: Optional[str] = None, status_code: int = 500):
        if not message:
            message = FRIENDLY_HTTP_MESSAGES.get(status_code, "An unexpected error occurred.")
        super().__init__(status_code=status_code, detail=message)


class NotFoundException(AppException):
    """404 — Resource does not exist."""
    def __init__(self, message: Optional[str] = None):
        super().__init__(message=message, status_code=404)


class BadRequestException(AppException):
    """400 — Caller sent invalid input."""
    def __init__(self, message: Optional[str] = None):
        super().__init__(message=message, status_code=400)


class UnauthorizedException(AppException):
    """401 — Not authenticated."""
    def __init__(self, message: Optional[str] = None):
        super().__init__(message=message, status_code=401)


class ForbiddenException(AppException):
    """403 — Authenticated but not authorized."""
    def __init__(self, message: Optional[str] = None):
        super().__init__(message=message, status_code=403)


class UnprocessableException(AppException):
    """422 — Input is syntactically valid but semantically unparseable."""
    def __init__(self, message: Optional[str] = None):
        super().__init__(message=message, status_code=422)


class RateLimitException(AppException):
    """429 — Too many requests (e.g. quota exhausted)."""
    def __init__(self, message: Optional[str] = None):
        super().__init__(message=message, status_code=429)


class ServiceUnavailableException(AppException):
    """503 — Downstream service (Google APIs, GitHub, etc.) is unavailable."""
    def __init__(self, message: Optional[str] = None):
        super().__init__(message=message, status_code=503)


class GatewayTimeoutException(AppException):
    """504 — Downstream service took too long to respond."""
    def __init__(self, message: Optional[str] = None):
        super().__init__(message=message, status_code=504)


# ---------------------------------------------------------------------------
# Global exception handler — uniform error JSON shape
# ---------------------------------------------------------------------------

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Catches all AppException subclasses and returns a consistent JSON body.

    - 5xx errors are logged at ERROR level with full context.
    - 4xx client errors are logged at WARNING level.
    - All responses follow the shape: {"error": "<message>"}

    Register in main.py via:
        app.add_exception_handler(AppException, app_exception_handler)
    """
    from core.logger import logger  # deferred to avoid circular import

    method = request.method
    path = request.url.path
    status = exc.status_code
    detail = exc.detail

    if status >= 500:
        logger.error(f"[API] {status} on {method} {path}: {detail}")
    else:
        logger.warning(f"[API] {status} on {method} {path}: {detail}")

    return JSONResponse(status_code=status, content={"error": detail})
