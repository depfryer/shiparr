"""Logging utilities for Shiparr.

Provides a central logger and configuration helper so we can get
consistent, structured-ish logs across the app.
"""

from __future__ import annotations

import logging
from typing import Optional

LOGGER_NAME = "Shiparr"


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging for the Shiparr process.

    Called once from the CLI entrypoint (``Shiparr.app.main``).
    """

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Only configure if nothing is configured yet, to play nice with tests.
    if logging.getLogger().handlers:
        logging.getLogger(LOGGER_NAME).setLevel(numeric_level)
        return

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Reduce noise from libraries
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a logger under the Shiparr namespace."""

    if name is None:
        return logging.getLogger(LOGGER_NAME)
    # Nest module name under the main logger namespace
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
