from __future__ import annotations

import asyncio
import re

from . import js
from . import selectors as sel
from . import timings as tm
from .errors import MiniAppNotOpen, SelectorBroken
from .session import BrowserSession


class MiniAppOps:
    """Generic interaction with a Telegram Mini App (web-app iframe)."""

    def __init__(self, session: BrowserSession):
        self.session = session

    async def _iframe_element(self):
        page = self.session.page
        loc = page.locator(sel.WEBAPP_IFRAME)
        if not await loc.count():
            raise MiniAppNotOpen()
        return loc.first

    async def _frame(self):
        el = await self._iframe_element()
        handle = await el.element_handle()
        frame = await handle.content_frame() if handle else None
        if frame is None:
            raise MiniAppNotOpen()
        return frame

    async def open(self, button_text: str | None = None) -> dict:
        from .telegram import TelegramOps  # local import to avoid cycle

        await self.session.ensure_started()
        await self.session.ensure_logged_in()
        page = self.session.page
        if await page.locator(sel.WEBAPP_IFRAME).count():
            frame = await self._frame()
            return {"status": "already_open", "url": frame.url}
        ops = TelegramOps(self.session)
        try:
            await ops.click_button(text=button_text) if button_text else \
                await ops.click_button(row=0, col=0)
        except Exception:
            pass  # the button may open the app anyway; verify by iframe below
        # first open of a bot's web app may ask for confirmation
        confirm = page.locator(".popup:visible .popup-button, .popup:visible button",
                               has_text=re.compile(r"^(open|launch|confirm)", re.I))
        try:
            await confirm.first.click(timeout=tm.MINIAPP_CONFIRM_TIMEOUT_MS)
        except Exception:
            pass
        try:
            await page.wait_for_selector(sel.WEBAPP_IFRAME, state="attached",
                                         timeout=tm.MINIAPP_IFRAME_TIMEOUT_MS)
        except Exception:
            raise SelectorBroken("web-app iframe (did the button open a Mini App?)")
        await asyncio.sleep(tm.MINIAPP_BOOT_S)
        frame = await self._frame()
        return {"status": "open", "url": frame.url}

    async def snapshot(self, max_elements: int = 150) -> str:
        frame = await self._frame()
        return await frame.evaluate(js.MINIAPP_SNAPSHOT, max_elements)

    async def click(self, ref: str) -> dict:
        frame = await self._frame()
        loc = frame.locator(f'[data-tgmcp-ref="{ref}"]')
        if not await loc.count():
            raise SelectorBroken(f"mini-app element {ref} (take a fresh tg_miniapp_snapshot)")
        await loc.click()
        await asyncio.sleep(tm.MINIAPP_ACTION_S)
        return {"clicked": ref}

    async def type(self, ref: str, text: str) -> dict:
        frame = await self._frame()
        loc = frame.locator(f'[data-tgmcp-ref="{ref}"]')
        if not await loc.count():
            raise SelectorBroken(f"mini-app element {ref} (take a fresh tg_miniapp_snapshot)")
        await loc.click()
        await loc.fill(text)
        return {"typed": text, "into": ref}

    async def screenshot(self) -> bytes:
        el = await self._iframe_element()
        return await el.screenshot()

    async def close(self) -> dict:
        page = self.session.page

        async def gone() -> bool:
            try:
                await page.wait_for_selector(sel.WEBAPP_IFRAME, state="detached",
                                             timeout=tm.MINIAPP_CLOSE_TIMEOUT_MS)
                return True
            except Exception:
                return await page.locator(sel.WEBAPP_IFRAME).count() == 0

        await page.keyboard.press("Escape")
        if await gone():
            return {"status": "closed"}
        # fall back to the Browser-window header icons (close is among them)
        buttons = page.locator(sel.WEBAPP_HEADER_BUTTONS)
        for i in range(min(await buttons.count(), 4)):
            await buttons.nth(i).click()
            if await gone():
                return {"status": "closed"}
        return {"status": "still_open"}
