"""
browser_manager.py
Manages the Playwright browser lifecycle.
Keeps automation logic separate from the dashboard.
"""

import asyncio
import threading
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from app.logging_manager import ActivityLogger


class BrowserManager:
    """
    Opens and manages a single Playwright browser instance.

    The browser is always launched in headed (non-headless) mode so the user
    can monitor the session.  Authentication is performed manually by the user.
    """

    def __init__(self, logger: ActivityLogger) -> None:
        self._logger = logger
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ public

    async def launch(
        self,
        browser_name: str = "chromium",
        headless: bool = False,
        page_load_timeout: int = 30,
    ) -> Page:
        """
        Start Playwright, launch the chosen browser, and return the active Page.
        Raises RuntimeError if the browser cannot be started.
        """
        if self._playwright is not None:
            await self.close()

        self._logger.info(f"Launching {browser_name} browser…")
        try:
            self._playwright = await async_playwright().start()
            launcher = getattr(self._playwright, browser_name)
            self._browser = await launcher.launch(
                headless=headless,
                args=["--start-maximized"],
            )
            self._context = await self._browser.new_context(
                no_viewport=True,
                # Do NOT intercept storage or cookies — let the portal manage its
                # own session legitimately.
            )
            self._page = await self._context.new_page()
            self._page.set_default_timeout(page_load_timeout * 1_000)
            self._page.set_default_navigation_timeout(page_load_timeout * 1_000)
            self._logger.info("Browser opened successfully.")
            return self._page
        except Exception as exc:
            self._logger.error(f"Failed to launch browser: {exc}")
            raise RuntimeError(f"Browser launch failed: {exc}") from exc

    async def navigate(self, url: str, timeout: int = 30) -> bool:
        """
        Navigate to a URL.  Returns True on success, False on timeout/error.
        """
        if self._page is None:
            self._logger.error("No active page. Launch the browser first.")
            return False
        try:
            self._logger.info(f"Navigating to: {url}")
            await self._page.goto(url, timeout=timeout * 1_000, wait_until="domcontentloaded")
            self._logger.info("Page loaded.")
            return True
        except Exception as exc:
            self._logger.error(f"Navigation error: {exc}")
            return False

    async def close(self) -> None:
        """Cleanly shut down the browser and Playwright runtime."""
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._logger.info("Browser closed.")

    async def is_alive(self) -> bool:
        """Return True when the browser process and page are still available."""
        try:
            if self._page is None or self._page.is_closed():
                return False
            if self._browser is None or not self._browser.is_connected():
                return False
            return True
        except Exception:
            return False

    @property
    def page(self) -> Optional[Page]:
        return self._page
