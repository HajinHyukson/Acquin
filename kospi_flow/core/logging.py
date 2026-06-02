"""Minimal logging setup shared across jobs.

Kept dependency-free (stdlib ``logging``). Our messages are routed through a
dedicated ``kospi_flow`` logger; the root logger is held at WARNING so noisy
third-party libraries don't spam the console. In particular, pykrx calls
``logging.info(args, kwargs)`` incorrectly on every failed request, which makes
Python's logging emit a ``--- Logging error --- TypeError`` traceback for each
one — holding root at WARNING suppresses those entirely while keeping our own
INFO logs.
"""

from __future__ import annotations

import logging

_CONFIGURED = False
_PACKAGE_LOGGER = "kospi_flow"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging once: our package at ``level``, root quiet at WARNING."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    pkg = logging.getLogger(_PACKAGE_LOGGER)
    pkg.setLevel(level)
    pkg.addHandler(handler)
    # Don't propagate to root, so our records aren't duplicated by any root
    # handler and aren't affected by the root level.
    pkg.propagate = False

    # Hold the root logger at WARNING. This filters third-party INFO/DEBUG spam
    # (notably pykrx's malformed ``logging.info(args, kwargs)`` debug calls)
    # before a record is ever created, so no broken-format tracebacks appear.
    root = logging.getLogger()
    if root.level == logging.NOTSET or root.level < logging.WARNING:
        root.setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger, ensuring logging is configured."""
    setup_logging()
    return logging.getLogger(name)
