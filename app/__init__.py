"""Application package initialization."""
from __future__ import annotations

import logging
import os


def _configure_logging() -> None:
    """Configure basic logging if the host app has not done so."""

    root_logger = logging.getLogger()
    if root_logger.handlers:  # respect existing logging configuration
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


_configure_logging()

__all__ = []
