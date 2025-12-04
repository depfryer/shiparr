from __future__ import annotations

import logging

from Shiparr.logging_utils import configure_logging, get_logger


def test_get_logger_names():
    root = get_logger()
    assert root.name == "Shiparr"

    mod = get_logger("foo.bar")
    assert mod.name == "Shiparr.foo.bar"


def test_configure_logging_sets_level():
    # Force a known logging configuration
    for h in logging.getLogger().handlers[:]:
        logging.getLogger().removeHandler(h)

    configure_logging("DEBUG")
    logger = get_logger()
    assert logger.isEnabledFor(logging.DEBUG)

    # Calling again with another level should update the Shiparr logger
    configure_logging("INFO")
    logger = get_logger()
    assert logger.isEnabledFor(logging.INFO)
