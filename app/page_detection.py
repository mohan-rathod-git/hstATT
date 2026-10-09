"""
page_detection.py
Detects whether the correct portal page is loaded and reads dropdown options.
Selectors are intentionally kept broad so they work even if the portal
upgrades its HTML — they should be refined after inspecting the real DOM.
"""

import asyncio
from typing import Dict, List, Optional, Tuple

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.logging_manager import ActivityLogger

# ---------------------------------------------------------------------------
# Selector hints — update these after opening the real portal and inspecting
# the actual HTML with DevTools (F12 → Elements).
# ---------------------------------------------------------------------------

# Page-presence indicators — any of these being visible means the form is ready
PAGE_INDICATORS = [
    "text=Manual Attendance",
    "text=MANUAL ATTENDANCE",
    "text=Mark Attendance",
    "select",           # at least one <select> element present
]

# Dropdown selectors — adjust to match the real element IDs/names
DATE_SELECT     = "select[name*='date'], select[id*='date'], #attendanceDate"
STUDENT_SELECT  = "select[name*='student'], select[id*='student'], #studentName, #studentId"
REASON_SELECT   = "select[name*='reason'], select[id*='reason'], #reason, #attendanceReason"
SUBMIT_BUTTON   = (
    "button:has-text('Mark Attendance'), "
    "input[type='submit'][value*='Mark'], "
    "button[type='submit']"
)


class PageDetector:
    """Inspects the portal page to detect form presence and read dropdown options."""

    def __init__(self, logger: ActivityLogger) -> None:
        self._logger = logger

    # ------------------------------------------------------------------ public

    async def wait_for_attendance_form(
        self, page: Page, timeout: int = 30
    ) -> bool:
        """
        Block until the attendance form appears or the timeout expires.
        Returns True when the form is detected.
        """
        self._logger.info("Waiting for attendance form to load…")
        deadline = timeout * 1_000  # ms

        for indicator in PAGE_INDICATORS:
            try:
                await page.wait_for_selector(indicator, timeout=deadline)
                self._logger.info(f"Attendance form detected (matched: {indicator}).")
                return True
            except PlaywrightTimeout:
                continue
            except Exception as exc:
                self._logger.warning(f"Indicator check failed ({indicator}): {exc}")
                continue

        self._logger.error(
            "Attendance form was not detected within the timeout. "
            "Make sure the portal URL is correct and you are logged in."
        )
        return False

    async def get_dropdown_options(
        self, page: Page, selector: str, label: str
    ) -> List[str]:
        """
        Read all <option> text values from a <select> element.
        Returns an empty list if the element cannot be found.
        """
        try:
            await page.wait_for_selector(selector, timeout=5_000)
            options: List[str] = await page.eval_on_selector_all(
                f"{selector} option",
                "nodes => nodes.map(o => o.textContent.trim()).filter(t => t.length > 0)",
            )
            self._logger.debug(f"{label} options: {options}")
            return options
        except PlaywrightTimeout:
            self._logger.warning(f"Could not find {label} dropdown (selector: {selector}).")
            return []
        except Exception as exc:
            self._logger.error(f"Error reading {label} dropdown: {exc}")
            return []

    async def get_date_options(self, page: Page) -> List[str]:
        return await self.get_dropdown_options(page, DATE_SELECT, "Date")

    async def get_student_options(self, page: Page) -> List[str]:
        return await self.get_dropdown_options(page, STUDENT_SELECT, "Student")

    async def get_reason_options(self, page: Page) -> List[str]:
        return await self.get_dropdown_options(page, REASON_SELECT, "Reason")

    async def detect_session_expired(self, page: Page) -> bool:
        """Return True if the page content suggests the session has ended."""
        try:
            content = await page.content()
            keywords = ["session expired", "login", "sign in", "please log in"]
            return any(kw in content.lower() for kw in keywords)
        except Exception:
            return False

    async def get_selectors(self) -> Dict[str, str]:
        """Expose the current selector strings for external use."""
        return {
            "date": DATE_SELECT,
            "student": STUDENT_SELECT,
            "reason": REASON_SELECT,
            "submit": SUBMIT_BUTTON,
        }
