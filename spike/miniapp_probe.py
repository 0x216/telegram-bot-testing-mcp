import asyncio
import json

from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession
from telegram_user_mcp.telegram import TelegramOps

DUMP_JS = """
() => ({
  popups: Array.from(document.querySelectorAll('.popup')).filter(p => p.offsetParent).map(p => ({
    cls: p.className.slice(0, 90),
    buttons: Array.from(p.querySelectorAll('button')).filter(b => b.offsetParent)
      .map(b => b.className.slice(0, 50) + ' => "' + (b.innerText || '').trim().slice(0, 30) + '"'),
    text: (p.innerText || '').replace(/\\n/g, ' | ').slice(0, 150),
  })),
  iframes: Array.from(document.querySelectorAll('iframe')).map(f => ({
    src: (f.src || '').slice(0, 90),
    cls: f.className.slice(0, 50),
    visible: !!f.offsetParent,
    parent: f.parentElement ? f.parentElement.className.slice(0, 60) : null,
  })),
})
"""


async def main():
    s = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    ops = TelegramOps(s)
    await ops.open_chat("@tgmcp_fixture_bot")
    page = s.page
    sent = await ops.send_message("/app")
    await ops.wait_for_message(timeout_s=30, after_id=sent["id"])
    res = await ops.click_button(text="Open App")
    print("clicked:", res.get("clicked"))
    for wait in (2, 5, 8):
        await asyncio.sleep(wait)
        print(f"--- +{wait}s:", json.dumps(await page.evaluate(DUMP_JS),
                                           ensure_ascii=False, indent=1))
    await page.screenshot(path="spike/out/miniapp-state.png")
    await s.stop()


asyncio.run(main())
