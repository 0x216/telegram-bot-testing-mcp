"""Spike: can we auto-create an account on Telegram test DC via WebK (?test=1)?

Steps: open web.telegram.org/k/?test=1 -> switch to phone login ->
enter 99966<DC><4 digits> -> code = DC repeated 5 times -> maybe sign-up screen.
Screenshots land in spike/out/.
"""
import random
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)
shutil.rmtree(OUT / "profile", ignore_errors=True)
DC = 2
PHONE = f"99966{DC}{random.randint(0, 9999):04d}"
CODE = str(DC) * 5

step_n = 0


def shot(page, name):
    global step_n
    step_n += 1
    path = OUT / f"{step_n:02d}-{name}.png"
    page.screenshot(path=str(path))
    print(f"[shot] {path.name}  url={page.url}")


def dump_state(page, label):
    texts = page.evaluate(
        "() => Array.from(document.querySelectorAll('button, .btn-primary, h4, .phone, .input-field-input'))"
        ".map(e => (e.tagName + ':' + (e.innerText || e.textContent || '').trim().slice(0, 60)))"
        ".filter(t => t.length > 3).slice(0, 30)"
    )
    print(f"[{label}] visible elements:")
    for t in texts:
        print("   ", t)


with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(OUT / "profile"),
        headless=True,
        viewport={"width": 1280, "height": 900},
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_default_timeout(30000)
    page.on("websocket", lambda ws: print(f"[ws] {ws.url}"))

    print(f"phone={PHONE} code={CODE}")
    page.goto("https://web.telegram.org/k/?test=1", wait_until="domcontentloaded")
    # WebK SPA boot takes a while
    page.wait_for_timeout(8000)
    shot(page, "boot")
    dump_state(page, "boot")

    # Switch from QR to phone login if needed
    btn = page.get_by_text("Log in by phone Number", exact=False)
    if btn.count() > 0:
        btn.first.click()
        page.wait_for_timeout(2000)
        shot(page, "phone-login-form")

    # Fill phone number: WebK has a div[contenteditable] phone input (.input-field-phone)
    phone_input = page.locator("div.input-field-phone .input-field-input, input[name=phone]")
    if phone_input.count() == 0:
        dump_state(page, "no-phone-input")
        shot(page, "no-phone-input")
        sys.exit("phone input not found")
    phone_input.first.click()
    # clear pre-filled country code
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.keyboard.type("+" + PHONE, delay=50)
    page.wait_for_timeout(1500)
    shot(page, "phone-filled")
    dump_state(page, "phone-filled")

    next_btn = page.get_by_role("button", name="Next", exact=False)
    if next_btn.count() == 0:
        next_btn = page.locator("button.btn-primary")
    next_btn.first.click()
    page.wait_for_timeout(5000)
    shot(page, "after-next")
    dump_state(page, "after-next")

    # Code entry: 5 separate cells, first one focused — just type
    if page.get_by_text("sent you an SMS", exact=False).count() > 0:
        page.keyboard.type(CODE, delay=250)
        shot(page, "code-typed")
        page.wait_for_timeout(8000)
        shot(page, "after-code")
        dump_state(page, "after-code")
    else:
        print("code screen not detected")

    # Possible sign-up screen (first/last name) for fresh numbers
    if page.get_by_text("Your Name", exact=False).count() > 0:
        print("sign-up screen detected")
        name_input = page.locator(".input-field-input[contenteditable=true]")
        if name_input.count() > 0:
            name_input.first.click()
            page.keyboard.type("Adapter Spike", delay=40)
            shot(page, "signup-filled")
            page.locator("button.btn-primary").first.click()
            page.wait_for_timeout(10000)

    shot(page, "final")
    dump_state(page, "final")
    # Are we in? The left column with chat list + search is the reliable sign
    in_app = page.locator("#column-left").count() > 0 and page.locator(".chatlist").count() > 0
    print("LOGGED IN:", in_app, "url:", page.url)
    ctx.close()
