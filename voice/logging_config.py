"""Logging setup for voice CLI tools."""

from __future__ import annotations

import logging
from pathlib import Path


VOICE_LOG_PATH = Path("logs") / "voice.log"
_VOICE_FILE_HANDLER_NAME = "voice-file-handler"


def configure_voice_logging(level_name: str = "INFO", log_path: Path = VOICE_LOG_PATH) -> Path:
    """Configures file logging for voice commands and returns the log path."""
    level = _parse_level(level_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers:
        if handler.get_name() == _VOICE_FILE_HANDLER_NAME:
            handler.setLevel(level)
            return log_path

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.set_name(_VOICE_FILE_HANDLER_NAME)
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root_logger.addHandler(file_handler)
    return log_path


def _parse_level(level_name: str) -> int:
    level = getattr(logging, level_name.strip().upper(), None)

    if isinstance(level, int):
        return level

    return logging.INFO
