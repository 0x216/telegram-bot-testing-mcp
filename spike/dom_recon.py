"""After login works: recon WebK DOM — search for a bot, open chat, send message, dump message DOM.

Usage: python spike/dom_recon.py <profile-dir> [@botusername]
Reuses a logged-in test-DC profile.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "out"
PROFILE = sys.argv[1] if len(sys.argv) > 1 else str(OUT / "profile-dc2")
BOT = sys.argv[2] if len(sys.argv) > 2 else "@BotFather"

n = 0


def shot(page, name):
    global n
    n += 1
    p = OUT / f"recon-{n:02d}-{name}.png"
    page.screenshot(path=str(p))
    print("[shot]", p.name)


with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(PROFILE, headless=True,
                                               viewport={"width": 1280, "height": 900})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_default_timeout(30000)
    page.goto("https://web.telegram.org/k/?test=1", wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    shot(page, "boot")

    logged_in = page.locator(".chatlist").count() > 0
    print("logged in:", logged_in)
    if not logged_in:
        sys.exit("profile is not logged in")

    # Search for the bot
    search = page.locator(".input-search input")
    print("search inputs:", search.count())
    search.first.click()
    page.keyboard.type(BOT, delay=60)
    page.wait_for_timeout(4000)
    shot(page, "search-results")

    # Dump search result structure
    results = page.evaluate(
        """() => Array.from(document.querySelectorAll('.search-group a, .chatlist a, ul a.chatlist-chat'))
             .slice(0, 10)
             .map(a => ({cls: a.className.slice(0,80), text: (a.innerText||'').replace(/\\n/g,' | ').slice(0,80),
                         peer: a.dataset ? a.dataset.peerId : null}))"""
    )
    print(json.dumps(results, ensure_ascii=False, indent=1))

    # Click first result
    first = page.locator(".search-group a, ul a.chatlist-chat").first
    first.click()
    page.wait_for_timeout(3000)
    shot(page, "chat-open")

    # Message input: WebK uses contenteditable div .input-message-input
    inp = page.locator(".input-message-input")
    print("message inputs:", inp.count())
    if inp.count() > 0:
        inp.first.click()
        page.keyboard.type("/start", delay=60)
        page.keyboard.press("Enter")
        page.wait_for_timeout(5000)
        shot(page, "after-start")

    # Dump message bubbles structure
    bubbles = page.evaluate(
        """() => Array.from(document.querySelectorAll('.bubble')).slice(-8).map(b => ({
              cls: b.className.slice(0, 120),
              mid: b.dataset.mid, peer: b.dataset.peerId,
              out: b.classList.contains('is-out'),
              text: (b.querySelector('.message')?.innerText || '').slice(0, 120),
              buttons: Array.from(b.querySelectorAll('.reply-markup-button')).map(x => x.innerText.trim()),
           }))"""
    )
    print(json.dumps(bubbles, ensure_ascii=False, indent=1))
    ctx.close()
