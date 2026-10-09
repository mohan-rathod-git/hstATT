"""
attendance_workflow.py
Orchestrates the full attendance-marking cycle:
  select date → select student → select reason → confirm → submit → parse result.

Designed to run in a background asyncio event loop so the Tkinter UI stays responsive.
"""

import asyncio
import enum
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.configuration import Configuration
from app.logging_manager import ActivityLogger
from app.page_detection import (
    DATE_SELECT,
    STUDENT_SELECT,
    REASON_SELECT,
    SUBMIT_BUTTON,
    PageDetector,
)


# ---------------------------------------------------------------------------
# Result classification
# ---------------------------------------------------------------------------

class AttendanceResult(enum.Enum):
    SUCCESS          = "SUCCESS"
    ALREADY_MARKED   = "ALREADY_MARKED"
    INVALID_DATE     = "INVALID_DATE"
    STUDENT_NOT_FOUND = "STUDENT_NOT_FOUND"
    REASON_NOT_SET   = "REASON_NOT_SET"
    SESSION_EXPIRED  = "SESSION_EXPIRED"
    NETWORK_ERROR    = "NETWORK_ERROR"
    TIMEOUT          = "TIMEOUT"
    UNKNOWN          = "UNKNOWN"
    CANCELLED        = "CANCELLED"


# ---------------------------------------------------------------------------
# Per-student job record
# ---------------------------------------------------------------------------

@dataclass
class AttendanceJob:
    date: str
    student: str
    reason: str
    result: Optional[AttendanceResult] = None
    detail: str = ""


# ---------------------------------------------------------------------------
# Workflow status signals sent to the UI
# ---------------------------------------------------------------------------

@dataclass
class WorkflowStatus:
    current_operation: str = ""
    success_count: int = 0
    already_marked_count: int = 0
    failed_count: int = 0
    progress: float = 0.0          # 0.0 – 1.0
    is_running: bool = False
    is_paused: bool = False
    jobs: List[AttendanceJob] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main workflow class
# ---------------------------------------------------------------------------

class AttendanceWorkflow:
    """
    High-level automation controller.

    Thread-safety note:
    - run_jobs() is a coroutine — run it in the background asyncio loop.
    - pause() / resume() / stop() are safe to call from the Tkinter thread.
    """

    # Keywords that indicate various server responses
    _SUCCESS_KEYWORDS    = ["successfully", "marked successfully", "attendance marked"]
    _DUPLICATE_KEYWORDS  = ["already marked", "already been marked", "duplicate"]
    _INVALID_DATE_KWORDS = ["invalid date", "date not permitted", "previous two days"]
    _SESSION_KWORDS      = ["session expired", "please login", "please log in"]
    _REASON_KWORDS       = ["select reason", "reason not selected"]

    def __init__(
        self,
        page: Page,
        config: Configuration,
        logger: ActivityLogger,
        status_callback: Callable[[WorkflowStatus], None],
        confirm_callback: Callable[[AttendanceJob], bool],
    ) -> None:
        self._page = page
        self._config = config
        self._logger = logger
        self._status_cb = status_callback
        self._confirm_cb = confirm_callback
        self._detector = PageDetector(logger)
        self._status = WorkflowStatus()
        self._stop_flag = False
        self._pause_flag = False

    # ------------------------------------------------------------------ control

    def stop(self) -> None:
        self._stop_flag = True
        self._logger.warning("Stop requested — will halt after current step.")

    def pause(self) -> None:
        self._pause_flag = True
        self._status.is_paused = True
        self._logger.info("Automation paused.")
        self._push_status()

    def resume(self) -> None:
        self._pause_flag = False
        self._status.is_paused = False
        self._logger.info("Automation resumed.")
        self._push_status()

    # ------------------------------------------------------------------ main entry

    async def run_jobs(self, jobs: List[AttendanceJob]) -> WorkflowStatus:
        """
        Process a list of AttendanceJob objects in order.
        Returns the final WorkflowStatus.
        """
        self._stop_flag = False
        self._pause_flag = False
        self._status = WorkflowStatus(jobs=jobs, is_running=True)
        total = len(jobs)
        self._push_status("Automation started.")

        # Verify the attendance form is present before starting
        form_ready = await self._detector.wait_for_attendance_form(
            self._page, timeout=self._config.element_wait_timeout
        )
        if not form_ready:
            self._logger.error("Attendance form not found. Stopping.")
            self._status.is_running = False
            self._push_status("Attendance form not detected.")
            return self._status

        for idx, job in enumerate(jobs):
            if self._stop_flag:
                self._logger.warning("Automation stopped by user.")
                break

            await self._wait_while_paused()
            if self._stop_flag:
                break

            self._push_status(f"Processing job {idx + 1}/{total}: {job.student}")
            result = await self._process_single_job(job)
            job.result = result

            if result == AttendanceResult.SUCCESS:
                self._status.success_count += 1
                self._logger.success(f"[{job.student}] Result: SUCCESS")
            elif result == AttendanceResult.ALREADY_MARKED:
                self._status.already_marked_count += 1
                self._logger.info(f"[{job.student}] Result: ALREADY MARKED")
            elif result == AttendanceResult.CANCELLED:
                self._logger.warning(f"[{job.student}] Cancelled by user.")
                break
            else:
                self._status.failed_count += 1
                self._logger.error(f"[{job.student}] Result: {result.value} — {job.detail}")

            self._status.progress = (idx + 1) / total
            self._push_status()
            await asyncio.sleep(1.0)  # brief pause between submissions

        self._status.is_running = False
        self._status.is_paused = False
        self._push_status("Automation finished.")
        return self._status

    # ------------------------------------------------------------------ per-job

    async def _process_single_job(self, job: AttendanceJob) -> AttendanceResult:
        """Run the full workflow for one student."""
        attempt = 0
        max_retries = self._config.max_retries
        backoff = 2.0  # seconds

        while attempt <= max_retries:
            if self._stop_flag:
                return AttendanceResult.CANCELLED

            # -- Check session health --
            if await self._detector.detect_session_expired(self._page):
                self._logger.error("Session has expired. Please log in again.")
                return AttendanceResult.SESSION_EXPIRED

            # -- Step 1: Select date --
            ok, detail = await self._select_option(DATE_SELECT, job.date, "Date")
            if not ok:
                job.detail = detail
                return AttendanceResult.INVALID_DATE

            # -- Step 2: Select student --
            ok, detail = await self._select_option(STUDENT_SELECT, job.student, "Student")
            if not ok:
                job.detail = detail
                return AttendanceResult.STUDENT_NOT_FOUND

            # -- Step 3: Select reason --
            ok, detail = await self._select_option(REASON_SELECT, job.reason, "Reason")
            if not ok:
                job.detail = detail
                return AttendanceResult.REASON_NOT_SET

            # -- Step 4: User confirmation --
            self._logger.info(
                f"Ready to submit → Date: {job.date} | Student: {job.student} | Reason: {job.reason}"
            )
            if self._config.require_confirmation:
                confirmed = await asyncio.get_event_loop().run_in_executor(
                    None, self._confirm_cb, job
                )
                if not confirmed:
                    self._logger.warning("User declined confirmation — skipping this entry.")
                    return AttendanceResult.CANCELLED

            # -- Step 5: Submit --
            result = await self._submit_and_parse(job)

            if result in (AttendanceResult.TIMEOUT, AttendanceResult.NETWORK_ERROR):
                attempt += 1
                if attempt <= max_retries:
                    wait = backoff * (2 ** (attempt - 1))
                    self._logger.warning(
                        f"Retrying in {wait:.0f}s (attempt {attempt}/{max_retries})…"
                    )
                    await asyncio.sleep(wait)
                    continue
                else:
                    self._logger.error("Max retries reached. Stopping to avoid duplicates.")
                    job.detail = "Max retries exhausted after timeout."
                    return AttendanceResult.TIMEOUT

            return result

        return AttendanceResult.UNKNOWN

    # ------------------------------------------------------------------ helpers

    async def _select_option(
        self, selector: str, value: str, label: str
    ) -> tuple[bool, str]:
        """
        Select <option> whose visible text matches `value` (case-insensitive).
        Returns (True, "") on success or (False, error_message) on failure.
        """
        timeout_ms = self._config.element_wait_timeout * 1_000
        try:
            await self._page.wait_for_selector(selector, timeout=timeout_ms)
            options: List[str] = await self._page.eval_on_selector_all(
                f"{selector} option",
                "nodes => nodes.map(o => ({value: o.value, text: o.textContent.trim()}))",
            )
            match = next(
                (o for o in options if value.lower() in o["text"].lower()), None
            )
            if match is None:
                msg = (
                    f"{label} '{value}' was not found in the dropdown. "
                    f"Available: {[o['text'] for o in options]}"
                )
                self._logger.error(msg)
                return False, msg

            await self._page.select_option(selector, value=match["value"])
            self._logger.info(f"{label} selected: '{match['text']}'")
            return True, ""

        except PlaywrightTimeout:
            msg = f"{label} dropdown not found within timeout."
            self._logger.error(msg)
            return False, msg
        except Exception as exc:
            msg = f"Unexpected error selecting {label}: {exc}"
            self._logger.error(msg)
            return False, msg

    async def _submit_and_parse(self, job: AttendanceJob) -> AttendanceResult:
        """Click Mark Attendance and interpret the portal's response."""
        timeout_ms = self._config.page_load_timeout * 1_000

        # Set up alert/dialog handler before clicking
        alert_text: List[str] = []

        def on_dialog(dialog):
            alert_text.append(dialog.message)
            asyncio.ensure_future(dialog.accept())

        self._page.on("dialog", on_dialog)

        try:
            self._logger.info("Clicking Mark Attendance…")
            submit = self._page.locator(SUBMIT_BUTTON).first
            await submit.click(timeout=timeout_ms)

            # Wait briefly for server response
            await asyncio.sleep(2.0)

            # Check any JS alert
            if alert_text:
                return self._classify_alert(alert_text[0], job)

            # Check page content for response text
            content = await self._page.content()
            return self._classify_page_content(content, job)

        except PlaywrightTimeout:
            job.detail = "Submission timed out — result unknown. Do not retry blindly."
            self._logger.error(job.detail)
            return AttendanceResult.TIMEOUT
        except Exception as exc:
            job.detail = str(exc)
            self._logger.error(f"Submission error: {exc}")
            return AttendanceResult.NETWORK_ERROR
        finally:
            self._page.remove_listener("dialog", on_dialog)

    def _classify_alert(self, text: str, job: AttendanceJob) -> AttendanceResult:
        t = text.lower()
        if any(k in t for k in self._DUPLICATE_KEYWORDS):
            return AttendanceResult.ALREADY_MARKED
        if any(k in t for k in self._SUCCESS_KEYWORDS):
            return AttendanceResult.SUCCESS
        if any(k in t for k in self._INVALID_DATE_KWORDS):
            job.detail = text
            return AttendanceResult.INVALID_DATE
        if any(k in t for k in self._SESSION_KWORDS):
            return AttendanceResult.SESSION_EXPIRED
        job.detail = f"Unrecognised alert: {text}"
        return AttendanceResult.UNKNOWN

    def _classify_page_content(self, content: str, job: AttendanceJob) -> AttendanceResult:
        c = content.lower()
        if any(k in c for k in self._DUPLICATE_KEYWORDS):
            return AttendanceResult.ALREADY_MARKED
        if any(k in c for k in self._SUCCESS_KEYWORDS):
            return AttendanceResult.SUCCESS
        if any(k in c for k in self._INVALID_DATE_KWORDS):
            return AttendanceResult.INVALID_DATE
        if any(k in c for k in self._SESSION_KWORDS):
            return AttendanceResult.SESSION_EXPIRED
        if any(k in c for k in self._REASON_KWORDS):
            return AttendanceResult.REASON_NOT_SET
        job.detail = "Response could not be classified — please check the portal manually."
        return AttendanceResult.UNKNOWN

    # ------------------------------------------------------------------ internal

    async def _wait_while_paused(self) -> None:
        while self._pause_flag and not self._stop_flag:
            await asyncio.sleep(0.3)

    def _push_status(self, operation: str = "") -> None:
        if operation:
            self._status.current_operation = operation
        try:
            self._status_cb(self._status)
        except Exception:
            pass
