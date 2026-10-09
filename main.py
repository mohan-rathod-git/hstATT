"""
main.py — Entry point for the Smart Attendance Automation System.
Shows the animated splash screen first, then launches the dashboard.

Branding: Tools and Automation by Rathod
"""

import sys
import os
import tkinter as tk

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from app.configuration import Configuration, ConfigError
from app.logging_manager import ActivityLogger


def main():
    # ---- Load config
    try:
        config = Configuration()
    except ConfigError as exc:
        import tkinter.messagebox as mb
        root = tk.Tk()
        root.withdraw()
        mb.showerror("Configuration Error", str(exc))
        sys.exit(1)

    logger = ActivityLogger(log_file=config.log_file)
    logger.info("Smart Attendance Automation System starting…")
    logger.info("Tools and Automation by Rathod")

    # ---- Root window (hidden — only used as Tk master)
    root = tk.Tk()
    root.withdraw()

    # ---- Show splash, launch dashboard after it closes
    def launch_dashboard():
        root.destroy()   # kill the hidden root

        import customtkinter as ctk
        from app.dashboard import Dashboard

        app = Dashboard(config=config, logger=logger)
        app.mainloop()

    from app.splash_screen import SplashScreen
    SplashScreen(root, on_done=launch_dashboard)
    root.mainloop()


if __name__ == "__main__":
    main()
