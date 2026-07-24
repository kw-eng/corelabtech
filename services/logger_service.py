"""Application logging setup for CoreLabTech production/runtime diagnostics."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def build_logger(name: str, filename: str) -> logging.Logger:
    """Return a rotating file logger with a stable format."""

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = RotatingFileHandler(
        LOG_DIR / filename,
        maxBytes=int(os.getenv("LOG_MAX_BYTES", "5242880")),
        backupCount=int(os.getenv("LOG_BACKUP_COUNT", "5")),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


app_logger = build_logger("corelabtech.app", "app.log")
access_logger = build_logger("corelabtech.access", "access.log")
security_logger = build_logger("corelabtech.security", "security.log")
performance_logger = build_logger("corelabtech.performance", "performance.log")
ai_logger = build_logger("corelabtech.ai", "ai.log")
upload_logger = build_logger("corelabtech.uploads", "uploads.log")
auth_logger = build_logger("corelabtech.auth", "auth.log")
error_logger = build_logger("corelabtech.errors", "errors.log")
