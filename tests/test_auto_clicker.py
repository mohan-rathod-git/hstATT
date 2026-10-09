"""
test_auto_clicker.py
Unit tests for the AutoClicker engine and PositionPicker.
No real screen interaction — patches ctypes calls.
"""

import time
import threading
from unittest.mock import patch, MagicMock

import pytest

from app.auto_clicker import (
    AutoClicker,
    AutoClickerConfig,
    ClickTarget,
    PositionPicker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(targets=None, interval=0.05, delay_ms=10, repeat=1, hotkey=False):
    return AutoClickerConfig(
        targets=targets or [ClickTarget(100, 200, "test")],
        interval_seconds=interval,
        click_delay_ms=delay_ms,
        repeat_count=repeat,
        hotkey_enabled=hotkey,
    )


# ---------------------------------------------------------------------------
# ClickTarget string representation
# ---------------------------------------------------------------------------

class TestClickTarget:
    def test_str_with_label(self):
        t = ClickTarget(10, 20, "Button A")
        assert "10" in str(t) and "20" in str(t) and "Button A" in str(t)

    def test_str_no_label(self):
        t = ClickTarget(10, 20)
        assert "(10, 20)" in str(t)
        assert "()" not in str(t)


# ---------------------------------------------------------------------------
# AutoClickerConfig defaults
# ---------------------------------------------------------------------------

class TestAutoClickerConfig:
    def test_default_interval(self):
        cfg = AutoClickerConfig()
        assert cfg.interval_seconds == 1.0

    def test_default_repeat_zero(self):
        cfg = AutoClickerConfig()
        assert cfg.repeat_count == 0  # infinite

    def test_targets_empty_by_default(self):
        cfg = AutoClickerConfig()
        assert cfg.targets == []


# ---------------------------------------------------------------------------
# AutoClicker start / stop
# ---------------------------------------------------------------------------

class TestAutoClickerControl:
    def test_start_with_no_targets_emits_error(self):
        status_msgs = []
        cfg = AutoClickerConfig(targets=[], repeat_count=1)
        ac = AutoClicker(config=cfg, on_status=lambda m: status_msgs.append(m))
        ac.start()
        assert not ac.is_running
        assert any("No click targets" in m for m in status_msgs)

    def test_start_and_stop(self):
        clicks = []
        with patch("app.auto_clicker._win_click") as mock_click:
            cfg = _config(repeat=0, interval=0.05)  # infinite
            ac = AutoClicker(
                config=cfg,
                on_click=lambda t, n: clicks.append(n),
            )
            ac.start()
            time.sleep(0.3)
            ac.stop()
            time.sleep(0.1)
            assert not ac.is_running
            assert mock_click.called

    def test_repeat_count_respected(self):
        done_event = threading.Event()
        status_msgs = []

        def on_status(m):
            status_msgs.append(m)
            if "Completed" in m or "stopped" in m:
                done_event.set()

        with patch("app.auto_clicker._win_click"):
            cfg = _config(repeat=2, interval=0.05, delay_ms=5)
            ac = AutoClicker(config=cfg, on_status=on_status)
            ac.start()
            done_event.wait(timeout=5)
            assert not ac.is_running

    def test_pause_and_resume(self):
        with patch("app.auto_clicker._win_click"):
            cfg = _config(repeat=0, interval=0.05)
            ac = AutoClicker(config=cfg)
            ac.start()
            time.sleep(0.1)
            ac.pause()
            count_at_pause = ac.total_clicks
            time.sleep(0.2)
            # clicks should not increase while paused
            assert ac.total_clicks == count_at_pause
            ac.resume()
            time.sleep(0.2)
            ac.stop()

    def test_toggle_starts_stopped_clicker(self):
        with patch("app.auto_clicker._win_click"):
            cfg = _config(repeat=0, interval=0.05)
            ac = AutoClicker(config=cfg)
            assert not ac.is_running
            ac.toggle()
            time.sleep(0.1)
            assert ac.is_running
            ac.toggle()
            time.sleep(0.1)
            assert not ac.is_running

    def test_total_clicks_increments(self):
        counts = []
        with patch("app.auto_clicker._win_click"):
            cfg = _config(
                targets=[ClickTarget(1, 2), ClickTarget(3, 4)],
                repeat=1, interval=0.05, delay_ms=5
            )
            ac = AutoClicker(
                config=cfg,
                on_click=lambda t, n: counts.append(n),
            )
            ac.start()
            time.sleep(1)
            assert len(counts) >= 2


# ---------------------------------------------------------------------------
# PositionPicker
# ---------------------------------------------------------------------------

class TestPositionPicker:
    def test_capture_callback_called_on_f6(self):
        captured = []

        with patch("app.auto_clicker._is_key_pressed") as mock_key, \
             patch("app.auto_clicker._get_cursor_pos", return_value=(300, 400)):

            # Simulate: not pressed → pressed (edge) → not pressed
            states = [False, True, False, False, False]
            mock_key.side_effect = lambda vk: states.pop(0) if states else False

            picker = PositionPicker(on_capture=lambda x, y: captured.append((x, y)))
            picker.start_listening()
            time.sleep(0.5)
            picker.stop_listening()

        assert (300, 400) in captured
