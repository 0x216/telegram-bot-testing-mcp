from __future__ import annotations

import asyncio

from playwright.async_api import BrowserContext, Page, async_playwright

from . import selectors as sel
from .config import Config
from .errors import AdapterError, NotLoggedIn, WaitTimeout


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

    async def _auth_text(self) -> str:
        auth = self.page.locator(sel.AUTH_PAGES)
        if not await auth.count():
            return ""
        return (await auth.inner_text()).lower()

    async def login_phone_start(self, phone: str) -> dict:
        """Headless login, step 1: submit the phone number.

        The confirmation code is delivered to the account's logged-in devices
        (or via SMS) — feed it to login_submit_code next.
        """
        await self.ensure_started()
        if await self.is_logged_in():
            return {"status": "already_logged_in"}
        page = self.page
        btn = page.get_by_text("Log in by phone Number", exact=False)
        if await btn.count():
            await btn.first.click()
            await asyncio.sleep(1.5)
        inp = page.locator(sel.PHONE_INPUT).first
        await inp.click()
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
        await page.keyboard.type("+" + phone.lstrip("+"), delay=40)
        await asyncio.sleep(0.7)
        await page.get_by_role("button", name="Next").first.click()
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 25
        while loop.time() < deadline:
            body = await self._auth_text()
            if "code" in body or "sms" in body:
                return {"status": "code_sent",
                        "hint": "Check the Telegram app on the account's other "
                                "devices (or SMS), then call login_submit_code."}
            if "invalid" in body or "banned" in body:
                raise AdapterError(f"Telegram rejected the phone number: {body[:120]}")
            await asyncio.sleep(1)
        raise WaitTimeout(25, what="the confirmation-code screen")

    async def login_submit_code(self, code: str) -> dict:
        """Headless login, step 2: type the confirmation code (cells are
        auto-focused on the code screen)."""
        page = self.page
        await page.keyboard.type(code.strip(), delay=150)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 20
        while loop.time() < deadline:
            if await self.is_logged_in():
                return {"status": "logged_in"}
            body = await self._auth_text()
            if "password" in body:
                return {"status": "password_needed",
                        "hint": "The account has 2FA; call login_submit_password."}
            if "invalid" in body:
                raise AdapterError("Telegram rejected the code (Invalid code).",
                                   hint="Re-run login_phone_start to retry.")
            await asyncio.sleep(1)
        raise WaitTimeout(20, what="login completion after the code")

    async def login_submit_password(self, password: str) -> dict:
        """Headless login, step 3 (only for 2FA accounts)."""
        page = self.page
        pw = page.locator(f"{sel.AUTH_PAGES} input[type=password]").first
        await pw.click()
        await pw.fill(password)
        await page.keyboard.press("Enter")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 20
        while loop.time() < deadline:
            if await self.is_logged_in():
                return {"status": "logged_in"}
            body = await self._auth_text()
            if "invalid" in body or "incorrect" in body:
                raise AdapterError("Telegram rejected the 2FA password.")
            await asyncio.sleep(1)
        raise WaitTimeout(20, what="login completion after the password")

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
