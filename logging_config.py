"""Structured logging configuration for the application using structlog."""

import logging
import sys
import os
from typing import Optional, List

import structlog
from structlog.types import EventDict, Processor


def add_app_context(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Add Flask application context to log entries.

    Adds user_id, household_id, and request_id when available.
    """
    try:
        from flask import g, has_request_context

        if has_request_context():
            # Add user context
            if hasattr(g, "user") and g.user:
                event_dict["user_id"] = g.user.id
                event_dict["username"] = g.user.username

            # Add household context
            if hasattr(g, "household") and g.household:
                event_dict["household_id"] = g.household.id
                event_dict["household_name"] = g.household.name

            # Add request ID if available
            if hasattr(g, "request_id"):
                event_dict["request_id"] = g.request_id
    except (ImportError, RuntimeError):
        # Flask not available or not in request context
        pass

    return event_dict


def setup_logging(
    app_name: str = "auto_cart", level: Optional[str] = None, use_json: bool = False
) -> structlog.BoundLogger:
    """
    Configure and return a structured logger for the application.

    Args:
        app_name: Name of the application/logger
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               If None, uses INFO for production, DEBUG for development
        use_json: If True, output JSON format (recommended for production)
                  If False, output human-readable format (recommended for development)

    Returns:
        Configured structlog logger instance
    """
    # Determine log level
    if level is None:
        env = os.environ.get("FLASK_ENV", "development")
        level = "DEBUG" if env == "development" else "INFO"

    # Determine output format based on environment if not specified
    if use_json is None:
        env = os.environ.get("FLASK_ENV", "development")
        use_json = env == "production"

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    # Configure structlog processors
    processors: List[Processor] = [
        # Add log level
        structlog.stdlib.add_log_level,
        # Add logger name
        structlog.stdlib.add_logger_name,
        # Add timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Add stack info for exceptions
        structlog.processors.StackInfoRenderer(),
        # Format exceptions
        structlog.processors.format_exc_info,
        # Add application context (user, household, request_id)
        add_app_context,
        # Decode unicode
        structlog.processors.UnicodeDecoder(),
    ]

    # Add appropriate renderer based on format
    if use_json:
        # JSON output for production (machine-readable)
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Console output for development (human-readable with colors)
        processors.append(
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            )
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Return configured logger
    return structlog.get_logger(app_name)


# Create default logger instance
logger = setup_logging()
