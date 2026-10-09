"""
logging_manager.py
Provides structured, timestamped logging to a file and optional UI callback.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


class ActivityLogger:
    """
    Central logger for the Smart Attendance application.

    - Writes to a rotating log file.
    - Calls an optional UI callback so the dashboard can display messages live.
    - Never records passwords or authentication tokens.
    """

    def __init__(self, log_file: str = "logs/activity.log") -> None:
        self._ui_callback: Optional[Callable[[str, str], None]] = None
        self._log_path = Path(log_file)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        # Python standard logger
        self._logger = logging.getLogger("SmartAttendance")
        self._logger.setLevel(logging.DEBUG)

        if not self._logger.handlers:
            fh = logging.FileHandler(self._log_path, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            fh.setFormatter(formatter)
            self._logger.addHandler(fh)

    # ------------------------------------------------------------------ public

    def set_ui_callback(self, callback: Callable[[str, str], None]) -> None:
        """
        Register a callback that the dashboard uses to append log lines.
        Signature: callback(message: str, level: str)
        """
        self._ui_callback = callback

    def info(self, message: str) -> None:
        self._emit(message, "INFO")

    def warning(self, message: str) -> None:
        self._emit(message, "WARNING")

    def error(self, message: str) -> None:
        self._emit(message, "ERROR")

    def success(self, message: str) -> None:
        """Convenience method logged at INFO level but flagged as SUCCESS for the UI."""
        self._emit(message, "SUCCESS")

    def debug(self, message: str) -> None:
        self._emit(message, "DEBUG")

    # ------------------------------------------------------------------ private

    def _emit(self, message: str, level: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        display = f"[{timestamp}] {message}"

        if level == "ERROR":
            self._logger.error(message)
        elif level == "WARNING":
            self._logger.warning(message)
        elif level == "DEBUG":
            self._logger.debug(message)
        else:
            self._logger.info(message)

        if self._ui_callback:
            try:
                self._ui_callback(display, level)
            except Exception:
                pass  # Never let a UI error kill the automation thread
