from __future__ import annotations

import asyncio
import re

from . import extract
from . import selectors as sel
from .errors import (
    AdapterError,
    ButtonNotFound,
    ChatNotFound,
    SelectorBroken,
    WaitTimeout,
)
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
        self._current_chat: str | None = None

    async def _ready(self):
        await self.session.ensure_started()
        await self.session.ensure_logged_in()
        return self.session.page

    # The search dropdown has two states: the quick view labels a bot row with
    # subtitle "bot" (no username shown), while the fully-resolved list shows
    # "@username" subtitles. Row innerText concatenates fields with no
    # separator, so match individual descendants' textContent. Prefer the
    # exact-@username hit; fall back to title==username + subtitle=="bot".
    # In title mode (query with spaces — service chats like "Telegram
    # Notifications") match the exact .peer-title instead.
    _FIND_ROW_JS = """
    (args) => {
      const rows = Array.from(document.querySelectorAll(args.rowSel));
      const uname = args.username.toLowerCase();
      if (args.byTitle) {
        for (let i = 0; i < rows.length; i++) {
          const title = rows[i].querySelector('.peer-title');
          if (title && (title.textContent || '').trim().toLowerCase() === uname) return i;
        }
        return -1;
      }
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
        # Queries with spaces are treated as exact chat titles (service chats
        # like "Telegram Notifications" have no username).
        page = await self._ready()
        by_title = " " in query.strip()
        username = query.strip() if by_title else _to_username(query)
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
                    "byTitle": by_title,
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
        self._current_chat = query
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
        # Identical texts may already exist in history; only bubbles newer than
        # this baseline count as "our" send.
        before_max = max((m.id for m in await extract.read_messages(page, limit=10)),
                         default=0)
        started = await self._press_start_if_needed(page)
        if started and text.strip().lower() == "/start":
            msgs = await extract.read_messages(page, limit=5)
            mine = [m for m in msgs if m.out and m.id > before_max]
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
            # insert_text (not type): emoji and other astral-plane chars are
            # silently dropped by synthesized keydown events
            await page.keyboard.insert_text(text)
            await asyncio.sleep(0.3)
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
            mine = [m for m in msgs if m.out and text.strip() in m.text
                    and m.id > before_max]
            if mine:
                # Optimistic bubbles carry huge temporary mids until the server
                # acks; give it a beat and prefer the settled (smallest) id.
                await asyncio.sleep(1.0)
                msgs = await extract.read_messages(page, limit=10)
                mine = [m for m in msgs if m.out and text.strip() in m.text
                        and m.id > before_max] or mine
                return min(mine, key=lambda m: m.id).to_dict()
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
        before_max = max((m.id for m in await extract.read_messages(page, limit=10)),
                         default=0)
        loop = asyncio.get_event_loop()
        labels: list[str] = []
        # Pressing a reply button sends its label as a message; verify the
        # outgoing bubble actually appeared and retry once if the click was
        # swallowed mid-render.
        for _attempt in range(2):
            kb = page.locator(f"{sel.REPLY_KEYBOARD}:visible")
            if not await kb.count():
                toggle = page.locator(sel.REPLY_KEYBOARD_TOGGLE)
                if await toggle.count():
                    await toggle.first.click()
                    await asyncio.sleep(0.7)
            buttons = page.locator(f"{sel.REPLY_KEYBOARD} {sel.REPLY_KEYBOARD_BUTTON}")
            labels = []
            for i in range(await buttons.count()):
                labels.append((await buttons.nth(i).inner_text()).strip())
            target = next((i for i, lbl in enumerate(labels)
                           if text.lower() in lbl.lower()), None)
            if target is None:
                continue
            await buttons.nth(target).click()
            deadline = loop.time() + 5
            while loop.time() < deadline:
                msgs = await extract.read_messages(page, limit=5)
                if any(m.out and m.id > before_max
                       and labels[target].lower() in m.text.lower() for m in msgs):
                    # let the optimistic bubble settle to its server mid
                    await asyncio.sleep(1.0)
                    msgs = await extract.read_messages(page, limit=5)
                    return {"clicked": labels[target],
                            "messages": [m.to_dict() for m in msgs]}
                await asyncio.sleep(0.4)
        if labels and any(text.lower() in lbl.lower() for lbl in labels):
            raise SelectorBroken(f"reply button {text!r} click did not send a message")
        raise ButtonNotFound(text, labels)

    # -- files / misc ----------------------------------------------------

    async def send_file(self, path: str, caption: str | None = None,
                        kind: str = "auto") -> dict:
        page = await self._ready()
        before = {m.id for m in await extract.read_messages(page, limit=10) if m.out}
        if kind == "auto":
            kind = "photo" if path.lower().rsplit(".", 1)[-1] in (
                "png", "jpg", "jpeg", "gif", "webp", "mp4", "mov") else "document"
        # Feeding the hidden input directly skips WebK's willAttachType state,
        # so go through the attach menu and catch the native file chooser.
        await page.locator(sel.ATTACH_BUTTON).last.click()
        pattern = re.compile("photo|video" if kind == "photo" else "document|file", re.I)
        item = page.locator(sel.MENU_ITEM, has_text=pattern).first
        try:
            async with page.expect_file_chooser(timeout=10_000) as fc_info:
                await item.click(timeout=5_000)
            chooser = await fc_info.value
            await chooser.set_files(path)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("attach menu / file chooser")
        try:
            await page.wait_for_selector(sel.ATTACH_POPUP, state="visible", timeout=10_000)
        except Exception:
            raise SelectorBroken("attach confirmation popup")
        if caption:
            cap = page.locator(f"{sel.ATTACH_POPUP} {sel.MESSAGE_INPUT}:visible")
            if await cap.count():
                await cap.first.click()
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

    async def send_voice(self, path: str, duration_s: float | None = None) -> dict:
        """Record a voice message through a fake microphone fed from a WAV file.

        Requires a browser relaunch when the WAV changes, then re-opens the
        current chat and drives the real record/send buttons.
        """
        import wave

        page = await self._ready()
        if duration_s is None:
            try:
                with wave.open(path, "rb") as w:
                    duration_s = w.getnframes() / w.getframerate()
            except Exception:
                raise AdapterError(f"{path!r} is not a readable WAV file.",
                                   hint="Voice capture needs PCM WAV input.")
        if self.session.voice_capture_file != path:
            if not self._current_chat:
                raise AdapterError("Open a chat before sending a voice message.")
            self.session.voice_capture_file = path
            await self.session.start()  # relaunch with the fake-mic flags
            await self.open_chat(self._current_chat)
            page = self.session.page
        before_max = max((m.id for m in await extract.read_messages(page, limit=10)),
                         default=0)
        record = page.locator(f"{sel.SEND_BUTTON}:visible").last
        if not await record.count():
            raise SelectorBroken("record (mic) button")
        await record.click()  # composer is empty -> starts recording
        await asyncio.sleep(min(duration_s + 0.7, 55))
        await page.locator(f"{sel.SEND_BUTTON}:visible").last.click()  # send
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 15
        while loop.time() < deadline:
            msgs = await extract.read_messages(page, limit=5)
            mine = [m for m in msgs if m.out and m.id > before_max
                    and m.media in ("voice", "audio")]
            if mine:
                return mine[-1].to_dict()
            await asyncio.sleep(0.5)
        raise SelectorBroken("sent voice bubble (recording may have failed)")

    async def clear_chat(self) -> dict:
        # WebK's topbar menu offers "Delete" which opens PopupPeer with
        # clear/delete choices; for a 1:1 bot chat this wipes the history.
        page = await self._ready()
        await page.locator(sel.TOPBAR_MENU_BUTTON).last.click()
        # "delete" alone would match the "Auto-delete" menu item first.
        item = page.locator(sel.MENU_ITEM,
                            has_text=re.compile("delete chat|clear history", re.I))
        try:
            await item.first.click(timeout=5_000)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("'Delete Chat'/'Clear history' menu item")
        confirm = page.locator(f".popup:visible {sel.POPUP_DANGER_BUTTON}")
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
