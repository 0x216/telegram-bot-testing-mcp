"""QA scenario for the Todo Bot — written FROM THE SPEC, the way an agent
would test it for a developer. Catches deviations and saves screenshots.

Run: TG_MCP_MODE=test BOT=@... uv run --with <package> qa_scenario.py
Exit code = number of spec violations found.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BOT = os.environ.get("BOT") or sys.exit("BOT env var required")
OUT = Path(__file__).parent / "qa_out"
OUT.mkdir(exist_ok=True)

findings: list[str] = []
passed: list[str] = []


def verdict(name: str, ok: bool, detail: str = ""):
    (passed if ok else findings).append(f"{name}" + (f" — {detail}" if detail else ""))
    print(f"  {'OK  ' if ok else 'BUG '} {name}" + (f" — {detail}" if detail else ""),
          flush=True)


def parse(res):
    text = res.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, AttributeError):
        return {"error": "non_json", "raw": str(text)[:200]}


def max_id(payload) -> int:
    if isinstance(payload, list):
        return max((m.get("id", 0) for m in payload if isinstance(m, dict)), default=0)
    if isinstance(payload, dict):
        own = payload.get("id", 0) if isinstance(payload.get("id"), int) else 0
        return max(own, max_id(payload.get("messages", [])))
    return 0


def texts(payload) -> str:
    if isinstance(payload, list):
        return "\n".join(m.get("text", "") for m in payload)
    return ""


async def shot(s, name):
    res = await s.call_tool("tg_screenshot", {"scope": "chat"})
    img = next((c for c in res.content if getattr(c, "type", "") == "image"), None)
    if img:
        (OUT / f"{name}.png").write_bytes(base64.b64decode(img.data))


async def wait_reply(s, last, timeout=25):
    fresh = parse(await s.call_tool("tg_wait_for_message",
                                    {"timeout_s": timeout, "after_id": last}))
    if isinstance(fresh, dict):
        return last, fresh  # error payload
    return max(last, max_id(fresh)), fresh


async def main():
    server = StdioServerParameters(command="telegram-bot-testing-mcp", env={**os.environ})
    async with stdio_client(server) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            print("== setup: open chat, clean history")
            opened = parse(await s.call_tool("tg_open_chat", {"query": BOT}))
            assert "error" not in opened, opened
            parse(await s.call_tool("tg_clear_chat", {}))
            opened = parse(await s.call_tool("tg_open_chat", {"query": BOT}))
            last = max_id(opened)

            print("== spec 1: /start -> welcome + 2x2 keyboard [Add,List]/[Done,Help]")
            sent = parse(await s.call_tool("tg_send_message", {"text": "/start"}))
            last = max(last, max_id(sent))
            last, fresh = await wait_reply(s, last)
            welcome = texts(fresh)
            verdict("welcome text present", "Welcome to Todo Bot" in welcome,
                    f"got: {welcome[:80]!r}")
            grid = next((m["buttons"] for m in fresh if isinstance(m, dict) and m.get("buttons")), [])
            verdict("keyboard layout is 2x2 [Add,List]/[Done,Help]",
                    grid == [["Add", "List"], ["Done", "Help"]],
                    f"got rows: {grid}")
            await shot(s, "01-start")

            print("== spec 2: Add flow stores the exact task text")
            clicked = parse(await s.call_tool("tg_click_button", {"text": "Add"}))
            prompt_ok = "Send me a task" in texts(clicked.get("messages", []))
            if not prompt_ok:
                last, fresh = await wait_reply(s, last)
                prompt_ok = "Send me a task" in texts(fresh)
            verdict("Add asks for a task", prompt_ok)
            last = max(last, max_id(clicked))

            task = "Buy milk 🥛 и хлеб"
            sent = parse(await s.call_tool("tg_send_message", {"text": task}))
            last = max(last, max_id(sent))
            last, fresh = await wait_reply(s, last)
            reply = texts(fresh)
            verdict("Added echoes the exact task text", f"Added: {task}" in reply,
                    f"got: {reply[:90]!r}")
            await shot(s, "02-add")

            print("== spec 3: List numbers tasks starting at 1")
            clicked = parse(await s.call_tool("tg_click_button", {"text": "List"}))
            listing = texts(clicked.get("messages", []))
            if "1." not in listing and "0." not in listing:
                last, fresh = await wait_reply(s, last)
                listing = texts(fresh)
            last = max(last, max_id(clicked))
            verdict("List starts numbering at 1", listing.strip().splitlines()
                    and any(line.strip().startswith("1.") for line in listing.splitlines()),
                    f"got: {listing[:90]!r}")
            await shot(s, "03-list")

            print("== spec 4: /help lists the commands")
            sent = parse(await s.call_tool("tg_send_message", {"text": "/help"}))
            last = max(last, max_id(sent))
            last, fresh = await wait_reply(s, last, timeout=15)
            if isinstance(fresh, dict) and fresh.get("error") == "timeout":
                verdict("/help replies", False, "bot stayed silent for 15s")
            else:
                verdict("/help replies", True, texts(fresh)[:60])
            await shot(s, "04-help")

            print("== spec 5: Done completes the first task")
            clicked = parse(await s.call_tool("tg_click_button", {"text": "Done"}))
            done_text = texts(clicked.get("messages", []))
            if "Done:" not in done_text and "Nothing" not in done_text:
                last, fresh = await wait_reply(s, last)
                done_text = texts(fresh)
            verdict("Done completes the stored task", "Done:" in done_text
                    and "Buy milk" in done_text, f"got: {done_text[:90]!r}")
            await shot(s, "05-done")

    print(f"\n=== QA REPORT for {BOT}")
    print(f"passed: {len(passed)}")
    for p in passed:
        print(f"  OK   {p}")
    print(f"violations: {len(findings)}")
    for f in findings:
        print(f"  BUG  {f}")
    sys.exit(len(findings))


asyncio.run(main())
