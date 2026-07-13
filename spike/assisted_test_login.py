"""Assisted test-DC login: opens headed WebK ?test=1 on profile-test,
pre-fills the phone number, clicks Next; the human types the code that
arrives on their logged-in test device. Polls until logged in.
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PHONE = sys.argv[1]
PROFILE = str(Path.home() / ".telegram-user-mcp" / "profile-test")

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(PROFILE, headless=False,
                                               viewport={"width": 1100, "height": 800})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_default_timeout(60000)
    page.goto("https://web.telegram.org/k/?test=1", wait_until="domcontentloaded")
    page.wait_for_selector("#page-chats:visible, #auth-pages:visible", state="attached")

    if page.locator("#page-chats:visible").count() > 0:
        print("ALREADY LOGGED IN")
        ctx.close()
        sys.exit(0)

    btn = page.get_by_text("Log in by phone Number", exact=False)
    if btn.count() > 0:
        btn.first.click()
        page.wait_for_timeout(2000)

    phone_input = page.locator(".input-field-phone .input-field-input")
    phone_input.first.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.keyboard.type("+" + PHONE.lstrip("+"), delay=50)
    page.wait_for_timeout(1000)
    page.get_by_role("button", name="Next", exact=False).first.click()
    print("PHONE SUBMITTED — enter the code from your test device in the window", flush=True)

    deadline = time.time() + 600
    while time.time() < deadline:
        if page.locator("#page-chats:visible").count() > 0:
            print("LOGGED IN OK")
            ctx.close()
            sys.exit(0)
        time.sleep(2)
    print("TIMED OUT waiting for code entry")
    ctx.close()
    sys.exit(1)
