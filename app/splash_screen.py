"""
splash_screen.py
Animated welcome / splash screen shown on startup.
"Tools and Automation by Rathod"
Auto-dismisses after 3.5 seconds or on click.
"""

import threading
import time
import math
import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BG        = "#0a0a1a"
ACCENT    = "#e94560"
GOLD      = "#f5a623"
CYAN      = "#00d4ff"
WHITE     = "#ffffff"
DIM_WHITE = "#c0c8d8"
CARD      = "#0f2040"


class SplashScreen(tk.Toplevel):
    """
    Full-screen-ish animated splash window.
    Calls `on_done()` when it closes so main.py can launch the dashboard.
    """

    _WIDTH  = 700
    _HEIGHT = 440

    def __init__(self, root: tk.Tk, on_done: Callable[[], None]) -> None:
        super().__init__(root)
        self._on_done = on_done
        self._tick   = 0
        self._closed = False

        # ---- Window chrome
        self.overrideredirect(True)           # borderless
        self.attributes("-topmost", True)
        self.configure(bg=BG)
        self.resizable(False, False)
        self._center()

        # ---- Canvas for everything
        self._cv = tk.Canvas(
            self, width=self._WIDTH, height=self._HEIGHT,
            bg=BG, highlightthickness=0
        )
        self._cv.pack(fill="both", expand=True)

        # Click anywhere to close
        self._cv.bind("<Button-1>", lambda _: self._close())

        # ---- Draw static elements
        self._draw_background()
        self._draw_hero()

        # ---- Animated items (IDs stored for update)
        self._ring_ids:   list = []
        self._progress_id: Optional[int] = None
        self._glow_id:    Optional[int] = None

        self._create_animated_rings()
        self._create_progress_bar()

        # ---- Start animation + auto-close timer
        self._animate()
        threading.Timer(3.5, self._close).start()

    # ==========================================================================
    # Layout helpers
    # ==========================================================================

    def _center(self) -> None:
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - self._WIDTH)  // 2
        y  = (sh - self._HEIGHT) // 2
        self.geometry(f"{self._WIDTH}x{self._HEIGHT}+{x}+{y}")

    def _draw_background(self) -> None:
        cv = self._cv
        W, H = self._WIDTH, self._HEIGHT

        # Gradient-effect bands (canvas rectangles)
        steps = 24
        for i in range(steps):
            ratio = i / steps
            # deep blue → dark navy
            r = int(10  + ratio * 8)
            g = int(10  + ratio * 16)
            b = int(26  + ratio * 40)
            col = f"#{r:02x}{g:02x}{b:02x}"
            y0  = int(H * ratio)
            y1  = int(H * (ratio + 1/steps)) + 1
            cv.create_rectangle(0, y0, W, y1, fill=col, outline="")

        # Top accent line
        cv.create_rectangle(0, 0, W, 4, fill=ACCENT, outline="")
        # Bottom accent line
        cv.create_rectangle(0, H - 4, W, H, fill=ACCENT, outline="")
        # Left stripe
        cv.create_rectangle(0, 0, 4, H, fill=GOLD, outline="")
        # Right stripe
        cv.create_rectangle(W - 4, 0, W, H, fill=CYAN, outline="")

        # Decorative dots grid (subtle)
        for row in range(0, H, 30):
            for col in range(0, W, 30):
                cv.create_oval(col-1, row-1, col+1, row+1, fill="#1a2040", outline="")

    def _draw_hero(self) -> None:
        cv = self._cv
        W, H = self._WIDTH, self._HEIGHT
        cx   = W // 2

        # ---- Badge / pill behind brand name
        cv.create_rectangle(cx - 200, 34, cx + 200, 78,
                             fill=CARD, outline=ACCENT, width=1)
        cv.create_text(cx, 56, text="⚡  TOOLS AND AUTOMATION BY RATHOD  ⚡",
                       fill=GOLD, font=("Segoe UI", 11, "bold"), anchor="center")

        # ---- Hero headline
        cv.create_text(cx, 148,
                       text="Smart Attendance",
                       fill=WHITE, font=("Segoe UI", 34, "bold"), anchor="center")
        cv.create_text(cx, 195,
                       text="Automation System",
                       fill=ACCENT, font=("Segoe UI", 28, "bold"), anchor="center")

        # ---- Sub-headline
        cv.create_text(cx, 240,
                       text="Karnataka Dept. of Social Welfare  •  Authorised Tool",
                       fill=DIM_WHITE, font=("Segoe UI", 11), anchor="center")

        # ---- Feature pills
        pills = [
            ("🌐 Portal Automation", CYAN),
            ("🖱  Auto Clicker",     GOLD),
            ("📋 Activity Logging",  ACCENT),
        ]
        pill_y = 278
        total_w = 180 * len(pills) + 10 * (len(pills) - 1)
        x0 = (W - total_w) // 2
        for text, colour in pills:
            cv.create_rectangle(x0, pill_y, x0 + 178, pill_y + 30,
                                 fill=CARD, outline=colour, width=1)
            cv.create_text(x0 + 89, pill_y + 15, text=text,
                           fill=colour, font=("Segoe UI", 10, "bold"), anchor="center")
            x0 += 188

        # ---- Footer
        cv.create_text(cx, H - 40,
                       text="Click anywhere to continue  •  Loading…",
                       fill=DIM_WHITE, font=("Segoe UI", 9), anchor="center")
        cv.create_text(cx, H - 22,
                       text="© Rathod  •  Tools and Automation",
                       fill="#4a5568", font=("Segoe UI", 8), anchor="center")

    # ==========================================================================
    # Animated rings (orbiting dots around a central glow)
    # ==========================================================================

    def _create_animated_rings(self) -> None:
        cv = self._cv
        cx, cy = 60, self._HEIGHT // 2  # left-side decoration

        # Central glow blob
        self._glow_id = cv.create_oval(
            cx - 20, cy - 20, cx + 20, cy + 20,
            fill=ACCENT, outline=""
        )

        # Orbiting dots
        for i in range(8):
            oid = cv.create_oval(0, 0, 8, 8, fill=CYAN, outline="")
            self._ring_ids.append(oid)

        # Right side decoration
        cx2, cy2 = self._WIDTH - 60, self._HEIGHT // 2
        self._glow_id2 = cv.create_oval(
            cx2 - 20, cy2 - 20, cx2 + 20, cy2 + 20,
            fill=GOLD, outline=""
        )
        self._ring_ids2: list = []
        for i in range(8):
            oid = cv.create_oval(0, 0, 8, 8, fill=ACCENT, outline="")
            self._ring_ids2.append(oid)

    def _create_progress_bar(self) -> None:
        cv = self._cv
        W, H = self._WIDTH, self._HEIGHT
        y = H - 60
        # Track
        cv.create_rectangle(60, y, W - 60, y + 6,
                             fill="#1a2040", outline=ACCENT, width=1)
        # Fill (starts empty)
        self._progress_id = cv.create_rectangle(
            61, y + 1, 61, y + 5, fill=ACCENT, outline=""
        )
        self._progress_track_x = (61, W - 61)

    # ==========================================================================
    # Animation loop
    # ==========================================================================

    def _animate(self) -> None:
        if self._closed:
            return

        self._tick += 1
        t = self._tick * 0.08  # speed factor

        # ---- Left orbiting ring
        cx, cy = 60, self._HEIGHT // 2
        n = len(self._ring_ids)
        for i, oid in enumerate(self._ring_ids):
            angle = t + (2 * math.pi * i / n)
            r = 32
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            self._cv.coords(oid, x - 4, y - 4, x + 4, y + 4)
            # Vary colour brightness
            brightness = int(128 + 127 * math.sin(angle + t))
            col = f"#00{brightness:02x}ff"
            self._cv.itemconfig(oid, fill=col)

        # ---- Right orbiting ring
        cx2, cy2 = self._WIDTH - 60, self._HEIGHT // 2
        n2 = len(self._ring_ids2)
        for i, oid in enumerate(self._ring_ids2):
            angle = -t + (2 * math.pi * i / n2)
            r = 32
            x = cx2 + r * math.cos(angle)
            y = cy2 + r * math.sin(angle)
            self._cv.coords(oid, x - 4, y - 4, x + 4, y + 4)
            brightness = int(128 + 127 * math.sin(angle - t))
            col = f"#{brightness:02x}9600"
            self._cv.itemconfig(oid, fill=col)

        # ---- Glow pulse
        pulse = 0.5 + 0.5 * math.sin(t * 2)
        r_g   = int(10 + pulse * 14)
        self._cv.coords(self._glow_id,
                        60 - r_g, self._HEIGHT // 2 - r_g,
                        60 + r_g, self._HEIGHT // 2 + r_g)

        # ---- Progress bar fill (3.5 s window)
        elapsed_frac = min(self._tick / (3.5 / 0.03), 1.0)
        x0, x1 = self._progress_track_x
        fill_x = x0 + int((x1 - x0) * elapsed_frac)
        self._cv.coords(self._progress_id,
                        x0, self._HEIGHT - 59, fill_x, self._HEIGHT - 55)

        self.after(30, self._animate)   # ~33 fps

    # ==========================================================================
    # Close
    # ==========================================================================

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.destroy()
        self._on_done()
