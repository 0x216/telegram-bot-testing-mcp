"""Create the fixture bot by driving @BotFather through the adapter itself.

Doubles as the first live e2e of open_chat/send_message/wait_for_message.
Run with TG_MCP_MODE=test. Prints BOT_TOKEN=... and BOT=@... on success.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession
from telegram_user_mcp.telegram import TelegramOps

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

CANDIDATES = ["tgmcp_fixture_bot", "tgmcp_fixture_0x216_bot", "tgmcp_fixture_e2e_bot"]


async def say_and_wait(ops: TelegramOps, text: str) -> str:
    sent = await ops.send_message(text)
    fresh = await ops.wait_for_message(timeout_s=45, after_id=sent.get("id") or None)
    reply = "\n".join(m["text"] for m in fresh)
    print(f">>> {text}\n<<< {reply[:400]}\n", flush=True)
    return reply


async def main() -> None:
    cfg = Config.from_env({"TG_MCP_MODE": "test"})
    session = BrowserSession(cfg)
    ops = TelegramOps(session)
    try:
        opened = await ops.open_chat("@BotFather")
        print("opened chat:", opened["chat"], f"({len(opened['messages'])} messages visible)")

        reply = await say_and_wait(ops, "/newbot")
        if "Alright" not in reply and "name" not in reply.lower():
            sys.exit(f"unexpected /newbot reply: {reply[:200]}")

        reply = await say_and_wait(ops, "MCP Fixture Bot")
        if "username" not in reply.lower():
            sys.exit(f"unexpected name reply: {reply[:200]}")

        token = None
        username = None
        for cand in CANDIDATES:
            reply = await say_and_wait(ops, cand)
            m = re.search(r"(\d+:[A-Za-z0-9_-]{30,})", reply)
            if m:
                token = m.group(1)
                username = cand
                break
            if "taken" not in reply.lower() and "invalid" not in reply.lower():
                sys.exit(f"unexpected username reply: {reply[:200]}")
        if not token:
            sys.exit("all username candidates rejected")

        png = await ops.screenshot("chat")
        (OUT / "botfather.png").write_bytes(png)
        print(f"BOT=@{username}")
        print(f"BOT_TOKEN={token}")
    finally:
        await session.stop()


asyncio.run(main())
