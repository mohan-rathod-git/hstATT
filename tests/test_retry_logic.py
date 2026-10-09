"""
test_retry_logic.py
Tests for retry/backoff behaviour and stop/pause controls.
Uses an asyncio-compatible approach without a real browser.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.attendance_workflow import AttendanceJob, AttendanceResult, AttendanceWorkflow, WorkflowStatus
from app.configuration import Configuration
from app.logging_manager import ActivityLogger


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_config(tmp_path, max_retries=2, require_confirmation=False):
    cfg_path = tmp_path / "settings.json"
    cfg = Configuration(path=cfg_path)
    cfg.update({
        "portal_url":           "https://example.gov",
        "max_retries":          max_retries,
        "require_confirmation": require_confirmation,
        "page_load_timeout":    5,
        "element_wait_timeout": 5,
    })
    return cfg


def _make_logger():
    logger = ActivityLogger.__new__(ActivityLogger)
    logger._ui_callback = None
    logger._logger = MagicMock()
    return logger


@pytest.fixture
def config(tmp_path):
    return _make_config(tmp_path)


@pytest.fixture
def logger():
    return _make_logger()


# ---------------------------------------------------------------------------
# Helper to build a workflow with mocked page
# ---------------------------------------------------------------------------

def _make_workflow(config, logger, status_cb=None, confirm_cb=None):
    page = MagicMock()
    page.is_closed = MagicMock(return_value=False)
    wf = AttendanceWorkflow(
        page=page,
        config=config,
        logger=logger,
        status_callback=status_cb or (lambda s: None),
        confirm_callback=confirm_cb or (lambda j: True),
    )
    return wf, page


# ---------------------------------------------------------------------------
# Stop control
# ---------------------------------------------------------------------------

class TestStopControl:
    def test_stop_flag_cancels_jobs(self, config, logger, tmp_path):
        wf, page = _make_workflow(config, logger)

        async def run():
            # Simulate the form not being found quickly
            with patch.object(wf._detector, "wait_for_attendance_form", new_callable=AsyncMock) as mock_form:
                mock_form.return_value = True
                wf.stop()  # immediately stop
                jobs = [AttendanceJob("01/01/2024", "Alice", "No Power")]
                status = await wf.run_jobs(jobs)
                assert not status.is_running

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Reason validation (via _select_option)
# ---------------------------------------------------------------------------

class TestReasonValidation:
    def test_reason_not_in_options_returns_false(self, config, logger):
        wf, page = _make_workflow(config, logger)

        async def run():
            # Simulate dropdown returning known options only
            page.wait_for_selector = AsyncMock()
            page.eval_on_selector_all = AsyncMock(return_value=[
                {"value": "1", "text": "Network Not Available"},
                {"value": "2", "text": "No Power"},
            ])
            page.select_option = AsyncMock()
            ok, detail = await wf._select_option("select#reason", "INVALID_REASON", "Reason")
            assert not ok
            assert "not found" in detail.lower()

        asyncio.run(run())

    def test_valid_reason_selects_correctly(self, config, logger):
        wf, page = _make_workflow(config, logger)

        async def run():
            page.wait_for_selector = AsyncMock()
            page.eval_on_selector_all = AsyncMock(return_value=[
                {"value": "1", "text": "Network Not Available"},
                {"value": "2", "text": "No Power"},
            ])
            page.select_option = AsyncMock()
            ok, detail = await wf._select_option("select#reason", "Network Not Available", "Reason")
            assert ok
            assert detail == ""
            page.select_option.assert_awaited_once_with("select#reason", value="1")

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    def test_timeout_triggers_retry(self, config, logger):
        """A TIMEOUT result should be retried up to max_retries times."""
        wf, page = _make_workflow(config, logger)
        call_count = [0]

        async def fake_submit(job):
            call_count[0] += 1
            return AttendanceResult.TIMEOUT

        async def run():
            with patch.object(wf._detector, "wait_for_attendance_form", new_callable=AsyncMock) as mf, \
                 patch.object(wf._detector, "detect_session_expired",   new_callable=AsyncMock) as ms, \
                 patch.object(wf, "_select_option", new_callable=AsyncMock) as msel, \
                 patch.object(wf, "_submit_and_parse", new_callable=AsyncMock) as msub, \
                 patch("asyncio.sleep", new_callable=AsyncMock):

                mf.return_value    = True
                ms.return_value    = False
                msel.return_value  = (True, "")
                msub.side_effect   = fake_submit

                jobs = [AttendanceJob("01/01/2024", "Alice", "No Power")]
                status = await wf.run_jobs(jobs)

                # Should have tried 1 initial + max_retries = 3 times total
                assert call_count[0] == config.max_retries + 1
                assert status.failed_count == 1

        asyncio.run(run())

    def test_success_does_not_retry(self, config, logger):
        wf, page = _make_workflow(config, logger)
        call_count = [0]

        async def fake_submit(job):
            call_count[0] += 1
            return AttendanceResult.SUCCESS

        async def run():
            with patch.object(wf._detector, "wait_for_attendance_form", new_callable=AsyncMock) as mf, \
                 patch.object(wf._detector, "detect_session_expired",   new_callable=AsyncMock) as ms, \
                 patch.object(wf, "_select_option", new_callable=AsyncMock) as msel, \
                 patch.object(wf, "_submit_and_parse", new_callable=AsyncMock) as msub:

                mf.return_value    = True
                ms.return_value    = False
                msel.return_value  = (True, "")
                msub.side_effect   = fake_submit

                jobs = [AttendanceJob("01/01/2024", "Bob", "No Power")]
                status = await wf.run_jobs(jobs)

                assert call_count[0] == 1
                assert status.success_count == 1

        asyncio.run(run())
