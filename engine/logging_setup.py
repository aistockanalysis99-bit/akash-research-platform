"""Logging configuration: INFO to console, DEBUG to file."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from .config import LOG_DIR, LOG_LEVEL


def setup_logging(name: str = "akash") -> logging.Logger:
    """Configure logging once. Idempotent."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(LOG_LEVEL)
    console.setFormatter(fmt)
    logger.addHandler(console)

    log_file: Path = LOG_DIR / f"{name}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger of the root 'akash' logger."""
    setup_logging("akash")
    return logging.getLogger(f"akash.{name}")
