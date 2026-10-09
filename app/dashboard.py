"""
dashboard.py
Main CustomTkinter desktop application window.
Tabs: Attendance Automation | Auto Clicker | About
All browser automation runs in a background asyncio loop so the UI never freezes.

Branding: Tools and Automation by Rathod
"""

import asyncio
import math
import threading
import time
import tkinter as tk
from tkinter import messagebox
from typing import List, Optional

import customtkinter as ctk

from app.attendance_workflow import (
    AttendanceJob,
    AttendanceResult,
    AttendanceWorkflow,
    WorkflowStatus,
)
from app.browser_manager import BrowserManager
from app.configuration import Configuration
from app.logging_manager import ActivityLogger
from app.page_detection import PageDetector
from app.auto_clicker_panel import AutoClickerPanel


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

COLOURS = {
    "bg":           "#1a1a2e",
    "surface":      "#16213e",
    "card":         "#0f3460",
    "accent":       "#e94560",
    "accent2":      "#0f3460",
    "success":      "#2ecc71",
    "warning":      "#f39c12",
    "error":        "#e74c3c",
    "text":         "#eaeaea",
    "subtext":      "#a0aec0",
    "border":       "#2d3748",
    "button_hover": "#c0392b",
}


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, config: Configuration, logger: ActivityLogger):
        super().__init__(parent)
        self.title("⚙  Settings")
        self.geometry("560x620")
        self.resizable(False, False)
        self.grab_set()
        self._config = config
        self._logger = logger
        self._build()

    def _build(self):
        pad = {"padx": 18, "pady": 6}

        ctk.CTkLabel(self, text="⚙  Settings", font=("Segoe UI", 18, "bold")).pack(pady=(20, 10))

        frame = ctk.CTkScrollableFrame(self, width=520, height=460)
        frame.pack(fill="both", expand=True, padx=16, pady=4)

        def field(label, attr, placeholder=""):
            ctk.CTkLabel(frame, text=label, anchor="w").pack(fill="x", **pad)
            var = ctk.StringVar(value=str(self._config.get(attr, "")))
            entry = ctk.CTkEntry(frame, textvariable=var, placeholder_text=placeholder, width=480)
            entry.pack(fill="x", padx=18, pady=(0, 10))
            return attr, var

        self._fields = {}
        for key, lbl, ph in [
            ("portal_url",           "Portal URL *",           "https://portal.example.gov.in/attendance"),
            ("default_reason",       "Default Reason",         "Network Not Available"),
            ("page_load_timeout",    "Page-Load Timeout (s)",  "30"),
            ("element_wait_timeout", "Element Timeout (s)",    "15"),
            ("max_retries",          "Max Retries",            "3"),
            ("log_file",             "Log File Path",          "logs/activity.log"),
        ]:
            attr, var = field(lbl, key, ph)
            self._fields[attr] = var

        # Browser dropdown
        ctk.CTkLabel(frame, text="Browser", anchor="w").pack(fill="x", **pad)
        self._browser_var = ctk.StringVar(value=self._config.browser)
        ctk.CTkOptionMenu(frame, variable=self._browser_var,
                          values=["chromium", "firefox", "webkit"],
                          width=480).pack(padx=18, pady=(0, 10))

        # Theme
        ctk.CTkLabel(frame, text="Theme", anchor="w").pack(fill="x", **pad)
        self._theme_var = ctk.StringVar(value=self._config.theme)
        ctk.CTkOptionMenu(frame, variable=self._theme_var,
                          values=["dark", "light", "system"],
                          width=480).pack(padx=18, pady=(0, 10))

        # Toggles
        self._require_confirm = ctk.BooleanVar(value=self._config.require_confirmation)
        ctk.CTkCheckBox(frame, text="Require confirmation before each submission",
                        variable=self._require_confirm).pack(anchor="w", padx=18, pady=6)

        self._headless = ctk.BooleanVar(value=self._config.headless)
        ctk.CTkCheckBox(frame, text="Headless mode (browser hidden)",
                        variable=self._headless).pack(anchor="w", padx=18, pady=6)

        # Save / Cancel
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=18, pady=12)
        ctk.CTkButton(btn_frame, text="💾  Save", command=self._save,
                      fg_color=COLOURS["success"], hover_color="#27ae60").pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="✕  Cancel", command=self.destroy,
                      fg_color=COLOURS["error"], hover_color="#c0392b").pack(side="left", padx=6)

    def _save(self):
        updates = {k: v.get() for k, v in self._fields.items()}
        updates["browser"]             = self._browser_var.get()
        updates["theme"]               = self._theme_var.get()
        updates["require_confirmation"] = self._require_confirm.get()
        updates["headless"]            = self._headless.get()
        for key in ("page_load_timeout", "element_wait_timeout", "max_retries"):
            try:
                updates[key] = int(updates[key])
            except ValueError:
                messagebox.showerror("Settings Error", f"'{key}' must be an integer.")
                return
        self._config.update(updates)
        try:
            self._config.save()
            self._logger.info("Settings saved.")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))
            return
        ctk.set_appearance_mode(updates["theme"])
        self.destroy()


# ---------------------------------------------------------------------------
# Main Dashboard Window
# ---------------------------------------------------------------------------

class Dashboard(ctk.CTk):
    def __init__(self, config: Configuration, logger: ActivityLogger):
        super().__init__()

        self._config = config
        self._logger = logger
        self._logger.set_ui_callback(self._append_log)

        self._browser_mgr: Optional[BrowserManager] = None
        self._workflow: Optional[AttendanceWorkflow] = None
        self._asyncio_loop: Optional[asyncio.AbstractEventLoop] = None
        self._bg_thread: Optional[threading.Thread] = None

        # Window setup
        ctk.set_appearance_mode(config.theme)
        ctk.set_default_color_theme("blue")
        self.title("🎓  Smart Attendance Automation System  •  Tools & Automation by Rathod")
        self.geometry("1160x880")
        self.minsize(960, 720)
        self.configure(fg_color=COLOURS["bg"])
        self._hero_tick = 0
        self._pulse_on = True

        self._build_ui()
        self._start_asyncio_loop()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ==========================================================================
    # UI Construction
    # ==========================================================================

    def _build_ui(self):
        self._build_hero_banner()

        # ---- Tab view
        self._tabs = ctk.CTkTabview(
            self, fg_color=COLOURS["surface"],
            segmented_button_fg_color=COLOURS["card"],
            segmented_button_selected_color=COLOURS["accent"],
            segmented_button_selected_hover_color=COLOURS["button_hover"],
            segmented_button_unselected_hover_color=COLOURS["border"],
            text_color=COLOURS["text"],
        )
        self._tabs.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        self._tabs.add("🎓 Attendance")
        self._tabs.add("🖱  Auto Clicker")
        self._tabs.add("ℹ  About")

        self._build_attendance_tab(self._tabs.tab("🎓 Attendance"))
        self._build_autoclicker_tab(self._tabs.tab("🖱  Auto Clicker"))
        self._build_about_tab(self._tabs.tab("ℹ  About"))

    # ==========================================================================
    # Hero Banner
    # ==========================================================================

    def _build_hero_banner(self) -> None:
        """Builds the animated top hero banner with Rathod branding."""

        # Outer hero frame
        hero = tk.Frame(self, bg="#0a0a1a", height=160)
        hero.pack(fill="x")
        hero.pack_propagate(False)

        # Accent top stripe (3 px)
        tk.Frame(hero, bg=COLOURS["accent"], height=3).pack(fill="x")

        # Canvas for gradient + decorations
        self._hero_canvas = tk.Canvas(
            hero, bg="#0a0a1a", highlightthickness=0, height=157
        )
        self._hero_canvas.pack(fill="both", expand=True)
        self._hero_canvas.bind("<Configure>", self._draw_hero_canvas)

        # --- Row 1: Brand badge (left) + Settings button (right)
        top_row = ctk.CTkFrame(self._hero_canvas, fg_color="transparent")
        top_row.place(x=0, y=6, relwidth=1.0)

        badge_frame = ctk.CTkFrame(
            top_row, fg_color="#0f2040",
            border_color="#f5a623", border_width=1, corner_radius=20
        )
        badge_frame.pack(side="left", padx=18, pady=4)
        ctk.CTkLabel(
            badge_frame,
            text="  ⚡  TOOLS AND AUTOMATION BY RATHOD  ⚡  ",
            font=("Segoe UI", 11, "bold"),
            text_color="#f5a623"
        ).pack(padx=6, pady=4)

        # Pulse status dot
        self._pulse_frame = ctk.CTkFrame(
            top_row, fg_color="#0f2040",
            border_color=COLOURS["success"], border_width=1, corner_radius=20
        )
        self._pulse_frame.pack(side="left", padx=8, pady=4)
        self._pulse_dot = ctk.CTkLabel(
            self._pulse_frame,
            text="  🟢  SYSTEM READY  ",
            font=("Segoe UI", 10),
            text_color=COLOURS["success"]
        )
        self._pulse_dot.pack(padx=6, pady=4)

        ctk.CTkButton(
            top_row, text="⚙  Settings", width=110,
            command=self._open_settings,
            fg_color=COLOURS["card"],
            hover_color=COLOURS["border"]
        ).pack(side="right", padx=18, pady=4)

        # --- Row 2: Hero headline
        headline_row = ctk.CTkFrame(self._hero_canvas, fg_color="transparent")
        headline_row.place(x=0, y=46, relwidth=1.0)

        ctk.CTkLabel(
            headline_row,
            text="🎓  Smart Attendance Automation System",
            font=("Segoe UI", 22, "bold"),
            text_color="#ffffff"
        ).pack(side="left", padx=18)

        ctk.CTkLabel(
            headline_row,
            text="Karnataka Dept. of Social Welfare  •  Authorised Portal Tool",
            font=("Segoe UI", 11),
            text_color="#a0aec0"
        ).pack(side="left", padx=6)

        # --- Row 3: Feature pills
        pills_row = ctk.CTkFrame(self._hero_canvas, fg_color="transparent")
        pills_row.place(x=0, y=100, relwidth=1.0)

        pills = [
            ("🌐  Portal Automation",  "#00d4ff",  "#0a2030"),
            ("🖱   Auto Clicker",       "#f5a623",  "#201000"),
            ("📋  Activity Logging",   "#e94560",  "#200010"),
            ("🔒  Secure  •  No Password Storage", "#2ecc71", "#001510"),
            ("⚡  By Rathod",          "#f5a623",  "#201000"),
        ]
        for label, fg, bg in pills:
            pill = ctk.CTkFrame(
                pills_row, fg_color=bg,
                border_color=fg, border_width=1, corner_radius=14
            )
            pill.pack(side="left", padx=6)
            ctk.CTkLabel(
                pill, text=f"  {label}  ",
                font=("Segoe UI", 10, "bold"),
                text_color=fg
            ).pack(padx=4, pady=5)

        # Bottom accent stripe
        tk.Frame(hero, bg="#f5a623", height=2).pack(fill="x", side="bottom")

        # Start pulse animation
        self._animate_pulse()

    def _draw_hero_canvas(self, event=None) -> None:
        """Draw the subtle diagonal gradient lines on the hero canvas."""
        cv = self._hero_canvas
        W = cv.winfo_width()
        H = cv.winfo_height()
        if W < 2:
            return
        cv.delete("grid_line")
        for i in range(0, W + H, 40):
            cv.create_line(i, 0, i - H, H,
                           fill="#0f1830", width=1, tags="grid_line")

    def _animate_pulse(self) -> None:
        """Pulse the status dot colour between green and dim."""
        try:
            if self._pulse_on:
                self._pulse_dot.configure(
                    text="  🟢  SYSTEM READY  ",
                    text_color=COLOURS["success"]
                )
            else:
                self._pulse_dot.configure(
                    text="  ⬤  SYSTEM READY  ",
                    text_color="#1a4030"
                )
            self._pulse_on = not self._pulse_on
            self.after(900, self._animate_pulse)
        except Exception:
            pass

    # ==========================================================================
    # TAB 1: Attendance
    # ==========================================================================

    def _build_attendance_tab(self, tab):
        body = ctk.CTkFrame(tab, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=4, pady=4)

        left = ctk.CTkFrame(body, width=340, fg_color=COLOURS["card"], corner_radius=12)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        right = ctk.CTkFrame(body, fg_color=COLOURS["card"], corner_radius=12)
        right.pack(side="left", fill="both", expand=True)

        self._build_left_panel(left)
        self._build_right_panel(right)

    # ---- Left panel -----------------------------------------------------------

    def _build_left_panel(self, parent):
        ctk.CTkLabel(parent, text="Control Panel",
                     font=("Segoe UI", 14, "bold"),
                     text_color=COLOURS["subtext"]).pack(pady=(16, 6), padx=16, anchor="w")

        self._btn_open   = self._make_btn(parent, "🌐  Open Portal",      self._open_portal,       COLOURS["card"])
        self._btn_start  = self._make_btn(parent, "▶  Start Automation",  self._start_automation,  COLOURS["success"])
        self._btn_pause  = self._make_btn(parent, "⏸  Pause",             self._pause,             COLOURS["warning"])
        self._btn_resume = self._make_btn(parent, "▶  Resume",            self._resume,            COLOURS["card"])
        self._btn_stop   = self._make_btn(parent, "⏹  Stop",              self._stop,              COLOURS["error"])

        self._btn_pause.configure(state="disabled")
        self._btn_resume.configure(state="disabled")
        self._btn_stop.configure(state="disabled")

        ctk.CTkFrame(parent, height=2, fg_color=COLOURS["border"]).pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(parent, text="Attendance Details",
                     font=("Segoe UI", 13, "bold"),
                     text_color=COLOURS["subtext"]).pack(pady=(0, 6), padx=16, anchor="w")

        ctk.CTkLabel(parent, text="Date", anchor="w", text_color=COLOURS["subtext"]).pack(fill="x", padx=16)
        self._date_var = ctk.StringVar()
        ctk.CTkEntry(parent, textvariable=self._date_var,
                     placeholder_text="DD/MM/YYYY").pack(fill="x", padx=16, pady=(2, 8))

        ctk.CTkLabel(parent, text="Student", anchor="w", text_color=COLOURS["subtext"]).pack(fill="x", padx=16)
        self._student_var = ctk.StringVar()
        ctk.CTkEntry(parent, textvariable=self._student_var,
                     placeholder_text="Student name or ID").pack(fill="x", padx=16, pady=(2, 4))
        ctk.CTkButton(parent, text="🔄 Load from Portal", height=28,
                      command=self._load_students_from_portal,
                      fg_color=COLOURS["card"], hover_color=COLOURS["border"]
                      ).pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(parent, text="Student List (one per line)",
                     anchor="w", text_color=COLOURS["subtext"]).pack(fill="x", padx=16)
        self._student_list_box = ctk.CTkTextbox(parent, height=80)
        self._student_list_box.pack(fill="x", padx=16, pady=(2, 8))

        ctk.CTkLabel(parent, text="Reason", anchor="w", text_color=COLOURS["subtext"]).pack(fill="x", padx=16)
        self._reason_var = ctk.StringVar(value=self._config.default_reason)
        self._reason_menu = ctk.CTkOptionMenu(
            parent, variable=self._reason_var,
            values=[
                self._config.default_reason or "-- Load portal first --",
                "Network Not Available",
                "No Power",
                "System Was Down",
                "Thumb Not Detected",
                "Software Not Working Due to Configuration Problem",
            ]
        )
        self._reason_menu.pack(fill="x", padx=16, pady=(2, 8))

        ctk.CTkFrame(parent, height=2, fg_color=COLOURS["border"]).pack(fill="x", padx=16, pady=10)
        self._lbl_success = self._stat_card(parent, "✅ Success",        "0", COLOURS["success"])
        self._lbl_already  = self._stat_card(parent, "🔁 Already Marked", "0", COLOURS["warning"])
        self._lbl_failed   = self._stat_card(parent, "❌ Failed",         "0", COLOURS["error"])

    # ---- Right panel -----------------------------------------------------------

    def _build_right_panel(self, parent):
        status_frame = ctk.CTkFrame(parent, fg_color=COLOURS["surface"], corner_radius=8)
        status_frame.pack(fill="x", padx=14, pady=(14, 4))
        ctk.CTkLabel(status_frame, text="Current Operation:",
                     font=("Segoe UI", 11), text_color=COLOURS["subtext"]).pack(side="left", padx=10)
        self._lbl_operation = ctk.CTkLabel(
            status_frame, text="Idle", font=("Segoe UI", 11, "bold"),
            text_color=COLOURS["text"])
        self._lbl_operation.pack(side="left", padx=4)

        self._progress_var = ctk.DoubleVar(value=0.0)
        self._progress_bar = ctk.CTkProgressBar(parent, variable=self._progress_var,
                                                  height=8, corner_radius=4)
        self._progress_bar.pack(fill="x", padx=14, pady=(4, 8))
        self._progress_bar.set(0)

        log_label = ctk.CTkFrame(parent, fg_color="transparent")
        log_label.pack(fill="x", padx=14)
        ctk.CTkLabel(log_label, text="📋  Activity Log",
                     font=("Segoe UI", 13, "bold")).pack(side="left")
        ctk.CTkButton(log_label, text="🗑 Clear", width=70, height=24,
                      command=self._clear_log,
                      fg_color=COLOURS["border"], hover_color=COLOURS["card"]
                      ).pack(side="right")

        self._log_box = ctk.CTkTextbox(parent, font=("Consolas", 11), wrap="word")
        self._log_box.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        self._log_box.configure(state="disabled")

    # ==========================================================================
    # TAB 2: Auto Clicker
    # ==========================================================================

    def _build_autoclicker_tab(self, tab):
        self._ac_panel = AutoClickerPanel(tab, logger=self._logger)
        self._ac_panel.pack(fill="both", expand=True)

    # ==========================================================================
    # TAB 3: About
    # ==========================================================================

    def _build_about_tab(self, tab):
        frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(frame, text="🎓  Smart Attendance Automation System",
                     font=("Segoe UI", 20, "bold"),
                     text_color=COLOURS["accent"]).pack(pady=(10, 4))
        ctk.CTkLabel(frame, text="Version 1.0  •  Python + Playwright + CustomTkinter",
                     font=("Segoe UI", 12), text_color=COLOURS["subtext"]).pack(pady=(0, 20))

        sections = [
            ("🎯 Attendance Tab", (
                "Automates manual attendance entry on the Karnataka Social Welfare portal.\n"
                "1. Click 'Open Portal' → log in manually.\n"
                "2. Select date, student(s) and reason.\n"
                "3. Click 'Start Automation'.\n"
                "4. Confirm each submission in the popup dialog.\n"
                "Results: ✅ Success  •  🔁 Already Marked  •  ❌ Failed"
            )),
            ("🖱  Auto Clicker Tab", (
                "Screen-coordinate auto-clicker with full control:\n\n"
                "• Add Targets manually (X, Y) or use the Position Picker.\n"
                "• Position Picker: Click 'Start Picking', move mouse, press F6 to capture.\n"
                "• Set Interval (seconds between cycles) and Click Delay (ms between targets).\n"
                "• Set Repeat Count (0 = run forever).\n"
                "• F8 hotkey starts/stops the clicker from anywhere on screen.\n"
                "• Pause and Resume without losing your progress."
            )),
            ("⚠  Important Notice", (
                "This tool is for authorised Karnataka Dept. of Social Welfare staff only.\n"
                "Never store portal passwords or session tokens.\n"
                "Always select the truthful attendance reason.\n"
                "Verify page selectors in app/page_detection.py against the real portal DOM."
            )),
        ]

        for title, body in sections:
            ctk.CTkLabel(frame, text=title,
                         font=("Segoe UI", 14, "bold"),
                         text_color=COLOURS["warning"]).pack(anchor="w", pady=(14, 2))
            ctk.CTkLabel(frame, text=body, font=("Segoe UI", 11),
                         text_color=COLOURS["text"],
                         justify="left", anchor="w",
                         wraplength=700).pack(anchor="w", padx=16)

    # ==========================================================================
    # Shared helpers
    # ==========================================================================

    def _make_btn(self, parent, text, command, color):
        btn = ctk.CTkButton(
            parent, text=text, command=command,
            fg_color=color, hover_color=self._darken(color),
            font=("Segoe UI", 12, "bold"), height=38, corner_radius=8
        )
        btn.pack(fill="x", padx=16, pady=4)
        return btn

    def _stat_card(self, parent, label, value, color):
        frame = ctk.CTkFrame(parent, fg_color=COLOURS["surface"], corner_radius=8)
        frame.pack(fill="x", padx=16, pady=3)
        ctk.CTkLabel(frame, text=label, font=("Segoe UI", 10),
                     text_color=COLOURS["subtext"]).pack(side="left", padx=10)
        lbl = ctk.CTkLabel(frame, text=value, font=("Segoe UI", 13, "bold"),
                           text_color=color)
        lbl.pack(side="right", padx=10)
        return lbl

    @staticmethod
    def _darken(hex_color: str) -> str:
        try:
            r = max(0, int(hex_color[1:3], 16) - 30)
            g = max(0, int(hex_color[3:5], 16) - 30)
            b = max(0, int(hex_color[5:7], 16) - 30)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    # ==========================================================================
    # Asyncio background loop
    # ==========================================================================

    def _start_asyncio_loop(self):
        self._asyncio_loop = asyncio.new_event_loop()
        self._bg_thread = threading.Thread(
            target=self._asyncio_loop.run_forever, daemon=True
        )
        self._bg_thread.start()

    def _run_async(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._asyncio_loop)

    # ==========================================================================
    # Attendance button handlers
    # ==========================================================================

    def _open_portal(self):
        url = self._config.portal_url.strip()
        if not url:
            messagebox.showerror(
                "No URL configured",
                "Please open Settings and enter the portal URL before proceeding."
            )
            return
        self._browser_mgr = BrowserManager(self._logger)
        self._run_async(self._async_open_portal(url))
        self._btn_open.configure(state="disabled")

    async def _async_open_portal(self, url: str):
        try:
            page = await self._browser_mgr.launch(
                browser_name=self._config.browser,
                headless=self._config.headless,
                page_load_timeout=self._config.page_load_timeout,
            )
            await self._browser_mgr.navigate(url, timeout=self._config.page_load_timeout)
            self.after(0, lambda: self._btn_open.configure(state="normal"))
            detector = PageDetector(self._logger)
            form_found = await detector.wait_for_attendance_form(
                page, timeout=self._config.element_wait_timeout
            )
            if form_found:
                reasons = await detector.get_reason_options(page)
                if reasons:
                    self.after(0, lambda r=reasons: self._update_reason_menu(r))
                students = await detector.get_student_options(page)
                if students:
                    self.after(0, lambda s=students: self._update_student_hint(s))
        except Exception as exc:
            self._logger.error(f"Portal open failed: {exc}")
            self.after(0, lambda: self._btn_open.configure(state="normal"))

    def _start_automation(self):
        errors = self._config.validate()
        if errors:
            messagebox.showerror("Configuration Error", "\n".join(errors))
            return
        if self._browser_mgr is None or self._browser_mgr.page is None:
            messagebox.showerror(
                "Browser Not Open",
                "Click 'Open Portal' first and log in before starting automation."
            )
            return
        jobs = self._build_jobs()
        if not jobs:
            messagebox.showerror("No Jobs", "Please enter at least one student name and a date.")
            return
        if not self._reason_var.get().strip():
            messagebox.showerror("No Reason", "Please select an attendance reason before starting.")
            return

        self._btn_start.configure(state="disabled")
        self._btn_pause.configure(state="normal")
        self._btn_stop.configure(state="normal")
        self._btn_resume.configure(state="disabled")

        self._workflow = AttendanceWorkflow(
            page=self._browser_mgr.page,
            config=self._config,
            logger=self._logger,
            status_callback=self._on_status_update,
            confirm_callback=self._show_confirmation_dialog,
        )
        self._run_async(self._async_run_jobs(jobs))

    async def _async_run_jobs(self, jobs):
        try:
            await self._workflow.run_jobs(jobs)
        except Exception as exc:
            self._logger.error(f"Automation error: {exc}")
        finally:
            self.after(0, self._on_automation_done)

    def _pause(self):
        if self._workflow:
            self._workflow.pause()
            self._btn_pause.configure(state="disabled")
            self._btn_resume.configure(state="normal")

    def _resume(self):
        if self._workflow:
            self._workflow.resume()
            self._btn_pause.configure(state="normal")
            self._btn_resume.configure(state="disabled")

    def _stop(self):
        if self._workflow:
            self._workflow.stop()

    def _open_settings(self):
        SettingsDialog(self, self._config, self._logger)

    def _load_students_from_portal(self):
        if self._browser_mgr is None or self._browser_mgr.page is None:
            messagebox.showinfo("Portal Not Open", "Open the portal first.")
            return
        self._run_async(self._async_load_students())

    async def _async_load_students(self):
        detector = PageDetector(self._logger)
        students = await detector.get_student_options(self._browser_mgr.page)
        if students:
            self.after(0, lambda s=students: self._update_student_hint(s))
        else:
            self.after(0, lambda: messagebox.showinfo(
                "No Students Found",
                "Could not read student dropdown from the portal.\n"
                "Make sure the form is loaded and you are logged in."
            ))

    # ==========================================================================
    # Job building
    # ==========================================================================

    def _build_jobs(self) -> List[AttendanceJob]:
        date   = self._date_var.get().strip()
        reason = self._reason_var.get().strip()
        multi_text = self._student_list_box.get("1.0", "end").strip()
        students = [s.strip() for s in multi_text.splitlines() if s.strip()]
        if not students:
            single = self._student_var.get().strip()
            if single:
                students = [single]
        return [AttendanceJob(date=date, student=s, reason=reason) for s in students]

    # ==========================================================================
    # Status / UI callbacks
    # ==========================================================================

    def _on_status_update(self, status: WorkflowStatus):
        self.after(0, lambda s=status: self._apply_status(s))

    def _apply_status(self, status: WorkflowStatus):
        self._lbl_operation.configure(text=status.current_operation or "Running…")
        self._progress_bar.set(status.progress)
        self._lbl_success.configure(text=str(status.success_count))
        self._lbl_already.configure(text=str(status.already_marked_count))
        self._lbl_failed.configure(text=str(status.failed_count))

    def _on_automation_done(self):
        self._lbl_operation.configure(text="Finished")
        self._btn_start.configure(state="normal")
        self._btn_pause.configure(state="disabled")
        self._btn_resume.configure(state="disabled")
        self._btn_stop.configure(state="disabled")
        self._logger.info("Automation session complete.")

    def _append_log(self, message: str, level: str):
        colour_map = {
            "SUCCESS": COLOURS["success"],
            "ERROR":   COLOURS["error"],
            "WARNING": COLOURS["warning"],
            "INFO":    COLOURS["text"],
            "DEBUG":   COLOURS["subtext"],
        }
        colour = colour_map.get(level, COLOURS["text"])
        self._log_box.configure(state="normal")
        self._log_box.insert("end", message + "\n")
        self._log_box.tag_config(level, foreground=colour)
        start = self._log_box.index(f"end-{len(message)+2}c")
        end   = self._log_box.index("end-1c")
        self._log_box.tag_add(level, start, end)
        self._log_box.configure(state="disabled")
        self._log_box.see("end")

    def _update_reason_menu(self, reasons: List[str]):
        clean = [r for r in reasons if r and r.lower() not in ("select", "-- select --", "")]
        if clean:
            self._reason_menu.configure(values=clean)
            if not self._reason_var.get() or self._reason_var.get() not in clean:
                self._reason_var.set(clean[0])
            self._logger.info(f"Reason dropdown loaded: {clean}")

    def _update_student_hint(self, students: List[str]):
        clean = [s for s in students if s and s.lower() not in ("select", "-- select --", "")]
        if clean:
            self._logger.info(f"Student list loaded: {len(clean)} students found.")
            current = self._student_list_box.get("1.0", "end").strip()
            if not current:
                self._student_list_box.delete("1.0", "end")
                self._student_list_box.insert("end", "\n".join(clean[:20]))

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    # ==========================================================================
    # Confirmation dialog
    # ==========================================================================

    def _show_confirmation_dialog(self, job: AttendanceJob) -> bool:
        event = threading.Event()
        result = [False]

        def _ask():
            ok = messagebox.askyesno(
                "Confirm Attendance Submission",
                f"About to mark attendance:\n\n"
                f"  Date:    {job.date}\n"
                f"  Student: {job.student}\n"
                f"  Reason:  {job.reason}\n\n"
                f"Do you want to proceed?",
            )
            result[0] = ok
            event.set()

        self.after(0, _ask)
        event.wait(timeout=120)
        return result[0]

    # ==========================================================================
    # Lifecycle
    # ==========================================================================

    def _on_close(self):
        if self._workflow:
            self._workflow.stop()
        # Stop any running auto-clicker
        if hasattr(self, "_ac_panel") and self._ac_panel._clicker:
            self._ac_panel._clicker.stop()
        if hasattr(self, "_ac_panel") and self._ac_panel._picker:
            self._ac_panel._picker.stop_listening()
        if self._browser_mgr:
            self._run_async(self._browser_mgr.close())
        if self._asyncio_loop:
            self._asyncio_loop.call_soon_threadsafe(self._asyncio_loop.stop)
        self.destroy()
