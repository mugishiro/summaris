"""Logging helper that standardises Lambda logger configuration."""

from __future__ import annotations

import logging
from typing import Any


def get_logger(name: str, level: int = logging.INFO, *, extra_handlers: list[logging.Handler] | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    if extra_handlers:
        for handler in extra_handlers:
            logger.addHandler(handler)

    # Avoid propagating to root to prevent duplicate logs in Lambda
    logger.propagate = False
    return logger
