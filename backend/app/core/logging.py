"""Console logging setup used by the FastAPI app and workers."""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Idempotent root-logger setup."""
    root = logging.getLogger()
    if getattr(root, "_ai_dev_video_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    root._ai_dev_video_configured = True  # type: ignore[attr-defined]
