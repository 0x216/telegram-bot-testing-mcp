"""Create a bot via @BotFather using ONLY the MCP tools (full dogfood).

Run: uv run --with <package> create_bot_mcp.py "Bot Name" username1 [username2 ...]
Env: TG_MCP_MODE=test
Prints BOT=@... and BOT_TOKEN=... on success.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

NAME = sys.argv[1]
CANDIDATES = sys.argv[2:]


def parse(res):
    return json.loads(res.content[0].text)


def max_id(payload) -> int:
    if isinstance(payload, list):
        return max((m.get("id", 0) for m in payload if isinstance(m, dict)), default=0)
    if isinstance(payload, dict):
        own = payload.get("id", 0) if isinstance(payload.get("id"), int) else 0
        return max(own, max_id(payload.get("messages", [])))
    return 0


async def say(s, last, text):
    sent = parse(await s.call_tool("tg_send_message", {"text": text}))
    if "error" in sent:
        sys.exit(f"send failed: {sent}")
    last = max(last, max_id(sent))
    fresh = parse(await s.call_tool("tg_wait_for_message",
                                    {"timeout_s": 45, "after_id": last}))
    if isinstance(fresh, dict) and "error" in fresh:
        sys.exit(f"wait failed: {fresh}")
    reply = "\n".join(m.get("text", "") for m in fresh)
    print(f">>> {text}\n<<< {reply[:250]}\n", flush=True)
    return max(last, max_id(fresh)), reply


async def main():
    server = StdioServerParameters(command="telegram-bot-testing-mcp", env={**os.environ})
    async with stdio_client(server) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            opened = parse(await s.call_tool("tg_open_chat", {"query": "@BotFather"}))
            if "error" in opened:
                sys.exit(f"open_chat failed: {opened}")
            last = max_id(opened)

            last, reply = await say(s, last, "/newbot")
            if "name" not in reply.lower():
                sys.exit(f"unexpected /newbot reply: {reply[:150]}")
            last, reply = await say(s, last, NAME)
            if "username" not in reply.lower():
                sys.exit(f"unexpected name reply: {reply[:150]}")
            for cand in CANDIDATES:
                last, reply = await say(s, last, cand)
                m = re.search(r"(\d+:[A-Za-z0-9_-]{30,})", reply)
                if m:
                    print(f"BOT=@{cand}")
                    print(f"BOT_TOKEN={m.group(1)}")
                    return
                if "taken" not in reply.lower() and "invalid" not in reply.lower():
                    sys.exit(f"unexpected username reply: {reply[:150]}")
            sys.exit("all username candidates rejected")


asyncio.run(main())
