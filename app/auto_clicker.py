"""
auto_clicker.py
Screen-coordinate auto-clicker that runs in a background thread.

Features:
  - Click at one or more (X, Y) targets in sequence
  - Configurable interval between clicks (seconds, supports decimals)
  - Configurable repeat count (or loop forever)
  - Pick-location mode: hover anywhere on screen, press F6 to capture the coordinate
  - Hotkey F8 to start / stop from anywhere on screen
  - Live click counter fed back to the UI via a callback
"""

import threading
import time
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# ---------------------------------------------------------------------------
# Windows API helpers (no external dependency — pure ctypes)
# ---------------------------------------------------------------------------

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32


def _win_click(x: int, y: int) -> None:
    """Perform a left mouse button click at screen coordinates (x, y)."""
    # Move cursor
    _user32.SetCursorPos(x, y)
    time.sleep(0.04)
    # MOUSEEVENTF_LEFTDOWN  = 0x0002
    # MOUSEEVENTF_LEFTUP    = 0x0004
    _user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.04)
    _user32.mouse_event(0x0004, 0, 0, 0, 0)


def _get_cursor_pos() -> tuple[int, int]:
    """Return current mouse cursor (x, y)."""
    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]
    pt = POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _is_key_pressed(vk_code: int) -> bool:
    """Return True if the given virtual key is currently held down."""
    return bool(_user32.GetAsyncKeyState(vk_code) & 0x8000)


# Virtual-key codes used as hotkeys
VK_F6 = 0x75   # capture position
VK_F8 = 0x77   # toggle start/stop


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ClickTarget:
    x: int
    y: int
    label: str = ""

    def __str__(self) -> str:
        lbl = f" ({self.label})" if self.label else ""
        return f"({self.x}, {self.y}){lbl}"


@dataclass
class AutoClickerConfig:
    targets: List[ClickTarget] = field(default_factory=list)
    interval_seconds: float = 1.0      # pause between each full cycle
    click_delay_ms: int = 100          # ms between individual targets in one cycle
    repeat_count: int = 0              # 0 = infinite
    hotkey_enabled: bool = True        # F8 toggles start/stop


# ---------------------------------------------------------------------------
# Main auto-clicker engine
# ---------------------------------------------------------------------------

class AutoClicker:
    """
    Runs a click loop in a daemon thread.
    Thread-safe: start/stop/pause can be called from any thread.
    """

    def __init__(
        self,
        config: AutoClickerConfig,
        on_click: Optional[Callable[[ClickTarget, int], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._config = config
        self._on_click = on_click      # callback(target, total_clicks)
        self._on_status = on_status    # callback(status_message)
        self._thread: Optional[threading.Thread] = None
        self._hotkey_thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._pause_evt = threading.Event()
        self._pause_evt.set()          # not paused by default
        self._total_clicks = 0
        self._running = False

    # ------------------------------------------------------------------ control

    def start(self) -> None:
        if self._running:
            return
        if not self._config.targets:
            self._emit_status("❌ No click targets configured.")
            return
        self._stop_evt.clear()
        self._pause_evt.set()
        self._total_clicks = 0
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AutoClicker")
        self._thread.start()
        self._emit_status("✅ Auto-clicker started.")

        if self._config.hotkey_enabled:
            self._hotkey_thread = threading.Thread(
                target=self._hotkey_listener, daemon=True, name="AutoClickerHotkey"
            )
            self._hotkey_thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        self._pause_evt.set()   # unblock if paused
        self._running = False
        self._emit_status("⏹ Auto-clicker stopped.")

    def pause(self) -> None:
        self._pause_evt.clear()
        self._emit_status("⏸ Auto-clicker paused.")

    def resume(self) -> None:
        self._pause_evt.set()
        self._emit_status("▶ Auto-clicker resumed.")

    def toggle(self) -> None:
        if self._running:
            self.stop()
        else:
            self.start()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def total_clicks(self) -> int:
        return self._total_clicks

    # ------------------------------------------------------------------ loop

    def _loop(self) -> None:
        cycles = 0
        repeat = self._config.repeat_count  # 0 = infinite

        while not self._stop_evt.is_set():
            # -- Pause gate --
            self._pause_evt.wait()
            if self._stop_evt.is_set():
                break

            # -- One full cycle through all targets --
            for target in self._config.targets:
                if self._stop_evt.is_set():
                    break
                self._pause_evt.wait()
                if self._stop_evt.is_set():
                    break

                try:
                    _win_click(target.x, target.y)
                    self._total_clicks += 1
                    if self._on_click:
                        self._on_click(target, self._total_clicks)
                except Exception as exc:
                    self._emit_status(f"⚠ Click error at {target}: {exc}")

                # inter-target delay
                delay = self._config.click_delay_ms / 1000.0
                self._stop_evt.wait(timeout=delay)

            cycles += 1

            # -- Repeat check --
            if repeat > 0 and cycles >= repeat:
                self._emit_status(f"✅ Completed {cycles} cycle(s).")
                self._running = False
                break

            # -- Inter-cycle interval --
            self._stop_evt.wait(timeout=self._config.interval_seconds)

        self._running = False

    # ------------------------------------------------------------------ hotkey listener

    def _hotkey_listener(self) -> None:
        """Poll F8 every 100 ms to toggle start/stop."""
        was_pressed = False
        while not self._stop_evt.is_set():
            pressed = _is_key_pressed(VK_F8)
            if pressed and not was_pressed:
                self.toggle()
            was_pressed = pressed
            time.sleep(0.1)

    # ------------------------------------------------------------------ helpers

    def _emit_status(self, msg: str) -> None:
        if self._on_status:
            try:
                self._on_status(msg)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Position picker helper (runs in a background thread)
# ---------------------------------------------------------------------------

class PositionPicker:
    """
    Hold F6 and move the mouse to capture its position.
    The captured coordinate is delivered via `on_capture` callback.
    """

    def __init__(self, on_capture: Callable[[int, int], None]) -> None:
        self._on_capture = on_capture
        self._thread: Optional[threading.Thread] = None
        self._active = False

    def start_listening(self) -> None:
        if self._active:
            return
        self._active = True
        self._thread = threading.Thread(
            target=self._listen, daemon=True, name="PositionPicker"
        )
        self._thread.start()

    def stop_listening(self) -> None:
        self._active = False

    def _listen(self) -> None:
        was_pressed = False
        while self._active:
            pressed = _is_key_pressed(VK_F6)
            if pressed and not was_pressed:
                x, y = _get_cursor_pos()
                try:
                    self._on_capture(x, y)
                except Exception:
                    pass
            was_pressed = pressed
            time.sleep(0.08)
