"""Fixture bot for e2e: exercises every surface the adapter must handle.

Plain stdlib long-polling client for the Bot API (the *bot* side legitimately
uses Bot API; the adapter's user side never does).

Env:
  BOT_TOKEN  — token from @BotFather
  BOT_API    — optional base, default https://api.telegram.org
               (use https://api.telegram.org/bot<token>/test/ route by setting
                BOT_TEST=1 for the test DC)

Behaviors:
  /start  -> greeting + 2x2 inline keyboard A1 A2 / B1 B2
  callback press -> edits the message to "you pressed <label>"
  /kb     -> reply keyboard [Red, Green]
  /photo  -> sends a small generated PNG
  /hide   -> removes the reply keyboard
  other   -> echo: <text>
"""
from __future__ import annotations

import io
import json
import os
import struct
import sys
import time
import urllib.parse
import urllib.request
import zlib

TOKEN = os.environ.get("BOT_TOKEN") or sys.exit("BOT_TOKEN env var required")
TEST = os.environ.get("BOT_TEST", "") in ("1", "true", "yes")
BASE = f"https://api.telegram.org/bot{TOKEN}" + ("/test" if TEST else "")


def call(method: str, /, files: dict | None = None, **params):
    url = f"{BASE}/{method}"
    if files:
        boundary = "----tgmcpfixture"
        body = b""
        for k, v in params.items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                     f"{v if isinstance(v, str) else json.dumps(v)}\r\n").encode()
        for k, (fname, data, ctype) in files.items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                     f"filename=\"{fname}\"\r\nContent-Type: {ctype}\r\n\r\n").encode() + data + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        data = urllib.parse.urlencode(
            {k: v if isinstance(v, str) else json.dumps(v) for k, v in params.items()}).encode()
        req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=70) as resp:
        out = json.load(resp)
    if not out.get("ok"):
        print("API error:", out, file=sys.stderr)
    return out.get("result")


def tiny_png() -> bytes:
    """4x4 red PNG, no deps."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * 4 for _ in range(4))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


INLINE_KB = {"inline_keyboard": [
    [{"text": "A1", "callback_data": "A1"}, {"text": "A2", "callback_data": "A2"}],
    [{"text": "B1", "callback_data": "B1"}, {"text": "B2", "callback_data": "B2"}],
]}
REPLY_KB = {"keyboard": [[{"text": "Red"}, {"text": "Green"}]],
            "resize_keyboard": True}


def handle_message(msg: dict):
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if text == "/start":
        call("sendMessage", chat_id=chat_id,
             text="fixture bot ready. Press a button:", reply_markup=INLINE_KB)
    elif text == "/kb":
        call("sendMessage", chat_id=chat_id, text="pick a color", reply_markup=REPLY_KB)
    elif text == "/hide":
        call("sendMessage", chat_id=chat_id, text="keyboard hidden",
             reply_markup={"remove_keyboard": True})
    elif text == "/photo":
        call("sendPhoto", chat_id=chat_id, caption="a tiny photo",
             files={"photo": ("tiny.png", tiny_png(), "image/png")})
    elif text == "/app":
        call("sendMessage", chat_id=chat_id, text="try the mini app:",
             reply_markup={"inline_keyboard": [[{
                 "text": "Open App",
                 "web_app": {"url": os.environ.get(
                     "MINIAPP_URL",
                     "https://0x216.github.io/telegram-bot-testing-mcp/miniapp/")},
             }]]})
    elif text:
        call("sendMessage", chat_id=chat_id, text=f"echo: {text}")
    elif msg.get("voice"):
        call("sendMessage", chat_id=chat_id,
             text=f"got your voice ({msg['voice'].get('duration', '?')}s)")
    elif msg.get("photo") or msg.get("document"):
        kind = "photo" if msg.get("photo") else "document"
        call("sendMessage", chat_id=chat_id, text=f"got your {kind}")


def handle_callback(cb: dict):
    call("answerCallbackQuery", callback_query_id=cb["id"])
    msg = cb.get("message")
    if msg:
        call("editMessageText", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
             text=f"you pressed {cb.get('data')}")


def main():
    me = call("getMe")
    print(f"fixture bot @{me['username']} up (test={TEST})", flush=True)
    offset = 0
    while True:
        try:
            updates = call("getUpdates", offset=offset, timeout=50) or []
        except Exception as e:
            print("poll error:", e, file=sys.stderr)
            time.sleep(3)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            try:
                if "message" in u:
                    handle_message(u["message"])
                elif "callback_query" in u:
                    handle_callback(u["callback_query"])
            except Exception as e:
                print("handler error:", e, file=sys.stderr)


if __name__ == "__main__":
    main()
