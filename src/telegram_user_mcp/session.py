from __future__ import annotations

import asyncio
import re

from playwright.async_api import BrowserContext, Page, async_playwright

from . import selectors as sel
from . import timings as tm
from .config import Config
from .errors import AdapterError, NotLoggedIn, WaitTimeout


class BrowserSession:
    """Owns the Playwright lifecycle over a persistent Chromium profile."""

    def __init__(self, config: Config):
        self.config = config
        self._pw = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None
        # when set, Chromium is launched with a fake microphone fed from this
        # WAV file (voice-message testing); changing it requires a relaunch
        self.voice_capture_file: str | None = None

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
        # --lang pins fresh profiles to English UI (our text fallbacks assume
        # it). NOTE: Playwright's locale= emulation must NOT be used here — its
        # CDP locale override breaks WebK's MTProto worker (messages hang in
        # is-sending; verified live 2026-07-13).
        args = ["--lang=en-US"]
        if self.voice_capture_file:
            args += [
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                f"--use-file-for-fake-audio-capture={self.voice_capture_file}%noloop",
            ]
        self._ctx = await self._pw.chromium.launch_persistent_context(
            str(self.config.profile_dir),
            headless=not headed,
            viewport={"width": 1280, "height": 900},
            args=args,
            permissions=["microphone"] if self.voice_capture_file else [],
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        await self._page.goto(self.config.base_url, wait_until="domcontentloaded")
        # Both #page-chats and #auth-pages are always in the DOM (page-chats can
        # even appear twice); visibility tells which state we're in. `:visible`
        # makes the comma-list match whichever becomes visible first.
        await self._page.wait_for_selector(
            f"{sel.LOGGED_IN_MARKER}:visible, {sel.AUTH_PAGES}:visible",
            state="attached", timeout=tm.BOOT_TIMEOUT_MS,
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

    @staticmethod
    def _contains_any(body: str, markers: tuple[str, ...]) -> bool:
        return any(m in body for m in markers)

    async def login_phone_start(self, phone: str) -> dict:
        """Headless login, step 1: submit the phone number.

        The confirmation code is delivered to the account's logged-in devices
        (or via SMS) — feed it to login_submit_code next.
        """
        await self.ensure_started()
        if await self.is_logged_in():
            return {"status": "already_logged_in"}
        page = self.page
        # The QR card has several secondary buttons (phone / passkey). Fresh
        # profiles are English (--lang), so match "phone" by text first; on a
        # non-English UI iterate the structural candidates and verify the
        # phone form actually appears, backing out with Escape otherwise.
        # The auth card's buttons render a beat after #auth-pages becomes
        # visible — poll instead of checking once.
        loop0 = asyncio.get_event_loop()
        deadline0 = loop0.time() + tm.SEARCH_ROUND_TIMEOUT_S
        tried_structural = False
        while loop0.time() < deadline0:
            if await page.locator(sel.PHONE_INPUT).count():
                break
            by_text = page.get_by_text(sel.TEXT_LOGIN_PHONE_BUTTON, exact=False)
            if await by_text.count():
                await by_text.first.click()
                await asyncio.sleep(tm.CARD_TRANSITION_S)
                continue
            # non-English UI: try each secondary auth button and verify the
            # phone form appears, backing out with Escape otherwise
            candidates = page.locator(sel.LOGIN_PHONE_BUTTON)
            if await candidates.count() and not tried_structural:
                tried_structural = True
                for i in range(await candidates.count()):
                    await candidates.nth(i).click()
                    await asyncio.sleep(tm.CARD_TRANSITION_S)
                    if await page.locator(sel.PHONE_INPUT).count():
                        break
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(tm.UI_SETTLE_S)
            await asyncio.sleep(tm.POLL_S)
        if not await page.locator(sel.PHONE_INPUT).count():
            raise WaitTimeout(tm.SEARCH_ROUND_TIMEOUT_S, what="the phone login form")
        inp = page.locator(sel.PHONE_INPUT).first
        await inp.click()
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
        await page.keyboard.type("+" + phone.lstrip("+"), delay=tm.TYPE_DELAY_MS)
        await asyncio.sleep(tm.UI_SETTLE_S)
        await page.locator(sel.AUTH_NEXT_BUTTON).first.click()
        digits = phone.lstrip("+")[-4:]
        loop = asyncio.get_event_loop()
        deadline = loop.time() + tm.LOGIN_CODE_SCREEN_TIMEOUT_S
        while loop.time() < deadline:
            # code screen shows the phone number as a heading — locale-proof
            heading = page.locator(sel.AUTH_PHONE_HEADING)
            if await heading.count():
                head = await heading.first.inner_text()
                if digits in head.replace(" ", ""):
                    return {"status": "code_sent",
                            "hint": "Check the Telegram app on the account's other "
                                    "devices (or SMS), then call login_submit_code."}
            body = await self._auth_text()
            if self._contains_any(body, sel.TEXT_CODE_SENT):
                return {"status": "code_sent",
                        "hint": "Check the Telegram app on the account's other "
                                "devices (or SMS), then call login_submit_code."}
            if self._contains_any(body, sel.TEXT_PHONE_REJECTED):
                raise AdapterError(f"Telegram rejected the phone number: {body[:120]}")
            await asyncio.sleep(tm.POLL_SLOW_S)
        raise WaitTimeout(tm.LOGIN_CODE_SCREEN_TIMEOUT_S,
                          what="the confirmation-code screen")

    async def login_submit_code(self, code: str) -> dict:
        """Headless login, step 2: type the confirmation code (cells are
        auto-focused on the code screen)."""
        page = self.page
        await page.keyboard.type(code.strip(), delay=tm.CODE_TYPE_DELAY_MS)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + tm.LOGIN_STEP_TIMEOUT_S
        while loop.time() < deadline:
            if await self.is_logged_in():
                return {"status": "logged_in"}
            if await page.locator(sel.PASSWORD_INPUT).count():
                return {"status": "password_needed",
                        "hint": "The account has 2FA; call login_submit_password."}
            body = await self._auth_text()
            if self._contains_any(body, sel.TEXT_PASSWORD_SCREEN):
                return {"status": "password_needed",
                        "hint": "The account has 2FA; call login_submit_password."}
            if (await page.locator(sel.AUTH_ERROR).count()
                    or self._contains_any(body, sel.TEXT_CODE_INVALID)):
                raise AdapterError("Telegram rejected the code.",
                                   hint="Re-run login_phone_start to retry.")
            await asyncio.sleep(tm.POLL_SLOW_S)
        raise WaitTimeout(tm.LOGIN_STEP_TIMEOUT_S, what="login completion after the code")

    async def login_submit_password(self, password: str) -> dict:
        """Headless login, step 3 (only for 2FA accounts)."""
        page = self.page
        pw = page.locator(sel.PASSWORD_INPUT).first
        await pw.click()
        await pw.fill(password)
        await page.keyboard.press("Enter")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + tm.LOGIN_STEP_TIMEOUT_S
        while loop.time() < deadline:
            if await self.is_logged_in():
                return {"status": "logged_in"}
            if await self.page.locator(sel.AUTH_ERROR).count():
                raise AdapterError("Telegram rejected the 2FA password.")
            await asyncio.sleep(tm.POLL_SLOW_S)
        raise WaitTimeout(tm.LOGIN_STEP_TIMEOUT_S,
                          what="login completion after the password")

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
            await asyncio.sleep(tm.LOGIN_POLL_S)
        await self.start()
        raise WaitTimeout(timeout_s, what="login (QR was not scanned in time)")
