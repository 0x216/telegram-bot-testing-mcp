from __future__ import annotations

import asyncio

from . import selectors as sel
from .errors import MiniAppNotOpen, SelectorBroken
from .session import BrowserSession

SNAPSHOT_JS = """
(max) => {
  let n = 0;
  const lines = [];
  const interesting = document.querySelectorAll(
    'a, button, input, textarea, select, [role], [onclick], h1, h2, h3, label, [data-tgmcp-ref]');
  for (const el of interesting) {
    if (n >= max) break;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const ref = 'e' + (++n);
    el.setAttribute('data-tgmcp-ref', ref);
    const role = el.getAttribute('role') || el.tagName.toLowerCase();
    const text = (el.innerText || el.value || el.placeholder || '').trim().slice(0, 80);
    lines.push(`[${ref}] ${role} "${text}"`);
  }
  return lines.join('\\n');
}
"""


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
        try:
            await page.wait_for_selector(sel.WEBAPP_IFRAME, state="attached", timeout=15_000)
        except Exception:
            raise SelectorBroken("web-app iframe (did the button open a Mini App?)")
        await asyncio.sleep(1.5)  # let the app boot
        frame = await self._frame()
        return {"status": "open", "url": frame.url}

    async def snapshot(self, max_elements: int = 150) -> str:
        frame = await self._frame()
        return await frame.evaluate(SNAPSHOT_JS, max_elements)

    async def click(self, ref: str) -> dict:
        frame = await self._frame()
        loc = frame.locator(f'[data-tgmcp-ref="{ref}"]')
        if not await loc.count():
            raise SelectorBroken(f"mini-app element {ref} (take a fresh tg_miniapp_snapshot)")
        await loc.click()
        await asyncio.sleep(0.5)
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
        btn = page.locator(sel.WEBAPP_CLOSE)
        if await btn.count():
            await btn.first.click()
            try:
                await page.wait_for_selector(sel.WEBAPP_IFRAME, state="detached", timeout=5_000)
            except Exception:
                pass
        return {"status": "closed" if not await page.locator(sel.WEBAPP_IFRAME).count()
                else "still_open"}
