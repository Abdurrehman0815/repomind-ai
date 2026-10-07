"""
RepoMind AI — Structured Logging Configuration

Uses structlog for structured logging.
Compatible with structlog 24.x using stdlib logger factory.
"""
import logging
import sys
from typing import Literal

import structlog


def configure_logging(
    level: str = "INFO",
    format: Literal["json", "console"] = "json",
) -> None:
    """Configure structlog with the given level and format."""

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure stdlib logging first — structlog forwards to it
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    # Pre-chain processors shared across formats
    pre_chain: list = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            *pre_chain,
            renderer,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
