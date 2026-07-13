from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from .config import Config
from .errors import AdapterError
from .miniapp import MiniAppOps
from .session import BrowserSession
from .telegram import TelegramOps


def build_server(config: Config | None = None) -> FastMCP:
    cfg = config or Config.from_env()
    mcp = FastMCP("telegram-user")
    state: dict[str, Any] = {}

    def session() -> BrowserSession:
        if "session" not in state:
            state["session"] = BrowserSession(cfg)
        return state["session"]

    def ops() -> TelegramOps:
        if "ops" not in state:
            state["ops"] = TelegramOps(session())
        return state["ops"]

    def apps() -> MiniAppOps:
        if "apps" not in state:
            state["apps"] = MiniAppOps(session())
        return state["apps"]

    def _json(data) -> str:
        return json.dumps(data, ensure_ascii=False)

    @mcp.tool()
    async def tg_status() -> str:
        """Report adapter mode, login state and profile location."""
        has_profile = (cfg.profile_dir / "Default").exists()
        logged_in = False
        if has_profile:
            try:
                logged_in = await session().is_logged_in()
            except AdapterError as e:
                return _json(e.to_payload())
        return _json({"mode": cfg.mode, "logged_in": logged_in,
                      "profile_dir": str(cfg.profile_dir)})

    @mcp.tool()
    async def tg_login(timeout_s: int = 300) -> str:
        """Open a visible browser window for one-time Telegram login (QR or phone).
        The session persists in the profile afterwards."""
        try:
            return _json(await session().login_interactive(timeout_s))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_open_chat(query: str) -> str:
        """Open a chat by @username or t.me link. Returns the last messages."""
        try:
            return _json(await ops().open_chat(query))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_send_message(text: str) -> str:
        """Send a text message or /command to the currently open chat."""
        try:
            return _json(await ops().send_message(text))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_send_file(path: str, caption: str = "") -> str:
        """Attach and send a file (photo/document) to the open chat."""
        try:
            return _json(await ops().send_file(path, caption or None))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_read_messages(limit: int = 20) -> str:
        """Read the last messages of the open chat as structured JSON
        (id, direction, text, time, button grid, media kind)."""
        try:
            return _json(await ops().read_messages(limit))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_wait_for_message(timeout_s: float = 30, after_id: int = 0) -> str:
        """Block until the bot sends something new (the core test primitive).
        Returns the new incoming messages."""
        try:
            return _json(await ops().wait_for_message(timeout_s, after_id or None))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_click_button(text: str = "", row: int = -1, col: int = -1,
                              message_id: int = 0) -> str:
        """Click an inline-keyboard button by text substring, or by 0-based row/col.
        Targets message_id or the last message that has buttons."""
        try:
            return _json(await ops().click_button(
                text or None, row if row >= 0 else None,
                col if col >= 0 else None, message_id or None))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_click_reply_button(text: str) -> str:
        """Click a reply-keyboard button (the keyboard shown near the input)."""
        try:
            return _json(await ops().click_reply_button(text))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_clear_chat() -> str:
        """Clear the open chat's history (test isolation between scenarios)."""
        try:
            return _json(await ops().clear_chat())
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_screenshot(scope: str = "chat", message_id: int = 0):
        """Screenshot the chat, a single message (scope='message' + message_id),
        or the whole window (scope='window')."""
        try:
            png = await ops().screenshot(scope, message_id or None)
            return Image(data=png, format="png")
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_miniapp_open(button_text: str = "") -> str:
        """Open a Mini App via a web-app button on the last message (or by text)."""
        try:
            return _json(await apps().open(button_text or None))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_miniapp_snapshot(max_elements: int = 150) -> str:
        """List interactive elements inside the open Mini App as [ref] lines
        usable with tg_miniapp_click / tg_miniapp_type."""
        try:
            return await apps().snapshot(max_elements)
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_miniapp_click(ref: str) -> str:
        """Click an element inside the Mini App by its snapshot ref (e.g. 'e3')."""
        try:
            return _json(await apps().click(ref))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_miniapp_type(ref: str, text: str) -> str:
        """Type text into a Mini App input by its snapshot ref."""
        try:
            return _json(await apps().type(ref, text))
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_miniapp_screenshot():
        """Screenshot the open Mini App."""
        try:
            return Image(data=await apps().screenshot(), format="png")
        except AdapterError as e:
            return _json(e.to_payload())

    @mcp.tool()
    async def tg_miniapp_close() -> str:
        """Close the open Mini App popup."""
        try:
            return _json(await apps().close())
        except AdapterError as e:
            return _json(e.to_payload())

    return mcp


mcp = build_server()
