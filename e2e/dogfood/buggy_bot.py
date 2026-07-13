"""Dogfood target: a small todo bot implemented with FOUR planted bugs.

SPEC (what the QA scenario tests against):
  /start -> welcome text + inline keyboard 2x2: [Add, List] / [Done, Help]
  Add    -> bot asks "Send me a task"; the next text becomes a task,
            bot replies "Added: <task text>"
  List   -> numbered list starting at 1 ("1. <task>") or "No tasks yet"
  Done   -> completes the first task: "Done: <task>" or "Nothing to do"
  /help  -> lists the commands

PLANTED BUGS (the adapter should catch all four):
  A (visual):    keyboard is one row of four, not 2x2
  B (silence):   /help handler is missing entirely
  C (data):      "Added:" strips non-ASCII (emoji/cyrillic vanish)
  D (off-by-one): List numbering starts at 0
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

TOKEN = os.environ.get("BOT_TOKEN") or sys.exit("BOT_TOKEN env var required")
TEST = os.environ.get("BOT_TEST", "") in ("1", "true", "yes")
BASE = f"https://api.telegram.org/bot{TOKEN}" + ("/test" if TEST else "")

tasks: dict[int, list[str]] = {}
awaiting: set[int] = set()


def call(method: str, /, **params):
    data = urllib.parse.urlencode(
        {k: v if isinstance(v, str) else json.dumps(v) for k, v in params.items()}).encode()
    req = urllib.request.Request(f"{BASE}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=70) as resp:
        out = json.load(resp)
    if not out.get("ok"):
        print("API error:", out, file=sys.stderr)
    return out.get("result")


KEYBOARD = {"inline_keyboard": [[  # BUG A: single row instead of 2x2
    {"text": "Add", "callback_data": "add"},
    {"text": "List", "callback_data": "list"},
    {"text": "Done", "callback_data": "done"},
    {"text": "Help", "callback_data": "help"},
]]}


def handle_message(msg):
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    if text == "/start":
        call("sendMessage", chat_id=chat_id,
             text="Welcome to Todo Bot! Manage your tasks:", reply_markup=KEYBOARD)
    # BUG B: /help is not handled anywhere
    elif chat_id in awaiting and text:
        awaiting.discard(chat_id)
        tasks.setdefault(chat_id, []).append(text)
        clean = text.encode("ascii", "ignore").decode()  # BUG C
        call("sendMessage", chat_id=chat_id, text=f"Added: {clean}")
    elif text and not text.startswith("/"):
        call("sendMessage", chat_id=chat_id, text="Use the buttons.")


def handle_callback(cb):
    call("answerCallbackQuery", callback_query_id=cb["id"])
    msg = cb.get("message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    data = cb.get("data")
    if data == "add":
        awaiting.add(chat_id)
        call("sendMessage", chat_id=chat_id, text="Send me a task")
    elif data == "list":
        items = tasks.get(chat_id, [])
        if items:
            listing = "\n".join(f"{i}. {t}" for i, t in enumerate(items))  # BUG D
        else:
            listing = "No tasks yet"
        call("sendMessage", chat_id=chat_id, text=listing)
    elif data == "done":
        items = tasks.get(chat_id, [])
        call("sendMessage", chat_id=chat_id,
             text=f"Done: {items.pop(0)}" if items else "Nothing to do")
    elif data == "help":
        call("sendMessage", chat_id=chat_id,
             text="Commands: /start, /help. Buttons: Add, List, Done")


def main():
    me = call("getMe")
    print(f"buggy todo bot @{me['username']} up (test={TEST})", flush=True)
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
