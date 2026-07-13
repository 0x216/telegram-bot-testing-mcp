from __future__ import annotations

import asyncio
import re

from . import extract
from . import selectors as sel
from .errors import ButtonNotFound, ChatNotFound, SelectorBroken, WaitTimeout
from .session import BrowserSession

_USERNAME_RE = re.compile(r"^(?:https?://)?(?:t\.me/)?@?([A-Za-z0-9_]{3,})/?$")


def _to_username(query: str) -> str:
    m = _USERNAME_RE.match(query.strip())
    if not m:
        raise ChatNotFound(query)
    return m.group(1)


class TelegramOps:
    """Semantic chat operations over an authenticated WebK page."""

    def __init__(self, session: BrowserSession):
        self.session = session

    async def _ready(self):
        await self.session.ensure_started()
        await self.session.ensure_logged_in()
        return self.session.page

    async def open_chat(self, query: str) -> dict:
        page = await self._ready()
        username = _to_username(query)
        await page.evaluate("u => { location.hash = '#@' + u }", username)
        try:
            await page.wait_for_selector(sel.MESSAGE_INPUT, state="visible", timeout=10_000)
        except Exception:
            raise ChatNotFound(query)
        await asyncio.sleep(1.0)  # let history render
        msgs = await extract.read_messages(page, limit=5)
        return {"chat": username, "messages": [m.to_dict() for m in msgs]}

    async def read_messages(self, limit: int = 20) -> list[dict]:
        page = await self._ready()
        return [m.to_dict() for m in await extract.read_messages(page, limit=limit)]

    async def send_message(self, text: str) -> dict:
        page = await self._ready()
        inp = page.locator(sel.MESSAGE_INPUT).last
        if not await inp.count():
            raise SelectorBroken("message input (is a chat open?)")
        await inp.click()
        await page.keyboard.type(text, delay=30)
        await page.keyboard.press("Enter")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 5
        while loop.time() < deadline:
            msgs = await extract.read_messages(page, limit=10)
            mine = [m for m in msgs if m.out and text.strip() in m.text]
            if mine:
                return mine[-1].to_dict()
            await asyncio.sleep(0.3)
        raise SelectorBroken("sent message bubble")

    async def wait_for_message(self, timeout_s: float = 30,
                               after_id: int | None = None) -> list[dict]:
        page = await self._ready()
        if after_id is None:
            msgs = await extract.read_messages(page, limit=30)
            after_id = max((m.id for m in msgs), default=0)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            msgs = await extract.read_messages(page, limit=30)
            fresh = [m for m in msgs if not m.out and not m.service and m.id > after_id]
            if fresh:
                return [m.to_dict() for m in fresh]
            await asyncio.sleep(0.5)
        raise WaitTimeout(timeout_s)

    # -- buttons ---------------------------------------------------------

    _BUTTONS_JS = """
    (args) => {
      let bubble = null;
      if (args.mid) bubble = document.querySelector(`${args.bubbleSel}[data-mid="${args.mid}"]`);
      else {
        const all = Array.from(document.querySelectorAll(args.bubbleSel))
                         .filter(b => b.querySelector(args.btnSel));
        bubble = all[all.length - 1] || null;
      }
      if (!bubble) return [];
      const out = [];
      Array.from(bubble.querySelectorAll(args.rowSel)).forEach((row, ri) => {
        Array.from(row.querySelectorAll(args.btnSel)).forEach((btn, ci) => {
          out.push({row: ri, col: ci, text: (btn.innerText || '').trim(),
                    mid: Number(bubble.dataset.mid || 0)});
        });
      });
      return out;
    }
    """

    async def click_button(self, text: str | None = None, row: int | None = None,
                           col: int | None = None, message_id: int | None = None) -> dict:
        page = await self._ready()
        buttons = await page.evaluate(self._BUTTONS_JS, {
            "mid": message_id, "bubbleSel": sel.BUBBLE,
            "rowSel": sel.INLINE_ROW, "btnSel": sel.INLINE_BUTTON,
        })
        wanted = text if text is not None else f"({row},{col})"
        if not buttons:
            raise ButtonNotFound(wanted, [])
        if text is not None:
            matches = [b for b in buttons if text.lower() in b["text"].lower()]
        elif row is not None and col is not None:
            matches = [b for b in buttons if b["row"] == row and b["col"] == col]
        else:
            matches = []
        if not matches:
            raise ButtonNotFound(wanted, [b["text"] for b in buttons])
        target = matches[0]
        bubble = page.locator(f'{sel.BUBBLE}[data-mid="{target["mid"]}"]')
        await bubble.locator(sel.INLINE_BUTTON).nth(buttons.index(target)).click()
        await asyncio.sleep(1.5)
        msgs = await extract.read_messages(page, limit=5)
        return {"clicked": target["text"], "messages": [m.to_dict() for m in msgs]}

    async def click_reply_button(self, text: str) -> dict:
        page = await self._ready()
        kb = page.locator(sel.REPLY_KEYBOARD)
        if not await kb.count():
            toggle = page.locator(sel.REPLY_KEYBOARD_TOGGLE)
            if await toggle.count():
                await toggle.click()
                await asyncio.sleep(0.5)
        buttons = page.locator(f"{sel.REPLY_KEYBOARD} {sel.REPLY_KEYBOARD_BUTTON}")
        labels = []
        for i in range(await buttons.count()):
            labels.append((await buttons.nth(i).inner_text()).strip())
        for i, label in enumerate(labels):
            if text.lower() in label.lower():
                await buttons.nth(i).click()
                await asyncio.sleep(1.0)
                msgs = await extract.read_messages(page, limit=5)
                return {"clicked": label, "messages": [m.to_dict() for m in msgs]}
        raise ButtonNotFound(text, labels)

    # -- files / misc ----------------------------------------------------

    async def send_file(self, path: str, caption: str | None = None) -> dict:
        page = await self._ready()
        file_inputs = page.locator(sel.FILE_INPUT)
        if not await file_inputs.count():
            raise SelectorBroken("file input")
        before = {m.id for m in await extract.read_messages(page, limit=10) if m.out}
        await file_inputs.first.set_input_files(path)
        try:
            await page.wait_for_selector(sel.ATTACH_POPUP, state="visible", timeout=10_000)
        except Exception:
            raise SelectorBroken("attach confirmation popup")
        if caption:
            cap = page.locator(f"{sel.ATTACH_POPUP} {sel.MESSAGE_INPUT}")
            if await cap.count():
                await cap.click()
                await page.keyboard.type(caption, delay=30)
        await page.locator(sel.ATTACH_POPUP_SEND).click()
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 15
        while loop.time() < deadline:
            msgs = await extract.read_messages(page, limit=10)
            fresh = [m for m in msgs if m.out and m.id not in before]
            if fresh:
                return fresh[-1].to_dict()
            await asyncio.sleep(0.5)
        raise SelectorBroken("uploaded message bubble")

    async def clear_chat(self) -> dict:
        page = await self._ready()
        await page.locator(sel.TOPBAR_MENU_BUTTON).click()
        item = page.locator(sel.MENU_ITEM, has_text=re.compile("clear", re.I))
        try:
            await item.first.click(timeout=5_000)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("'Clear messages' menu item")
        confirm = page.locator(sel.POPUP_BUTTON, has_text=re.compile("clear|delete", re.I))
        try:
            await confirm.first.click(timeout=5_000)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("clear-history confirmation button")
        await asyncio.sleep(1.0)
        return {"status": "cleared"}

    async def screenshot(self, scope: str = "chat", message_id: int | None = None) -> bytes:
        page = await self._ready()
        if scope == "message" and message_id is not None:
            loc = page.locator(f'{sel.BUBBLE}[data-mid="{message_id}"]')
            if await loc.count():
                return await loc.screenshot()
            raise SelectorBroken(f"message bubble {message_id}")
        if scope == "chat":
            loc = page.locator(sel.CHAT_CONTAINER)
            if await loc.count():
                return await loc.screenshot()
        return await page.screenshot()
