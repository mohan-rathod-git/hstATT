"""
test_result_detection.py
Unit tests for response classification logic in AttendanceWorkflow.
Uses a minimal subclass to expose private helpers without a live browser.
"""

import pytest
from app.attendance_workflow import AttendanceJob, AttendanceResult, AttendanceWorkflow


class _FakeWorkflow(AttendanceWorkflow):
    """Minimal subclass that skips the constructor — only tests classify helpers."""

    def __init__(self):
        # Intentionally skip super().__init__ to avoid needing a real page/config
        pass


@pytest.fixture
def wf():
    return _FakeWorkflow()


# ---------------------------------------------------------------------------
# Alert classification
# ---------------------------------------------------------------------------

class TestAlertClassification:
    def test_already_marked(self, wf):
        job = AttendanceJob("01/01/2024", "Alice", "No Power")
        result = wf._classify_alert("Student already marked", job)
        assert result == AttendanceResult.ALREADY_MARKED

    def test_already_marked_variant(self, wf):
        job = AttendanceJob("01/01/2024", "Bob", "No Power")
        result = wf._classify_alert("Attendance has already been marked for this student", job)
        assert result == AttendanceResult.ALREADY_MARKED

    def test_success_alert(self, wf):
        job = AttendanceJob("01/01/2024", "Carol", "No Power")
        result = wf._classify_alert("Attendance marked successfully!", job)
        assert result == AttendanceResult.SUCCESS

    def test_invalid_date(self, wf):
        job = AttendanceJob("01/01/2020", "Dave", "No Power")
        result = wf._classify_alert("Invalid date – only previous two days allowed", job)
        assert result == AttendanceResult.INVALID_DATE

    def test_session_expired_alert(self, wf):
        job = AttendanceJob("01/01/2024", "Eve", "No Power")
        result = wf._classify_alert("Session expired. Please login again.", job)
        assert result == AttendanceResult.SESSION_EXPIRED

    def test_unknown_alert(self, wf):
        job = AttendanceJob("01/01/2024", "Frank", "No Power")
        result = wf._classify_alert("Something unexpected happened", job)
        assert result == AttendanceResult.UNKNOWN


# ---------------------------------------------------------------------------
# Page content classification
# ---------------------------------------------------------------------------

class TestPageContentClassification:
    def _page(self, html: str) -> str:
        return f"<html><body>{html}</body></html>"

    def test_duplicate_in_page(self, wf):
        job = AttendanceJob("01/01/2024", "Grace", "No Power")
        result = wf._classify_page_content(self._page("already marked"), job)
        assert result == AttendanceResult.ALREADY_MARKED

    def test_success_in_page(self, wf):
        job = AttendanceJob("01/01/2024", "Hank", "No Power")
        result = wf._classify_page_content(self._page("Attendance marked successfully"), job)
        assert result == AttendanceResult.SUCCESS

    def test_session_in_page(self, wf):
        job = AttendanceJob("01/01/2024", "Ivy", "No Power")
        result = wf._classify_page_content(self._page("Session expired, please login"), job)
        assert result == AttendanceResult.SESSION_EXPIRED

    def test_reason_not_set_in_page(self, wf):
        job = AttendanceJob("01/01/2024", "Jack", "")
        result = wf._classify_page_content(self._page("Please select reason"), job)
        assert result == AttendanceResult.REASON_NOT_SET

    def test_unknown_page_content(self, wf):
        job = AttendanceJob("01/01/2024", "Karen", "No Power")
        result = wf._classify_page_content(self._page("Welcome to the portal"), job)
        assert result == AttendanceResult.UNKNOWN
