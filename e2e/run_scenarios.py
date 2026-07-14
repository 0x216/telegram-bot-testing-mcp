"""E2E scenario runner: drives the MCP server as a real client.

Prereqs:
  * profile logged in (telegram-bot-testing-mcp login), matching TG_MCP_MODE
  * fixture bot running (e2e/fixture_bot.py with BOT_TOKEN)
  * BOT env var = @username of the fixture bot

Run: BOT=@my_fixture_bot python e2e/run_scenarios.py
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

BOT = os.environ.get("BOT") or sys.exit("BOT env var required (@username of fixture bot)")
OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

PASS, FAIL = 0, 0


def check(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    PASS += ok
    FAIL += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail and not ok else ""),
          flush=True)


def parse(res) -> dict | list:
    text = res.content[0].text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, AttributeError):
        return {"error": "non_json_tool_result", "raw": str(text)[:300]}


def max_id(payload) -> int:
    """Largest message id anywhere in a tool result."""
    if isinstance(payload, list):
        return max((m.get("id", 0) for m in payload if isinstance(m, dict)), default=0)
    if isinstance(payload, dict):
        own = payload.get("id", 0) if isinstance(payload.get("id"), int) else 0
        return max(own, max_id(payload.get("messages", [])))
    return 0


async def main() -> None:
    server = StdioServerParameters(
        command=sys.executable, args=["-m", "telegram_user_mcp.cli"],
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    async with stdio_client(server) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("== status")
            st = parse(await s.call_tool("tg_status", {}))
            check("logged in", st.get("logged_in") is True, json.dumps(st))
            if not st.get("logged_in"):
                sys.exit("run `telegram-bot-testing-mcp login` first")

            print("== open chat")
            opened = parse(await s.call_tool("tg_open_chat", {"query": BOT}))
            check("chat opened", "error" not in opened, json.dumps(opened)[:200])

            print("== clear history (test isolation)")
            cleared = parse(await s.call_tool("tg_clear_chat", {}))
            check("cleared", cleared.get("status") == "cleared", json.dumps(cleared)[:200])
            opened = parse(await s.call_tool("tg_open_chat", {"query": BOT}))
            check("chat reopened", "error" not in opened, json.dumps(opened)[:200])
            last = max_id(opened)

            print("== /start -> inline keyboard")
            sent = parse(await s.call_tool("tg_send_message", {"text": "/start"}))
            check("message sent", "error" not in sent, json.dumps(sent)[:200])
            last = max(last, max_id(sent))
            fresh = parse(await s.call_tool("tg_wait_for_message",
                                            {"timeout_s": 30, "after_id": last}))
            ok = isinstance(fresh, list) and any(m.get("buttons") for m in fresh)
            check("bot replied with keyboard", ok, json.dumps(fresh)[:300])
            grid = next((m["buttons"] for m in fresh if m.get("buttons")), []) if ok else []
            check("keyboard is 2x2", grid == [["A1", "A2"], ["B1", "B2"]], str(grid))
            last = max(last, max_id(fresh))

            print("== click A2 -> message edited")
            clicked = parse(await s.call_tool("tg_click_button", {"text": "A2"}))
            check("clicked", clicked.get("clicked") == "A2", json.dumps(clicked)[:200])
            await asyncio.sleep(2)
            msgs = parse(await s.call_tool("tg_read_messages", {"limit": 5}))
            edited = any("you pressed A2" in m.get("text", "") for m in msgs)
            check("edit landed", edited, json.dumps(msgs)[:300])
            last = max(last, max_id(msgs))

            print("== echo")
            sent = parse(await s.call_tool("tg_send_message", {"text": "hello e2e"}))
            last = max(last, max_id(sent))
            fresh = parse(await s.call_tool("tg_wait_for_message",
                                            {"timeout_s": 30, "after_id": last}))
            ok = isinstance(fresh, list) and any("echo: hello e2e" in m.get("text", "") for m in fresh)
            check("echo received", ok, json.dumps(fresh)[:300])
            last = max(last, max_id(fresh))

            print("== reply keyboard")
            sent = parse(await s.call_tool("tg_send_message", {"text": "/kb"}))
            last = max(last, max_id(sent))
            fresh = parse(await s.call_tool("tg_wait_for_message",
                                            {"timeout_s": 30, "after_id": last}))
            last = max(last, max_id(fresh))
            picked = parse(await s.call_tool("tg_click_reply_button", {"text": "Red"}))
            check("reply button clicked", picked.get("clicked") == "Red", json.dumps(picked)[:200])
            # the bot may reply fast enough to land inside the click result
            ok = any("echo: Red" in m.get("text", "") for m in picked.get("messages", []))
            if not ok:
                fresh = parse(await s.call_tool("tg_wait_for_message",
                                                {"timeout_s": 30, "after_id": last}))
                ok = isinstance(fresh, list) and any("echo: Red" in m.get("text", "") for m in fresh)
                last = max(last, max_id(fresh))
            check("reply press echoed", ok, json.dumps(picked)[:300])
            last = max(last, max_id(picked))

            print("== photo from bot")
            sent = parse(await s.call_tool("tg_send_message", {"text": "/photo"}))
            last = max(last, max_id(sent))
            fresh = parse(await s.call_tool("tg_wait_for_message",
                                            {"timeout_s": 30, "after_id": last}))
            ok = isinstance(fresh, list) and any(m.get("media") == "photo" for m in fresh)
            check("photo detected", ok, json.dumps(fresh)[:300])
            last = max(last, max_id(fresh))

            print("== rich content from bot")

            async def command_reply(cmd, timeout=30):
                nonlocal last
                sent = parse(await s.call_tool("tg_send_message", {"text": cmd}))
                last = max(last, max_id(sent))
                fresh = parse(await s.call_tool("tg_wait_for_message",
                                                {"timeout_s": timeout, "after_id": last}))
                if isinstance(fresh, list):
                    last = max(last, max_id(fresh))
                    return fresh
                return []

            fresh = await command_reply("/reply")
            if not any(m.get("reply_to") for m in fresh):
                extra = parse(await s.call_tool("tg_wait_for_message",
                                                {"timeout_s": 15, "after_id": last}))
                if isinstance(extra, list):
                    fresh += extra
                    last = max(last, max_id(extra))
            replied = next((m for m in fresh if m.get("reply_to")), None)
            check("reply attribution extracted",
                  bool(replied) and replied["reply_to"].get("quote") == "reply target",
                  json.dumps(fresh)[:250])

            fresh = await command_reply("/forwarded")
            fwd = next((m for m in fresh if m.get("forwarded_from")), None)
            check("forward header extracted",
                  bool(fwd) and "Fixture" in fwd["forwarded_from"],
                  json.dumps(fresh)[:250])

            fresh = await command_reply("/location")
            check("location detected",
                  any(m.get("media") == "location" for m in fresh),
                  json.dumps(fresh)[:250])

            fresh = await command_reply("/venue")
            venue = next((m for m in fresh if m.get("media") == "venue"), None)
            check("venue detected with title",
                  bool(venue) and "Eiffel Tower" in venue.get("text", ""),
                  json.dumps(fresh)[:250])

            fresh = await command_reply("/contact")
            contact = next((m for m in fresh if m.get("media") == "contact"), None)
            check("contact detected with name",
                  bool(contact) and "Fixture Contact" in contact.get("text", ""),
                  json.dumps(fresh)[:250])

            fresh = await command_reply("/poll")
            poll = next((m for m in fresh if m.get("media") == "poll"), None)
            check("poll question and options extracted",
                  bool(poll) and poll.get("poll", {}).get("question") == "favorite color?"
                  and poll["poll"].get("options") == ["Red", "Green", "Blue"],
                  json.dumps(fresh)[:300])

            fresh = await command_reply("/gif")
            check("gif/animation detected (as video)",
                  any(m.get("media") == "video" for m in fresh),
                  json.dumps(fresh)[:250])

            print("== send file to bot")
            tiny = OUT / "upload.png"
            if not tiny.exists():
                import struct
                import zlib

                def chunk(tag: bytes, data: bytes) -> bytes:
                    return (struct.pack(">I", len(data)) + tag + data
                            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

                raw = b"".join(b"\x00" + b"\x00\x80\xff" * 4 for _ in range(4))
                tiny.write_bytes(
                    b"\x89PNG\r\n\x1a\n"
                    + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(raw))
                    + chunk(b"IEND", b""))
            up = parse(await s.call_tool("tg_send_file",
                                         {"path": str(tiny), "caption": "here"}))
            check("file sent", "error" not in up, json.dumps(up)[:200])
            last = max(last, max_id(up))
            fresh = parse(await s.call_tool("tg_wait_for_message",
                                            {"timeout_s": 30, "after_id": last}))
            ok = isinstance(fresh, list) and any("got your photo" in m.get("text", "")
                                                 or "got your document" in m.get("text", "") for m in fresh)
            check("bot confirmed upload", ok, json.dumps(fresh)[:300])

            print("== voice message via fake microphone")
            tone = OUT / "tone.wav"
            if not tone.exists():
                import math
                import struct as _struct
                import wave

                with wave.open(str(tone), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(16000)
                    frames = b"".join(
                        _struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * t / 16000)))
                        for t in range(int(16000 * 2.0)))
                    w.writeframes(frames)
            voiced = parse(await s.call_tool("tg_send_voice", {"path": str(tone)}))
            check("voice sent", "error" not in voiced and voiced.get("media") in ("voice", "audio"),
                  json.dumps(voiced)[:250])
            last = max(last, max_id(voiced))
            fresh = parse(await s.call_tool("tg_wait_for_message",
                                            {"timeout_s": 30, "after_id": last}))
            ok = isinstance(fresh, list) and any("got your voice" in m.get("text", "") for m in fresh)
            check("bot confirmed voice", ok, json.dumps(fresh)[:300])
            last = max(last, max_id(fresh))

            print("== mini app")
            import re as _re
            sent = parse(await s.call_tool("tg_send_message", {"text": "/app"}))
            last = max(last, max_id(sent))
            fresh = parse(await s.call_tool("tg_wait_for_message",
                                            {"timeout_s": 30, "after_id": last}))
            last = max(last, max_id(fresh))
            opened = parse(await s.call_tool("tg_miniapp_open", {"button_text": "Open App"}))
            check("mini app opened", opened.get("status") in ("open", "already_open"),
                  json.dumps(opened)[:200])
            snap_res = await s.call_tool("tg_miniapp_snapshot", {})
            snap = snap_res.content[0].text
            check("snapshot lists elements", "[e" in snap, snap[:150])
            name_ref = next((m.group(1) for m in
                             _re.finditer(r"\[(e\d+)\] input", snap)), None)
            greet_ref = next((m.group(1) for m in
                              _re.finditer(r'\[(e\d+)\] button "Greet"', snap)), None)
            check("input and Greet button found", bool(name_ref and greet_ref),
                  snap[:200])
            if name_ref and greet_ref:
                parse(await s.call_tool("tg_miniapp_type",
                                        {"ref": name_ref, "text": "Claude"}))
                parse(await s.call_tool("tg_miniapp_click", {"ref": greet_ref}))
                snap2 = (await s.call_tool("tg_miniapp_snapshot", {})).content[0].text
                check("mini app reacted (Hello, Claude!)", "Hello, Claude!" in snap2,
                      snap2[:200])
                appshot = await s.call_tool("tg_miniapp_screenshot", {})
                img = next((c for c in appshot.content
                            if getattr(c, "type", "") == "image"), None)
                check("mini app screenshot", img is not None)
                if img:
                    (OUT / "miniapp.png").write_bytes(base64.b64decode(img.data))
                closed = parse(await s.call_tool("tg_miniapp_close", {}))
                check("mini app closed", closed.get("status") == "closed",
                      json.dumps(closed)[:150])

            print("== screenshot")
            shot = await s.call_tool("tg_screenshot", {"scope": "chat"})
            img = next((c for c in shot.content if getattr(c, "type", "") == "image"), None)
            check("screenshot returned", img is not None)
            if img:
                (OUT / "chat.png").write_bytes(base64.b64decode(img.data))
                print(f"  saved {OUT / 'chat.png'}")

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
