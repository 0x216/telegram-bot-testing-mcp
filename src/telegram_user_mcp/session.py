from __future__ import annotations

import asyncio

from playwright.async_api import BrowserContext, Page, async_playwright

from . import selectors as sel
from .config import Config
from .errors import NotLoggedIn, WaitTimeout


class BrowserSession:
    """Owns the Playwright lifecycle over a persistent Chromium profile."""

    def __init__(self, config: Config):
        self.config = config
        self._pw = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("session not started")
        return self._page

    async def ensure_started(self) -> None:
        if self._page is None:
            await self.start()

    async def start(self, headed: bool | None = None) -> None:
        await self.stop()
        headed = self.config.headed if headed is None else headed
        self.config.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            str(self.config.profile_dir),
            headless=not headed,
            viewport={"width": 1280, "height": 900},
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        await self._page.goto(self.config.base_url, wait_until="domcontentloaded")
        # Both #page-chats and #auth-pages are always in the DOM (page-chats can
        # even appear twice); visibility tells which state we're in. `:visible`
        # makes the comma-list match whichever becomes visible first.
        await self._page.wait_for_selector(
            f"{sel.LOGGED_IN_MARKER}:visible, {sel.AUTH_PAGES}:visible",
            state="attached", timeout=60_000,
        )

    async def stop(self) -> None:
        if self._ctx is not None:
            await self._ctx.close()
            self._ctx = self._page = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None

    async def is_logged_in(self) -> bool:
        await self.ensure_started()
        return await self.page.locator(f"{sel.LOGGED_IN_MARKER}:visible").count() > 0

    async def ensure_logged_in(self) -> None:
        if not await self.is_logged_in():
            raise NotLoggedIn()

    async def login_interactive(self, timeout_s: int = 300) -> dict:
        if await self.is_logged_in():
            return {"status": "already_logged_in"}
        await self.start(headed=True)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            if await self.page.locator(f"{sel.LOGGED_IN_MARKER}:visible").count() > 0:
                await self.start()  # relaunch in configured (headless) mode
                return {"status": "logged_in"}
            await asyncio.sleep(2)
        await self.start()
        raise WaitTimeout(timeout_s, what="login (QR was not scanned in time)")
