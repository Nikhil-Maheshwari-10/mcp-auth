"""
core/messages.py
Centralized string constants for all API error and success messages.
Import these instead of hardcoding strings in routers/handlers.
"""

# ---------------------------------------------------------------------------
# Google OAuth Scope Groups
# Maps friendly scope-category names to required Google OAuth scope strings.
# Used at callback to detect partial consent and at tool level to guard calls.
# ---------------------------------------------------------------------------
GOOGLE_SCOPE_GROUPS = {
    "gmail": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
    ],
    "calendar": [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ],
}

# ---------------------------------------------------------------------------
# HTTP Defaults (returned when no specific message is provided)
# ---------------------------------------------------------------------------
FRIENDLY_HTTP_MESSAGES = {
    400: "Invalid request. Please check your input and try again.",
    401: "Authentication required. Please sign in.",
    403: "Access denied. You do not have permission to perform this action.",
    404: "Resource not found.",
    405: "This action is not supported for this endpoint.",
    409: "Conflict detected. Please refresh and try again.",
    422: "Invalid input. Please correct the errors and try again.",
    429: "Too many requests. Please try again shortly.",
    500: "Something went wrong on our side. Please try again.",
    503: "Service temporarily unavailable. Please try again shortly.",
    504: "Request timed out. Please try again.",
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_NOT_AUTHENTICATED     = "Authentication required. Please sign in with Google."
AUTH_SESSION_EXPIRED       = "Your session has expired. Please sign in again."
AUTH_GITHUB_NOT_CONNECTED  = "GitHub account not connected. Please link GitHub in Settings."
AUTH_INVALID_STATE         = "OAuth state token is invalid or expired. Please try again."
AUTH_TOKEN_EXCHANGE_FAILED = "Failed to exchange authorization code. Please try again."
AUTH_MISSING_USER          = "No authenticated user found for this session."

# ---------------------------------------------------------------------------
# Tools / API calls
# ---------------------------------------------------------------------------
TOOL_GOOGLE_TOKEN_MISSING  = "Google account not connected. Please sign in with Google."
TOOL_GITHUB_TOKEN_MISSING  = "GitHub account not connected. Go to Settings to link your GitHub account."
TOOL_CALENDAR_ERROR        = "Failed to fetch calendar events: {}"
TOOL_GMAIL_ERROR           = "Failed to access Gmail: {}"
TOOL_GITHUB_ERROR          = "Failed to access GitHub: {}"

# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------
INTERNAL_ERROR             = "An internal error occurred. Please try again."
