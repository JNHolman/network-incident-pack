"""Logging configuration for the Incident Pack CLI."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"


def configure_logging(level: str) -> None:
    """Configure process-wide CLI logging using a validated logging level name."""
    numeric_level = getattr(logging, level.upper())
    logging.basicConfig(level=numeric_level, format=LOG_FORMAT)
