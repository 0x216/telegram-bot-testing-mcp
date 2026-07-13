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

    async def _run(coro) -> str:
        """Every tool returns JSON — never a raw traceback across MCP."""
        try:
            return _json(await coro)
        except AdapterError as e:
            return _json(e.to_payload())
        except Exception as e:
            return _json({"error": "internal",
                          "message": f"{type(e).__name__}: {e}",
                          "hint": "Unexpected UI state; use tg_screenshot to inspect."})

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
        return await _run(session().login_interactive(timeout_s))

    @mcp.tool()
    async def tg_login_phone(phone: str) -> str:
        """Headless login step 1: submit the phone number. The code arrives on
        the account's other logged-in devices (or SMS); pass it to tg_login_code."""
        return await _run(session().login_phone_start(phone))

    @mcp.tool()
    async def tg_login_code(code: str) -> str:
        """Headless login step 2: submit the confirmation code. May return
        password_needed for 2FA accounts (then call tg_login_password)."""
        return await _run(session().login_submit_code(code))

    @mcp.tool()
    async def tg_login_password(password: str) -> str:
        """Headless login step 3: submit the two-factor password (2FA only)."""
        return await _run(session().login_submit_password(password))

    @mcp.tool()
    async def tg_open_chat(query: str) -> str:
        """Open a chat by @username or t.me link. Returns the last messages."""
        return await _run(ops().open_chat(query))

    @mcp.tool()
    async def tg_send_message(text: str) -> str:
        """Send a text message or /command to the currently open chat."""
        return await _run(ops().send_message(text))

    @mcp.tool()
    async def tg_send_file(path: str, caption: str = "", kind: str = "auto") -> str:
        """Attach and send a file to the open chat.
        kind: auto (by extension) | photo | document."""
        return await _run(ops().send_file(path, caption or None, kind))

    @mcp.tool()
    async def tg_read_messages(limit: int = 20) -> str:
        """Read the last messages of the open chat as structured JSON
        (id, direction, text, time, button grid, media kind)."""
        return await _run(ops().read_messages(limit))

    @mcp.tool()
    async def tg_wait_for_message(timeout_s: float = 30, after_id: int = 0) -> str:
        """Block until the bot sends something new (the core test primitive).
        Returns the new incoming messages."""
        return await _run(ops().wait_for_message(timeout_s, after_id or None))

    @mcp.tool()
    async def tg_click_button(text: str = "", row: int = -1, col: int = -1,
                              message_id: int = 0) -> str:
        """Click an inline-keyboard button by text substring, or by 0-based row/col.
        Targets message_id or the last message that has buttons."""
        return await _run(ops().click_button(
            text or None, row if row >= 0 else None,
            col if col >= 0 else None, message_id or None))

    @mcp.tool()
    async def tg_click_reply_button(text: str) -> str:
        """Click a reply-keyboard button (the keyboard shown near the input)."""
        return await _run(ops().click_reply_button(text))

    @mcp.tool()
    async def tg_clear_chat() -> str:
        """Clear the open chat's history (test isolation between scenarios)."""
        return await _run(ops().clear_chat())

    @mcp.tool()
    async def tg_screenshot(scope: str = "chat", message_id: int = 0):
        """Screenshot the chat, a single message (scope='message' + message_id),
        or the whole window (scope='window')."""
        try:
            png = await ops().screenshot(scope, message_id or None)
            return Image(data=png, format="png")
        except AdapterError as e:
            return _json(e.to_payload())
        except Exception as e:
            return _json({"error": "internal", "message": f"{type(e).__name__}: {e}",
                          "hint": "Unexpected UI state."})

    @mcp.tool()
    async def tg_miniapp_open(button_text: str = "") -> str:
        """Open a Mini App via a web-app button on the last message (or by text)."""
        return await _run(apps().open(button_text or None))

    @mcp.tool()
    async def tg_miniapp_snapshot(max_elements: int = 150) -> str:
        """List interactive elements inside the open Mini App as [ref] lines
        usable with tg_miniapp_click / tg_miniapp_type."""
        try:
            return await apps().snapshot(max_elements)
        except AdapterError as e:
            return _json(e.to_payload())
        except Exception as e:
            return _json({"error": "internal", "message": f"{type(e).__name__}: {e}",
                          "hint": "Unexpected UI state."})

    @mcp.tool()
    async def tg_miniapp_click(ref: str) -> str:
        """Click an element inside the Mini App by its snapshot ref (e.g. 'e3')."""
        return await _run(apps().click(ref))

    @mcp.tool()
    async def tg_miniapp_type(ref: str, text: str) -> str:
        """Type text into a Mini App input by its snapshot ref."""
        return await _run(apps().type(ref, text))

    @mcp.tool()
    async def tg_miniapp_screenshot():
        """Screenshot the open Mini App."""
        try:
            return Image(data=await apps().screenshot(), format="png")
        except AdapterError as e:
            return _json(e.to_payload())
        except Exception as e:
            return _json({"error": "internal", "message": f"{type(e).__name__}: {e}",
                          "hint": "Unexpected UI state."})

    @mcp.tool()
    async def tg_miniapp_close() -> str:
        """Close the open Mini App popup."""
        return await _run(apps().close())

    return mcp


mcp = build_server()
