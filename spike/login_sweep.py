"""Sweep test-DC login: DC 1..3, capture console to see exact MTProto errors."""
import random
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

DC = int(sys.argv[1]) if len(sys.argv) > 1 else 2
PHONE = f"99966{DC}{random.randint(0, 9999):04d}"
CODE = str(DC) * 5

console_lines = []


def on_console(msg):
    text = msg.text
    if any(k in text.lower() for k in ("error", "code", "auth", "sign", "phone", "dc")):
        console_lines.append(text[:300])


with sync_playwright() as p:
    profile = OUT / f"profile-dc{DC}"
    shutil.rmtree(profile, ignore_errors=True)
    ctx = p.chromium.launch_persistent_context(str(profile), headless=True,
                                               viewport={"width": 1280, "height": 900})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_default_timeout(30000)
    page.on("console", on_console)

    print(f"=== DC{DC} phone={PHONE} code={CODE}")
    page.goto("https://web.telegram.org/k/?test=1&debug=1", wait_until="domcontentloaded")
    page.wait_for_timeout(8000)

    btn = page.get_by_text("Log in by phone Number", exact=False)
    if btn.count() > 0:
        btn.first.click()
        page.wait_for_timeout(2000)

    phone_input = page.locator("div.input-field-phone .input-field-input")
    phone_input.first.click()
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    page.keyboard.type("+" + PHONE, delay=50)
    page.wait_for_timeout(1000)
    page.get_by_role("button", name="Next", exact=False).first.click()
    page.wait_for_timeout(5000)

    if page.get_by_text("sent you an SMS", exact=False).count() == 0:
        page.screenshot(path=str(OUT / f"sweep-dc{DC}-no-code-screen.png"))
        print("no code screen; console tail:")
        for line in console_lines[-25:]:
            print("  C:", line)
        ctx.close()
        sys.exit()

    console_lines.clear()
    page.keyboard.type(CODE, delay=200)
    page.wait_for_timeout(6000)
    page.screenshot(path=str(OUT / f"sweep-dc{DC}-result.png"))
    err = page.get_by_text("Invalid code", exact=False).count() > 0
    signup = page.get_by_text("Your Name", exact=False).count() > 0
    in_app = page.locator(".chatlist").count() > 0
    print(f"invalid_code={err} signup_screen={signup} chatlist={in_app}")
    print("console after code submit:")
    for line in console_lines[-30:]:
        print("  C:", line)
    ctx.close()
