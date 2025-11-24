"""
Central logging configuration helper.
"""

import logging
from typing import Optional

from common.config import get_settings


def configure_logging(level: Optional[int] = None) -> None:
    """Configure basic logging format for the application."""

    settings = get_settings()
    log_level = level or (logging.DEBUG if settings.environment != "production" else logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    """Return module-specific logger."""

    return logging.getLogger(name)


__all__ = ["configure_logging", "get_logger"]

