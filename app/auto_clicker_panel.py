"""
auto_clicker_panel.py
CustomTkinter panel for the Auto-Clicker feature.
Embedded as a tab inside the main Dashboard.
"""

import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import Callable, List, Optional

import customtkinter as ctk

from app.auto_clicker import AutoClicker, AutoClickerConfig, ClickTarget, PositionPicker
from app.logging_manager import ActivityLogger


# Colour palette (mirrors dashboard.py)
C = {
    "bg":       "#1a1a2e",
    "surface":  "#16213e",
    "card":     "#0f3460",
    "accent":   "#e94560",
    "success":  "#2ecc71",
    "warning":  "#f39c12",
    "error":    "#e74c3c",
    "text":     "#eaeaea",
    "subtext":  "#a0aec0",
    "border":   "#2d3748",
}


class AutoClickerPanel(ctk.CTkFrame):
    """
    Full-featured auto-clicker UI embedded in a tab.

    Layout
    ──────
    Left  : target list + add/remove controls + position picker
    Right : settings (interval, delay, repeats, hotkey) + live stats + log
    """

    def __init__(self, parent, logger: ActivityLogger, **kwargs):
        super().__init__(parent, fg_color=C["surface"], **kwargs)
        self._logger = logger
        self._clicker: Optional[AutoClicker] = None
        self._picker: Optional[PositionPicker] = None
        self._picking = False
        self._targets: List[ClickTarget] = []
        self._click_count = 0

        self._build()

    # ==========================================================================
    # UI Construction
    # ==========================================================================

    def _build(self):
        # Two-column layout
        left = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=12)
        left.pack(side="left", fill="y", padx=(12, 6), pady=12)
        left.pack_propagate(False)
        left.configure(width=320)

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=12)

        self._build_left(left)
        self._build_right(right)

    # ---- Left: target list ------------------------------------------------

    def _build_left(self, parent):
        ctk.CTkLabel(parent, text="🖱  Click Targets",
                     font=("Segoe UI", 14, "bold"),
                     text_color=C["text"]).pack(pady=(14, 6), padx=14, anchor="w")

        # Scrollable target list
        list_frame = ctk.CTkScrollableFrame(parent, height=220, fg_color=C["surface"],
                                            corner_radius=8)
        list_frame.pack(fill="x", padx=12, pady=(0, 8))
        self._list_frame = list_frame
        self._target_rows: list = []

        # Manual coordinate entry
        coords_frame = ctk.CTkFrame(parent, fg_color="transparent")
        coords_frame.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkLabel(coords_frame, text="X:", text_color=C["subtext"], width=20).pack(side="left")
        self._x_var = ctk.StringVar(value="0")
        ctk.CTkEntry(coords_frame, textvariable=self._x_var, width=70).pack(side="left", padx=(2, 8))

        ctk.CTkLabel(coords_frame, text="Y:", text_color=C["subtext"], width=20).pack(side="left")
        self._y_var = ctk.StringVar(value="0")
        ctk.CTkEntry(coords_frame, textvariable=self._y_var, width=70).pack(side="left", padx=(2, 8))

        ctk.CTkLabel(coords_frame, text="Label:", text_color=C["subtext"]).pack(side="left")
        self._label_var = ctk.StringVar()
        ctk.CTkEntry(coords_frame, textvariable=self._label_var,
                     placeholder_text="optional", width=80).pack(side="left", padx=4)

        # Add / Remove buttons
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkButton(btn_row, text="➕ Add Target", command=self._add_manual,
                      fg_color=C["success"], hover_color="#27ae60",
                      height=32).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="🗑 Remove Last", command=self._remove_last,
                      fg_color=C["error"], hover_color="#c0392b",
                      height=32).pack(side="left")

        # Divider
        ctk.CTkFrame(parent, height=2, fg_color=C["border"]).pack(fill="x", padx=12, pady=8)

        # Position picker
        ctk.CTkLabel(parent, text="📍 Position Picker",
                     font=("Segoe UI", 13, "bold"),
                     text_color=C["text"]).pack(anchor="w", padx=14, pady=(0, 4))

        ctk.CTkLabel(parent,
                     text="Move mouse to location, then press F6\nto capture the coordinate.",
                     text_color=C["subtext"], font=("Segoe UI", 11),
                     justify="left").pack(anchor="w", padx=14, pady=(0, 6))

        self._live_pos_var = ctk.StringVar(value="Mouse: ( — , — )")
        ctk.CTkLabel(parent, textvariable=self._live_pos_var,
                     font=("Consolas", 12), text_color=C["warning"]).pack(anchor="w", padx=14)

        self._btn_pick = ctk.CTkButton(
            parent, text="🔴 Start Picking (F6)",
            command=self._toggle_picker,
            fg_color=C["warning"], hover_color="#e67e22", height=36)
        self._btn_pick.pack(fill="x", padx=12, pady=(6, 4))

        # Divider
        ctk.CTkFrame(parent, height=2, fg_color=C["border"]).pack(fill="x", padx=12, pady=8)

        # Live click counter
        self._lbl_count = ctk.CTkLabel(parent, text="Clicks: 0",
                                        font=("Segoe UI", 18, "bold"),
                                        text_color=C["success"])
        self._lbl_count.pack(anchor="center", pady=4)

        self._lbl_status = ctk.CTkLabel(parent, text="Idle",
                                         font=("Segoe UI", 11),
                                         text_color=C["subtext"])
        self._lbl_status.pack(anchor="center")

    # ---- Right: settings + controls + log ---------------------------------

    def _build_right(self, parent):
        # Settings card
        settings = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12)
        settings.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(settings, text="⚙  Clicker Settings",
                     font=("Segoe UI", 13, "bold"),
                     text_color=C["text"]).pack(anchor="w", padx=16, pady=(12, 6))

        grid = ctk.CTkFrame(settings, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(0, 12))
        grid.columnconfigure((0, 2), weight=0)
        grid.columnconfigure((1, 3), weight=1)

        def setting_field(row, col, label, var, tip=""):
            ctk.CTkLabel(grid, text=label, text_color=C["subtext"],
                         anchor="w").grid(row=row, column=col*2, padx=(0, 6), pady=4, sticky="w")
            e = ctk.CTkEntry(grid, textvariable=var, width=100)
            e.grid(row=row, column=col*2+1, padx=(0, 20), pady=4, sticky="w")
            return e

        self._interval_var    = ctk.StringVar(value="1.0")
        self._delay_var       = ctk.StringVar(value="100")
        self._repeat_var      = ctk.StringVar(value="0")

        setting_field(0, 0, "Interval (sec):",    self._interval_var)
        setting_field(0, 1, "Click Delay (ms):",  self._delay_var)
        setting_field(1, 0, "Repeat Count:",       self._repeat_var)

        ctk.CTkLabel(grid, text="(0 = infinite)",
                     text_color=C["subtext"], font=("Segoe UI", 10)
                     ).grid(row=1, column=3, sticky="w", pady=4)

        self._hotkey_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(settings, text="Enable F8 hotkey (start/stop from anywhere)",
                        variable=self._hotkey_var,
                        text_color=C["text"]).pack(anchor="w", padx=16, pady=(0, 12))

        # Main control buttons
        ctrl = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12)
        ctrl.pack(fill="x", pady=(0, 8))

        btn_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=12)

        self._btn_start = ctk.CTkButton(
            btn_row, text="▶  Start Auto-Clicker",
            command=self._start,
            fg_color=C["success"], hover_color="#27ae60",
            font=("Segoe UI", 13, "bold"), height=40)
        self._btn_start.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._btn_pause_ac = ctk.CTkButton(
            btn_row, text="⏸  Pause",
            command=self._pause_clicker,
            fg_color=C["warning"], hover_color="#e67e22",
            height=40, state="disabled")
        self._btn_pause_ac.pack(side="left", padx=(0, 6))

        self._btn_stop = ctk.CTkButton(
            btn_row, text="⏹  Stop",
            command=self._stop,
            fg_color=C["error"], hover_color="#c0392b",
            height=40, state="disabled")
        self._btn_stop.pack(side="left")

        # Info strip
        info = ctk.CTkFrame(ctrl, fg_color=C["surface"], corner_radius=6)
        info.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkLabel(
            info,
            text="  ℹ  F6 = capture position   •   F8 = toggle start/stop   "
                 "•   Interval: pause between cycles   •   Delay: pause between targets  ",
            font=("Segoe UI", 10), text_color=C["subtext"]
        ).pack(padx=6, pady=4)

        # Activity log
        log_hdr = ctk.CTkFrame(parent, fg_color="transparent")
        log_hdr.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(log_hdr, text="📋  Auto-Clicker Log",
                     font=("Segoe UI", 13, "bold")).pack(side="left")
        ctk.CTkButton(log_hdr, text="🗑 Clear", width=70, height=24,
                      command=self._clear_log,
                      fg_color=C["border"], hover_color=C["card"]).pack(side="right")

        self._log = ctk.CTkTextbox(parent, font=("Consolas", 10), wrap="word")
        self._log.pack(fill="both", expand=True)
        self._log.configure(state="disabled")

    # ==========================================================================
    # Target management
    # ==========================================================================

    def _add_manual(self):
        try:
            x = int(self._x_var.get())
            y = int(self._y_var.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "X and Y must be whole numbers.")
            return
        label = self._label_var.get().strip()
        self._add_target(ClickTarget(x=x, y=y, label=label))

    def _add_target(self, target: ClickTarget):
        self._targets.append(target)
        idx = len(self._targets)
        row = ctk.CTkFrame(self._list_frame, fg_color=C["surface"], corner_radius=6)
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text=f"  #{idx}  {target}",
                     font=("Consolas", 11), text_color=C["text"],
                     anchor="w").pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkButton(row, text="✕", width=28, height=24,
                      fg_color=C["error"], hover_color="#c0392b",
                      command=lambda t=target, r=row: self._remove_specific(t, r)
                      ).pack(side="right", padx=4, pady=2)
        self._target_rows.append(row)
        self._log_msg(f"Target added: {target}")

    def _remove_last(self):
        if not self._targets:
            return
        self._targets.pop()
        row = self._target_rows.pop()
        row.destroy()
        self._log_msg("Last target removed.")

    def _remove_specific(self, target: ClickTarget, row):
        if target in self._targets:
            self._targets.remove(target)
        if row in self._target_rows:
            self._target_rows.remove(row)
        row.destroy()
        self._log_msg(f"Target removed: {target}")

    # ==========================================================================
    # Position picker
    # ==========================================================================

    def _toggle_picker(self):
        if self._picking:
            self._stop_picker()
        else:
            self._start_picker()

    def _start_picker(self):
        self._picking = True
        self._btn_pick.configure(text="🟢 Picking… (F6 to capture, click here to stop)",
                                 fg_color=C["success"])
        self._picker = PositionPicker(on_capture=self._on_position_captured)
        self._picker.start_listening()
        # Start live mouse-position display
        self._update_live_pos()
        self._log_msg("Position picker started. Move mouse and press F6 to capture.")

    def _stop_picker(self):
        self._picking = False
        if self._picker:
            self._picker.stop_listening()
        self._btn_pick.configure(text="🔴 Start Picking (F6)", fg_color=C["warning"])
        self._live_pos_var.set("Mouse: ( — , — )")
        self._log_msg("Position picker stopped.")

    def _update_live_pos(self):
        if not self._picking:
            return
        try:
            from app.auto_clicker import _get_cursor_pos
            x, y = _get_cursor_pos()
            self._live_pos_var.set(f"Mouse: ( {x} , {y} )")
        except Exception:
            pass
        self.after(80, self._update_live_pos)

    def _on_position_captured(self, x: int, y: int):
        """Called from the picker background thread when F6 is pressed."""
        label = f"Pick-{len(self._targets)+1}"
        target = ClickTarget(x=x, y=y, label=label)
        # Update UI from main thread
        self.after(0, lambda t=target: self._add_target(t))
        self.after(0, lambda: self._x_var.set(str(x)))
        self.after(0, lambda: self._y_var.set(str(y)))
        self.after(0, lambda: self._log_msg(
            f"📍 Position captured: ({x}, {y})"
        ))

    # ==========================================================================
    # Clicker controls
    # ==========================================================================

    def _start(self):
        if not self._targets:
            messagebox.showerror("No Targets", "Add at least one click target before starting.")
            return
        try:
            interval  = float(self._interval_var.get())
            delay_ms  = int(self._delay_var.get())
            repeats   = int(self._repeat_var.get())
        except ValueError:
            messagebox.showerror("Invalid Settings", "Interval, delay, and repeat must be numbers.")
            return

        if interval <= 0:
            messagebox.showerror("Invalid Interval", "Interval must be greater than 0.")
            return

        cfg = AutoClickerConfig(
            targets=list(self._targets),
            interval_seconds=interval,
            click_delay_ms=delay_ms,
            repeat_count=repeats,
            hotkey_enabled=self._hotkey_var.get(),
        )
        self._click_count = 0
        self._clicker = AutoClicker(
            config=cfg,
            on_click=self._on_click_done,
            on_status=self._on_clicker_status,
        )
        self._clicker.start()
        self._btn_start.configure(state="disabled")
        self._btn_pause_ac.configure(state="normal")
        self._btn_stop.configure(state="normal")

    def _pause_clicker(self):
        if self._clicker:
            if self._btn_pause_ac.cget("text").startswith("⏸"):
                self._clicker.pause()
                self._btn_pause_ac.configure(text="▶  Resume")
            else:
                self._clicker.resume()
                self._btn_pause_ac.configure(text="⏸  Pause")

    def _stop(self):
        if self._clicker:
            self._clicker.stop()
        self._btn_start.configure(state="normal")
        self._btn_pause_ac.configure(text="⏸  Pause", state="disabled")
        self._btn_stop.configure(state="disabled")

    # ==========================================================================
    # Callbacks from AutoClicker thread
    # ==========================================================================

    def _on_click_done(self, target: ClickTarget, total: int):
        self.after(0, lambda: self._lbl_count.configure(text=f"Clicks: {total}"))
        self.after(0, lambda: self._log_msg(
            f"✅ Click #{total} → {target}"
        ))

    def _on_clicker_status(self, msg: str):
        self.after(0, lambda: self._lbl_status.configure(text=msg))
        self.after(0, lambda: self._log_msg(msg))
        # If clicker reports it finished, re-enable start button
        if any(word in msg for word in ("stopped", "Completed")):
            self.after(0, lambda: self._btn_start.configure(state="normal"))
            self.after(0, lambda: self._btn_pause_ac.configure(state="disabled"))
            self.after(0, lambda: self._btn_stop.configure(state="disabled"))

    # ==========================================================================
    # Log helpers
    # ==========================================================================

    def _log_msg(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self._log.configure(state="normal")
        self._log.insert("end", line)
        self._log.configure(state="disabled")
        self._log.see("end")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
