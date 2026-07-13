"""Autonomous e2e for the headless phone login.

Two sessions of the SAME test account:
  A (reader)  — existing profile-test; opens the "Telegram Notifications"
                service chat and reads the incoming login code.
  B (fresh)   — empty profile; performs login_phone_start / login_submit_code.

Run: python e2e/test_headless_login.py +4207745XXXXX
"""
from __future__ import annotations

import asyncio
import re
import shutil
import sys
from pathlib import Path

from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession
from telegram_user_mcp.telegram import TelegramOps

PHONE = sys.argv[1] if len(sys.argv) > 1 else sys.exit("phone required")
FRESH = Path("e2e/out/headless-profile")

CODE_RE = re.compile(r"(?:login code|код)\D{0,10}(\d{5,6})", re.I)


async def main() -> None:
    shutil.rmtree(FRESH, ignore_errors=True)
    reader = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    fresh = BrowserSession(Config.from_env({
        "TG_MCP_MODE": "test", "TG_MCP_PROFILE_DIR": str(FRESH)}))
    rops = TelegramOps(reader)
    try:
        print("== reader: open service chat")
        opened = await rops.open_chat("Telegram Notifications")
        baseline = max((m["id"] for m in opened["messages"]), default=0)
        print(f"   ok, {len(opened['messages'])} messages, baseline={baseline}")

        print("== fresh: submit phone")
        res = await fresh.login_phone_start(PHONE)
        print("  ", res)
        assert res["status"] == "code_sent", res

        print("== reader: wait for the login code")
        code = None
        fresh_msgs = await rops.wait_for_message(timeout_s=60, after_id=baseline)
        for m in fresh_msgs:
            match = CODE_RE.search(m["text"])
            if match:
                code = match.group(1)
                break
        assert code, f"no code found in: {[m['text'][:60] for m in fresh_msgs]}"
        print(f"   code received: {code}")

        print("== fresh: submit code")
        res = await fresh.login_submit_code(code)
        print("  ", res)
        assert res["status"] == "logged_in", res
        assert await fresh.is_logged_in()
        print("HEADLESS LOGIN E2E: PASS")
    finally:
        await reader.stop()
        await fresh.stop()
        shutil.rmtree(FRESH, ignore_errors=True)  # drop the extra session's profile


asyncio.run(main())
