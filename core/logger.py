"""
core/logger.py — Structured, color-coded logging system for mcp-auth.

Inspired by kt-assistant logging architecture.
Outputs formatted, color-coded logs to terminal and rotated log files to logs/app.log.
"""

import os
import sys
import logging
from loguru import logger

# ─── Module name shortener ────────────────────────────────────────────────────
# Maps verbose module paths to short, readable tags shown in the terminal.
_MODULE_LABELS = {
    "api.main":                  "SERVER  ",
    "api.auth.google":           "AUTH-GOG",
    "api.auth.github":           "AUTH-GH ",
    "api.auth.middleware":       "SESSION ",
    "api.auth.session":          "SESSION ",
    "api.auth.refresh":          "REFRESH ",
    "db.token_repo":             "DATABASE",
    "db.engine":                 "DATABASE",
    "adk_agent.agent":           "AGENT   ",
    "adk_agent.prompts":         "AGENT   ",
    "mcp_server.tools.gmail":    "GMAIL   ",
    "mcp_server.tools.calendar": "CALENDAR",
    "mcp_server.tools.github":   "GITHUB  ",
    "mcp_server.tools.common":   "DATABASE",
    "core.logger":               "SYSTEM  ",
    "main":                      "SERVER  ",
    "uvicorn":                   "SERVER  ",
    "uvicorn.access":            "HTTP    ",
    "uvicorn.error":             "SERVER  ",
    "logging":                   "HTTP    ",
    "google_llm":                "LLM     ",
    "service_factory":           "SYSTEM  ",
    "local_storage":             "SYSTEM  ",
}


def _format(record):
    module = record["name"]
    # Allow explicitly passed label via logger.bind(label="XYZ")
    label = record["extra"].get("label") or _MODULE_LABELS.get(module, module.split(".")[-1][:8].upper().ljust(8))
    level = record["level"].name

    # Pick a color and badge per log level (high contrast on both Dark and Light themes)
    if level == "DEBUG":
        line_color = "<blue>"
        end_color = "</blue>"
        lvl_tag = "<blue>DBG</blue>"
    elif level == "INFO":
        line_color = ""
        end_color = ""
        lvl_tag = "<cyan><bold>INF</bold></cyan>"
    elif level == "SUCCESS":
        line_color = "<green>"
        end_color = "</green>"
        lvl_tag = "<green><bold>✓ OK</bold></green>"
    elif level == "WARNING":
        line_color = "<yellow>"
        end_color = "</yellow>"
        lvl_tag = "<yellow><bold>WRN</bold></yellow>"
    elif level == "ERROR":
        line_color = "<red>"
        end_color = "</red>"
        lvl_tag = "<red><bold>ERR</bold></red>"
    elif level == "CRITICAL":
        line_color = "<red><bold>"
        end_color = "</bold></red>"
        lvl_tag = "<red><bold>CRT</bold></red>"
    else:
        line_color = ""
        end_color = ""
        lvl_tag = level[:3]

    # Category color coding for quick visual grouping (avoiding <white> or <dim> which disappear on light backgrounds)
    cleaned_label = label.strip()
    if cleaned_label in ("DATABASE", "DB"):
        label_tag = f"<yellow>{label}</yellow>"
    elif cleaned_label in ("AGENT", "LLM", "MODEL", "CHAT"):
        label_tag = f"<blue><bold>{label}</bold></blue>"
    elif cleaned_label in ("GMAIL", "CALENDAR"):
        label_tag = f"<green>{label}</green>"
    elif cleaned_label in ("GITHUB",):
        label_tag = f"<magenta>{label}</magenta>"
    elif cleaned_label in ("AUTH-GOG", "AUTH-GH", "SESSION", "REFRESH"):
        label_tag = f"<cyan>{label}</cyan>"
    elif cleaned_label in ("SERVER", "SYSTEM"):
        label_tag = f"<magenta><bold>{label}</bold></magenta>"
    elif cleaned_label in ("HTTP", "ACCESS"):
        label_tag = f"<cyan>{label}</cyan>"
    elif cleaned_label in ("HTTP-ERR",):
        label_tag = f"<red>{label}</red>"
    else:
        label_tag = f"<cyan>{label}</cyan>"

    # ── Special per-message highlighting for important chat events ──────────
    # These patterns override the default level-based line color so that
    # user questions, agent answers, and tool calls are always easy to spot.
    msg = record["message"]
    if msg.startswith("[CHAT] Q:"):
        # User question — bright green, bold
        line_color = "<bold><green>"
        end_color  = "</green></bold>"
    elif msg.startswith("[CHAT] A:"):
        # Agent answer — bold cyan
        line_color = "<bold><cyan>"
        end_color  = "</cyan></bold>"
    elif msg.startswith("[AGENT] Calling tool:"):
        # Tool invocation — magenta
        line_color = "<magenta>"
        end_color  = "</magenta>"

    fmt = (
        "{time:HH:mm:ss}"
        f" {lvl_tag}"
        f" │ {label_tag} │"
        f" {line_color}{{message}}{end_color}"
        "\n{exception}"
    )
    return fmt


class InterceptHandler(logging.Handler):
    """Intercept standard Python logging and redirect to Loguru."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logger(log_level: str | None = None) -> None:
    """Configure Loguru console and file logging sinks."""
    level = (log_level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logger.remove()

    # ── Console Sink: colored & human-readable ──────────────────────────────
    logger.add(
        sys.stdout,
        level=level,
        format=_format,
        colorize=True,
    )

    # ── File Sink: plain text for search and archiving ───────────────────────
    os.makedirs("logs", exist_ok=True)
    logger.add(
        "logs/app.log",
        rotation="10 MB",
        retention="10 days",
        level="DEBUG",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        colorize=False,
    )

    # Intercept uvicorn and fastapi logs
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for uvicorn_logger in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logging.getLogger(uvicorn_logger).handlers = [InterceptHandler()]


# Initialize immediately upon module import
setup_logger()

__all__ = ["logger", "setup_logger"]
