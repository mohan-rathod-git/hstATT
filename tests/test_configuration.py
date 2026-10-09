"""
test_configuration.py
Unit tests for Configuration loading, defaults, validation, and persistence.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from app.configuration import Configuration, ConfigError, DEFAULTS


@pytest.fixture
def tmp_config(tmp_path):
    """Return a Configuration instance backed by a temp directory."""
    cfg_path = tmp_path / "settings.json"
    return Configuration(path=cfg_path)


class TestDefaults:
    def test_fresh_config_has_defaults(self, tmp_config):
        for key, default in DEFAULTS.items():
            assert tmp_config.get(key) == default

    def test_portal_url_empty_by_default(self, tmp_config):
        assert tmp_config.portal_url == ""

    def test_browser_default_chromium(self, tmp_config):
        assert tmp_config.browser == "chromium"

    def test_max_retries_default(self, tmp_config):
        assert tmp_config.max_retries == 3


class TestLoadSave:
    def test_save_creates_file(self, tmp_config, tmp_path):
        tmp_config.save()
        assert (tmp_path / "settings.json").exists()

    def test_round_trip(self, tmp_path):
        cfg_path = tmp_path / "settings.json"
        cfg1 = Configuration(path=cfg_path)
        cfg1.set("portal_url", "https://example.gov.in/attend")
        cfg1.save()

        cfg2 = Configuration(path=cfg_path)
        assert cfg2.portal_url == "https://example.gov.in/attend"

    def test_missing_key_falls_back_to_default(self, tmp_path):
        """Saved file missing a key should load with the default value."""
        cfg_path = tmp_path / "settings.json"
        cfg_path.write_text(json.dumps({"portal_url": "https://x.gov"}), encoding="utf-8")

        cfg = Configuration(path=cfg_path)
        assert cfg.max_retries == DEFAULTS["max_retries"]

    def test_corrupt_json_raises_config_error(self, tmp_path):
        cfg_path = tmp_path / "settings.json"
        cfg_path.write_text("NOT VALID JSON {{{", encoding="utf-8")

        with pytest.raises(ConfigError):
            Configuration(path=cfg_path)


class TestValidation:
    def test_empty_url_fails(self, tmp_config):
        errors = tmp_config.validate()
        assert any("URL" in e for e in errors)

    def test_valid_config_passes(self, tmp_config):
        tmp_config.update({
            "portal_url": "https://portal.example.gov.in",
            "browser": "chromium",
            "processing_mode": "single",
            "page_load_timeout": 30,
            "element_wait_timeout": 15,
            "max_retries": 3,
        })
        assert tmp_config.validate() == []

    def test_invalid_browser_fails(self, tmp_config):
        tmp_config.set("portal_url", "https://x.gov")
        tmp_config.set("browser", "internet_explorer")
        errors = tmp_config.validate()
        assert any("browser" in e.lower() or "Browser" in e for e in errors)

    def test_invalid_mode_fails(self, tmp_config):
        tmp_config.set("portal_url", "https://x.gov")
        tmp_config.set("processing_mode", "automatic")
        errors = tmp_config.validate()
        assert any("mode" in e.lower() for e in errors)

    def test_timeout_below_minimum_fails(self, tmp_config):
        tmp_config.set("portal_url", "https://x.gov")
        tmp_config.set("page_load_timeout", 1)
        errors = tmp_config.validate()
        assert any("timeout" in e.lower() for e in errors)

    def test_max_retries_above_limit_fails(self, tmp_config):
        tmp_config.set("portal_url", "https://x.gov")
        tmp_config.set("max_retries", 99)
        errors = tmp_config.validate()
        assert any("retries" in e.lower() or "retry" in e.lower() for e in errors)
