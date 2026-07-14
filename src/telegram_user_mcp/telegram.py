from __future__ import annotations

import asyncio
import re

from . import extract
from . import js
from . import selectors as sel
from . import timings as tm
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

    async def _type_into_search(self, page, text: str) -> bool:
        search = page.locator(sel.SEARCH_INPUT).first
        await search.wait_for(state="visible", timeout=tm.BOOT_TIMEOUT_MS)
        await search.click()
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
        await page.keyboard.type(text, delay=tm.TYPE_DELAY_MS)
        await asyncio.sleep(tm.UI_SETTLE_S)
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
        for _attempt in range(tm.SEARCH_ROUNDS):
            if _attempt:
                await page.keyboard.press("Escape")
                await asyncio.sleep(tm.SPA_RETRY_PAUSE_S)
            if not await self._type_into_search(page, username):
                await asyncio.sleep(tm.SPA_RETRY_PAUSE_S)  # SPA not ready yet
                continue
            deadline = loop.time() + tm.SEARCH_ROUND_TIMEOUT_S
            while loop.time() < deadline:
                idx = await page.evaluate(js.FIND_SEARCH_ROW, {
                    "rowSel": sel.SEARCH_RESULT_ROW, "username": username,
                    "byTitle": by_title,
                })
                if idx >= 0:
                    break
                await asyncio.sleep(tm.POLL_S)
            if idx >= 0:
                break
        if idx < 0:
            await page.keyboard.press("Escape")
            raise ChatNotFound(query)
        await page.locator(sel.SEARCH_RESULT_ROW).nth(idx).click()
        try:
            await page.wait_for_selector(f"{sel.ACTIVE_CHAT} {sel.MESSAGE_INPUT}",
                                         state="visible",
                                         timeout=tm.CHAT_OPEN_TIMEOUT_MS)
        except Exception:
            raise SelectorBroken("message composer after opening the chat")
        await asyncio.sleep(tm.HISTORY_RENDER_S)
        self._current_chat = query
        msgs = await extract.read_messages(page, limit=5)
        return {"chat": username, "messages": [m.to_dict() for m in msgs]}

    async def read_messages(self, limit: int = 20) -> list[dict]:
        page = await self._ready()
        return [m.to_dict() for m in await extract.read_messages(page, limit=limit)]

    async def _press_start_if_needed(self, page) -> bool:
        # Un-started bot chats cover the composer with a START control;
        # pressing it is Telegram's way of sending /start.
        ctl = page.locator(f"{sel.ACTIVE_CHAT} {sel.START_CONTROL}")
        if await ctl.count() and await ctl.first.is_visible():
            btn = ctl.first.locator("button:visible")
            target = btn.first if await btn.count() else ctl.first
            await target.click()
            await asyncio.sleep(tm.START_OVERLAY_S)
            return True
        return False

    async def _open_bubble_menu_item(self, page, message_id: int, item_text: str):
        bubble = page.locator(
            f'{sel.ACTIVE_CHAT} {sel.BUBBLE}[data-mid="{message_id}"]')
        if not await bubble.count():
            raise ChatNotFound(f"message {message_id}")
        await bubble.first.click(button="right")
        item = page.locator(sel.MENU_ITEM, has_text=item_text)
        try:
            await item.first.click(timeout=tm.MENU_ITEM_TIMEOUT_MS)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken(f"{item_text!r} in the message context menu")
        await asyncio.sleep(tm.UI_SETTLE_S)

    async def send_message(self, text: str, reply_to: int | None = None) -> dict:
        page = await self._ready()
        # Identical texts may already exist in history; only bubbles newer than
        # this baseline count as "our" send. sort_id keeps fractional pending
        # mids (208.0001) distinguishable from their integer neighbours.
        before_max = max((m.sort_id for m in await extract.read_messages(page, limit=10)),
                         default=0.0)
        if reply_to is not None:
            await self._open_bubble_menu_item(page, reply_to, sel.TEXT_MENU_REPLY)
        started = await self._press_start_if_needed(page)
        if started and text.strip().lower() == "/start":
            msgs = await extract.read_messages(page, limit=5)
            mine = [m for m in msgs if m.out and m.sort_id > before_max]
            if mine:
                return mine[-1].to_dict()
        composer = f"{sel.ACTIVE_CHAT} {sel.MESSAGE_INPUT}"
        for _attempt in range(3):
            current = await page.evaluate(js.COMPOSER, {"sel": composer, "focus": True})
            if current is None:
                raise SelectorBroken("message input (is a chat open?)")
            if current.strip():
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Delete")
            # insert_text (not type): emoji and other astral-plane chars are
            # silently dropped by synthesized keydown events
            await page.keyboard.insert_text(text)
            await asyncio.sleep(tm.UI_SETTLE_S)
            typed = await page.evaluate(js.COMPOSER, {"sel": composer, "focus": False})
            if typed is not None and typed.strip() == text.strip():
                break
        else:
            raise SelectorBroken("composer did not accept the typed text")
        await page.keyboard.press("Enter")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + tm.SEND_CONFIRM_TIMEOUT_S
        pending_seen = False
        while loop.time() < deadline:
            msgs = await extract.read_messages(page, limit=10)
            mine = [m for m in msgs if m.out and text.strip() in m.text
                    and m.sort_id > before_max]
            if any(m.failed for m in mine):
                raise AdapterError("Telegram marked the message as failed (is-error).",
                                   hint="Check the connection/session and retry.")
            delivered = [m for m in mine if not m.sending]
            if delivered:
                return min(delivered, key=lambda m: m.sort_id).to_dict()
            pending_seen = pending_seen or bool(mine)
            await asyncio.sleep(tm.POLL_FAST_S)
        if pending_seen:
            raise AdapterError(
                "Message is stuck in the 'sending' state — Telegram did not "
                "acknowledge it in time.",
                hint="Connection or session problem; check tg_status, or re-login.")
        raise SelectorBroken("sent message bubble")

    async def wait_for_message(self, timeout_s: float = tm.WAIT_MESSAGE_DEFAULT_S,
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
            await asyncio.sleep(tm.POLL_S)
        raise WaitTimeout(timeout_s)

    # -- buttons ---------------------------------------------------------

    async def click_button(self, text: str | None = None, row: int | None = None,
                           col: int | None = None, message_id: int | None = None) -> dict:
        page = await self._ready()
        buttons = await page.evaluate(js.INLINE_BUTTONS, {
            "mid": message_id, "bubbleSel": f"{sel.ACTIVE_CHAT} {sel.BUBBLE}",
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
        bubble = page.locator(f'{sel.ACTIVE_CHAT} {sel.BUBBLE}[data-mid="{target["mid"]}"]')
        await bubble.locator(sel.INLINE_BUTTON).nth(buttons.index(target)).click()
        await asyncio.sleep(tm.CALLBACK_SETTLE_S)
        msgs = await extract.read_messages(page, limit=5)
        return {"clicked": target["text"], "messages": [m.to_dict() for m in msgs]}

    async def click_reply_button(self, text: str) -> dict:
        page = await self._ready()
        before_max = max((m.sort_id for m in await extract.read_messages(page, limit=10)),
                         default=0.0)
        loop = asyncio.get_event_loop()
        labels: list[str] = []
        # Pressing a reply button sends its label as a message; verify the
        # outgoing bubble actually appeared and retry once if the click was
        # swallowed mid-render.
        for _attempt in range(2):
            kb = page.locator(f"{sel.ACTIVE_CHAT} {sel.REPLY_KEYBOARD}:visible")
            if not await kb.count():
                toggle = page.locator(f"{sel.ACTIVE_CHAT} {sel.REPLY_KEYBOARD_TOGGLE}")
                if await toggle.count():
                    await toggle.first.click()
                    await asyncio.sleep(tm.KEYBOARD_TOGGLE_S)
            buttons = page.locator(
                f"{sel.ACTIVE_CHAT} {sel.REPLY_KEYBOARD} {sel.REPLY_KEYBOARD_BUTTON}")
            labels = []
            for i in range(await buttons.count()):
                labels.append((await buttons.nth(i).inner_text()).strip())
            target = next((i for i, lbl in enumerate(labels)
                           if text.lower() in lbl.lower()), None)
            if target is None:
                continue
            await buttons.nth(target).click()
            deadline = loop.time() + tm.REPLY_CLICK_CONFIRM_S
            while loop.time() < deadline:
                msgs = await extract.read_messages(page, limit=5)
                if any(m.out and not m.sending and m.sort_id > before_max
                       and labels[target].lower() in m.text.lower() for m in msgs):
                    await asyncio.sleep(tm.MID_SETTLE_S)
                    msgs = await extract.read_messages(page, limit=5)
                    return {"clicked": labels[target],
                            "messages": [m.to_dict() for m in msgs]}
                await asyncio.sleep(tm.POLL_FAST_S)
        if labels and any(text.lower() in lbl.lower() for lbl in labels):
            raise SelectorBroken(f"reply button {text!r} click did not send a message")
        raise ButtonNotFound(text, labels)

    # -- files / misc ----------------------------------------------------

    async def send_file(self, path: str, caption: str | None = None,
                        kind: str = "auto") -> dict:
        page = await self._ready()
        before = {m.sort_id for m in await extract.read_messages(page, limit=10) if m.out}
        if kind == "auto":
            kind = "photo" if path.lower().rsplit(".", 1)[-1] in (
                "png", "jpg", "jpeg", "gif", "webp", "mp4", "mov") else "document"
        # Feeding the hidden input directly skips WebK's willAttachType state,
        # so go through the attach menu and catch the native file chooser.
        await page.keyboard.press("Escape")  # dismiss any lingering overlay
        await asyncio.sleep(tm.UI_SETTLE_S)
        await page.locator(f"{sel.ACTIVE_CHAT} {sel.ATTACH_BUTTON}").last.click()
        pattern = re.compile("photo|video" if kind == "photo" else "document|file", re.I)
        item = page.locator(sel.MENU_ITEM, has_text=pattern).first
        try:
            async with page.expect_file_chooser(timeout=tm.FILE_CHOOSER_TIMEOUT_MS) as fc_info:
                await item.click(timeout=tm.MENU_ITEM_TIMEOUT_MS)
            chooser = await fc_info.value
            await chooser.set_files(path)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("attach menu / file chooser")
        try:
            await page.wait_for_selector(sel.ATTACH_POPUP, state="visible",
                                         timeout=tm.ATTACH_POPUP_TIMEOUT_MS)
        except Exception:
            raise SelectorBroken("attach confirmation popup")
        if caption:
            cap = page.locator(f"{sel.ATTACH_POPUP} {sel.MESSAGE_INPUT}:visible")
            if await cap.count():
                await cap.first.click()
                await page.keyboard.insert_text(caption)
        await page.locator(sel.ATTACH_POPUP_SEND).click()
        loop = asyncio.get_event_loop()
        deadline = loop.time() + tm.UPLOAD_CONFIRM_TIMEOUT_S
        while loop.time() < deadline:
            msgs = await extract.read_messages(page, limit=10)
            fresh = [m for m in msgs if m.out and not m.sending
                     and m.sort_id not in before]
            if fresh:
                return fresh[-1].to_dict()
            await asyncio.sleep(tm.POLL_S)
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
        before_max = max((m.sort_id for m in await extract.read_messages(page, limit=10)),
                         default=0.0)
        record = page.locator(f"{sel.ACTIVE_CHAT} {sel.SEND_BUTTON}:visible").last
        if not await record.count():
            raise SelectorBroken("record (mic) button")
        await record.click()  # composer is empty -> starts recording
        await asyncio.sleep(min(duration_s + tm.KEYBOARD_TOGGLE_S, tm.VOICE_MAX_RECORD_S))
        await page.locator(f"{sel.ACTIVE_CHAT} {sel.SEND_BUTTON}:visible").last.click()  # send
        loop = asyncio.get_event_loop()
        deadline = loop.time() + tm.VOICE_CONFIRM_TIMEOUT_S
        while loop.time() < deadline:
            msgs = await extract.read_messages(page, limit=5)
            mine = [m for m in msgs if m.out and not m.sending
                    and m.sort_id > before_max and m.media in ("voice", "audio")]
            if mine:
                return mine[-1].to_dict()
            await asyncio.sleep(tm.POLL_S)
        raise SelectorBroken("sent voice bubble (recording may have failed)")

    async def forward_message(self, message_id: int, to_chat: str | None = None) -> dict:
        """Forward a message via the picker. Default target: the current chat
        (forwarding a bot's message back to it is the common test loop)."""
        page = await self._ready()
        if to_chat is None:
            title_el = page.locator(f"{sel.ACTIVE_CHAT} {sel.TOPBAR_TITLE}").first
            to_chat = (await title_el.inner_text()).strip()
        before_max = max((m.sort_id for m in await extract.read_messages(page, limit=10)),
                         default=0.0)
        await self._open_bubble_menu_item(page, message_id, sel.TEXT_MENU_FORWARD)
        try:
            await page.wait_for_selector(sel.FWD_PICKER_SEARCH, state="visible",
                                         timeout=tm.MENU_ITEM_TIMEOUT_MS)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("forward picker")
        await page.locator(sel.FWD_PICKER_SEARCH).first.click()
        await page.keyboard.type(to_chat, delay=tm.TYPE_DELAY_MS)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + tm.SEARCH_ROUND_TIMEOUT_S
        idx = -1
        while loop.time() < deadline:
            idx = await page.evaluate(js.FIND_SEARCH_ROW, {
                "rowSel": sel.FWD_PICKER_ROW, "username": to_chat, "byTitle": True,
            })
            if idx >= 0:
                break
            await asyncio.sleep(tm.POLL_S)
        if idx < 0:
            await page.keyboard.press("Escape")
            raise ChatNotFound(to_chat)
        await page.locator(sel.FWD_PICKER_ROW).nth(idx).click()
        try:
            await page.locator(sel.FWD_CONFIRM).first.click(
                timeout=tm.MENU_ITEM_TIMEOUT_MS)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("forward confirm button")
        # the picker fades out asynchronously; don't leave it intercepting
        # the next operation's clicks
        try:
            await page.wait_for_selector(sel.FWD_PICKER_SEARCH, state="hidden",
                                         timeout=tm.MENU_ITEM_TIMEOUT_MS)
        except Exception:
            await page.keyboard.press("Escape")
        deadline = loop.time() + tm.SEND_CONFIRM_TIMEOUT_S
        while loop.time() < deadline:
            msgs = await extract.read_messages(page, limit=10)
            fresh = [m for m in msgs if m.out and not m.sending
                     and m.sort_id > before_max]
            if fresh:
                return fresh[-1].to_dict()
            await asyncio.sleep(tm.POLL_S)
        return {"status": "forwarded",
                "note": "target chat is not the current one; bubble not visible here"}

    async def clear_chat(self) -> dict:
        # WebK's topbar menu offers "Delete" which opens PopupPeer with
        # clear/delete choices; for a 1:1 bot chat this wipes the history.
        page = await self._ready()
        await page.locator(f"{sel.ACTIVE_CHAT} {sel.TOPBAR_MENU_BUTTON}").last.click()
        # Matches the English label OR the locale-independent icon glyph;
        # plain "delete" would hit the "Auto-delete" item first.
        item = page.locator(sel.MENU_ITEM,
                            has_text=re.compile(sel.TEXT_DELETE_MENU, re.I))
        try:
            await item.first.click(timeout=tm.MENU_ITEM_TIMEOUT_MS)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("'Delete Chat'/'Clear history' menu item")
        confirm = page.locator(f".popup:visible {sel.POPUP_DANGER_BUTTON}")
        try:
            await confirm.first.click(timeout=tm.MENU_ITEM_TIMEOUT_MS)
        except Exception:
            await page.keyboard.press("Escape")
            raise SelectorBroken("delete/clear confirmation button")
        await asyncio.sleep(tm.MENU_OPEN_S)
        return {"status": "cleared"}

    async def screenshot(self, scope: str = "chat", message_id: int | None = None) -> bytes:
        page = await self._ready()
        if scope == "message" and message_id is not None:
            loc = page.locator(f'{sel.ACTIVE_CHAT} {sel.BUBBLE}[data-mid="{message_id}"]')
            if await loc.count():
                return await loc.screenshot()
            raise SelectorBroken(f"message bubble {message_id}")
        if scope == "chat":
            loc = page.locator(f"{sel.ACTIVE_CHAT} {sel.CHAT_CONTAINER}")
            if await loc.count():
                return await loc.screenshot()
        return await page.screenshot()
