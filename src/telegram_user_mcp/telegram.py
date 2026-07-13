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

    # The search dropdown has two states: the quick view labels a bot row with
    # subtitle "bot" (no username shown), while the fully-resolved list shows
    # "@username" subtitles. Row innerText concatenates fields with no
    # separator, so match individual descendants' textContent. Prefer the
    # exact-@username hit; fall back to title==username + subtitle=="bot".
    _FIND_ROW_JS = """
    (args) => {
      const rows = Array.from(document.querySelectorAll(args.rowSel));
      const uname = args.username.toLowerCase();
      const want = '@' + uname;
      for (let i = 0; i < rows.length; i++) {
        for (const el of rows[i].querySelectorAll('*')) {
          const t = (el.textContent || '').trim().toLowerCase();
          if (t === want || t.startsWith(want + ',')) return i;
        }
      }
      for (let i = 0; i < rows.length; i++) {
        const sub = rows[i].querySelector('.row-subtitle');
        const title = rows[i].querySelector('.peer-title');
        if (sub && title
            && (sub.textContent || '').trim().toLowerCase() === 'bot'
            && (title.textContent || '').trim().toLowerCase() === uname) return i;
      }
      return -1;
    }
    """

    async def _type_into_search(self, page, text: str) -> bool:
        search = page.locator(sel.SEARCH_INPUT).first
        await search.wait_for(state="visible", timeout=15_000)
        await search.click()
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
        await page.keyboard.type(text, delay=50)
        await asyncio.sleep(0.3)
        typed = await search.input_value()
        return typed.strip().lower() == text.strip().lower()

    async def open_chat(self, query: str) -> dict:
        # Deep-link hash assignment is silently ignored by WebK at runtime, so
        # go the way a human does: left-column search, click the exact @username.
        page = await self._ready()
        username = _to_username(query)
        loop = asyncio.get_event_loop()
        idx = -1
        # Global username resolution can be slow (especially on the test DC),
        # and keystrokes typed during SPA boot get swallowed, leaving the search
        # stuck on a stale query. Escape closes the search overlay so the next
        # round starts a fresh query.
        for _attempt in range(3):
            if _attempt:
                await page.keyboard.press("Escape")
                await asyncio.sleep(2)
            if not await self._type_into_search(page, username):
                await asyncio.sleep(2)  # SPA not ready to accept input yet
                continue
            deadline = loop.time() + 15
            while loop.time() < deadline:
                idx = await page.evaluate(self._FIND_ROW_JS, {
                    "rowSel": sel.SEARCH_RESULT_ROW, "username": username,
                })
                if idx >= 0:
                    break
                await asyncio.sleep(0.5)
            if idx >= 0:
                break
        if idx < 0:
            await page.keyboard.press("Escape")
            raise ChatNotFound(query)
        await page.locator(sel.SEARCH_RESULT_ROW).nth(idx).click()
        try:
            await page.wait_for_selector(sel.MESSAGE_INPUT, state="visible", timeout=10_000)
        except Exception:
            raise SelectorBroken("message composer after opening the chat")
        await asyncio.sleep(1.0)  # let history render
        msgs = await extract.read_messages(page, limit=5)
        return {"chat": username, "messages": [m.to_dict() for m in msgs]}

    async def read_messages(self, limit: int = 20) -> list[dict]:
        page = await self._ready()
        return [m.to_dict() for m in await extract.read_messages(page, limit=limit)]

    async def _press_start_if_needed(self, page) -> bool:
        # Un-started bot chats cover the composer with a START control;
        # pressing it is Telegram's way of sending /start.
        ctl = page.locator(sel.START_CONTROL)
        if await ctl.count() and await ctl.first.is_visible():
            btn = ctl.first.locator("button:visible")
            target = btn.first if await btn.count() else ctl.first
            await target.click()
            await asyncio.sleep(1.5)
            return True
        return False

    async def send_message(self, text: str) -> dict:
        page = await self._ready()
        started = await self._press_start_if_needed(page)
        if started and text.strip().lower() == "/start":
            msgs = await extract.read_messages(page, limit=5)
            mine = [m for m in msgs if m.out]
            if mine:
                return mine[-1].to_dict()
        # Several .input-message-input nodes coexist (the active one carries
        # data-peer-id and sits on top); focus it via JS instead of clicking
        # through overlapping editors.
        _FOCUS_JS = """(q) => {
          const els = Array.from(document.querySelectorAll(q)).filter(e => e.offsetParent);
          const el = els.find(e => e.dataset.peerId) || els[els.length - 1];
          if (!el) return null;
          el.focus();
          return el.textContent || '';
        }"""
        _READ_JS = """(q) => {
          const els = Array.from(document.querySelectorAll(q)).filter(e => e.offsetParent);
          const el = els.find(e => e.dataset.peerId) || els[els.length - 1];
          return el ? (el.textContent || '') : null;
        }"""
        for _attempt in range(3):
            current = await page.evaluate(_FOCUS_JS, sel.MESSAGE_INPUT)
            if current is None:
                raise SelectorBroken("message input (is a chat open?)")
            if current.strip():
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Delete")
            await page.keyboard.type(text, delay=30)
            await asyncio.sleep(0.2)
            typed = await page.evaluate(_READ_JS, sel.MESSAGE_INPUT)
            if typed is not None and typed.strip() == text.strip():
                break
        else:
            raise SelectorBroken("composer did not accept the typed text")
        await page.keyboard.press("Enter")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 10
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
          const t = btn.querySelector(args.btnTextSel);
          out.push({row: ri, col: ci, text: ((t ? t.innerText : btn.innerText) || '').trim(),
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
            "btnTextSel": sel.INLINE_BUTTON_TEXT,
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
        # WebK's topbar menu offers "Delete" which opens PopupPeer with
        # clear/delete choices; for a 1:1 bot chat this wipes the history.
        page = await self._ready()
        await page.locator(sel.TOPBAR_MENU_BUTTON).last.click()
        item = page.locator(sel.MENU_ITEM, has_text=re.compile("delete|clear", re.I))
        try:
            await item.first.click(timeout=5_000)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("'Delete/Clear' menu item")
        confirm = page.locator(f"{sel.DELETE_POPUP} {sel.POPUP_DANGER_BUTTON}")
        try:
            await confirm.first.click(timeout=5_000)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("delete/clear confirmation button")
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
