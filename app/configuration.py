"""
configuration.py
Handles loading, saving, and validating the JSON settings file.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"

DEFAULTS: Dict[str, Any] = {
    "portal_url": "",
    "browser": "chromium",
    "default_reason": "",
    "page_load_timeout": 30,
    "element_wait_timeout": 15,
    "max_retries": 3,
    "require_confirmation": True,
    "processing_mode": "single",
    "theme": "light",
    "log_file": "logs/activity.log",
    "students": [],
    "headless": False,
}

VALID_BROWSERS = {"chromium", "firefox", "webkit"}
VALID_MODES = {"single", "multi"}


class ConfigError(Exception):
    """Raised when the configuration is invalid."""


class Configuration:
    """Manages persistent application settings."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self._path = path
        self._data: Dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------ load/save

    def load(self) -> None:
        """Load settings from disk, falling back to defaults for missing keys."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                # Merge with defaults so new keys are always present
                self._data = {**DEFAULTS, **loaded}
            except (json.JSONDecodeError, OSError) as exc:
                raise ConfigError(f"Could not read settings file: {exc}") from exc
        else:
            self._data = dict(DEFAULTS)
            self.save()

    def save(self) -> None:
        """Persist current settings to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except OSError as exc:
            raise ConfigError(f"Could not write settings file: {exc}") from exc

    # ------------------------------------------------------------------ getters

    def get(self, key: str, fallback: Any = None) -> Any:
        return self._data.get(key, fallback)

    @property
    def portal_url(self) -> str:
        return str(self._data.get("portal_url", ""))

    @property
    def browser(self) -> str:
        return str(self._data.get("browser", "chromium"))

    @property
    def default_reason(self) -> str:
        return str(self._data.get("default_reason", ""))

    @property
    def page_load_timeout(self) -> int:
        return int(self._data.get("page_load_timeout", 30))

    @property
    def element_wait_timeout(self) -> int:
        return int(self._data.get("element_wait_timeout", 15))

    @property
    def max_retries(self) -> int:
        return int(self._data.get("max_retries", 3))

    @property
    def require_confirmation(self) -> bool:
        return bool(self._data.get("require_confirmation", True))

    @property
    def processing_mode(self) -> str:
        return str(self._data.get("processing_mode", "single"))

    @property
    def theme(self) -> str:
        return str(self._data.get("theme", "light"))

    @property
    def log_file(self) -> str:
        return str(self._data.get("log_file", "logs/activity.log"))

    @property
    def students(self) -> List[str]:
        return list(self._data.get("students", []))

    @property
    def headless(self) -> bool:
        return bool(self._data.get("headless", False))

    # ------------------------------------------------------------------ setters

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def update(self, values: Dict[str, Any]) -> None:
        self._data.update(values)

    # ------------------------------------------------------------------ validation

    def validate(self) -> List[str]:
        """
        Return a list of human-readable error strings.
        Empty list means the config is valid.
        """
        errors: List[str] = []

        if not self.portal_url.strip():
            errors.append("Portal URL is not configured.")

        if self.browser not in VALID_BROWSERS:
            errors.append(
                f"Browser '{self.browser}' is not supported. "
                f"Choose from: {', '.join(sorted(VALID_BROWSERS))}."
            )

        if self.processing_mode not in VALID_MODES:
            errors.append(
                f"Processing mode '{self.processing_mode}' is invalid. "
                f"Choose 'single' or 'multi'."
            )

        if self.page_load_timeout < 5 or self.page_load_timeout > 300:
            errors.append("Page-load timeout must be between 5 and 300 seconds.")

        if self.element_wait_timeout < 2 or self.element_wait_timeout > 120:
            errors.append("Element-wait timeout must be between 2 and 120 seconds.")

        if self.max_retries < 0 or self.max_retries > 10:
            errors.append("Max retries must be between 0 and 10.")

        return errors
