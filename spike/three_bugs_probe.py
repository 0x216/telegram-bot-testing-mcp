import asyncio
import json

from telegram_user_mcp import selectors as sel
from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession
from telegram_user_mcp.telegram import TelegramOps

POPUP_JS = """
() => Array.from(document.querySelectorAll('.popup')).filter(p => p.offsetParent).map(p => ({
  cls: p.className.slice(0, 80),
  buttons: Array.from(p.querySelectorAll('button')).map(b =>
    b.className.slice(0, 60) + ' => "' + (b.innerText || '').trim().slice(0, 30) + '"'),
  checkboxes: Array.from(p.querySelectorAll('label')).map(l => (l.innerText || '').trim().slice(0, 40)),
}))
"""

KB_JS = """
() => {
  const kb = document.querySelector('.reply-keyboard');
  if (!kb) return {kb: false};
  return {
    kb: true,
    visible: !!kb.offsetParent,
    html: kb.outerHTML.slice(0, 600),
  };
}
"""


async def main():
    s = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    ops = TelegramOps(s)
    await ops.open_chat("@tgmcp_fixture_bot")
    page = s.page

    print("=== A: reply keyboard")
    sent = await ops.send_message("/kb")
    await ops.wait_for_message(timeout_s=30, after_id=sent["id"])
    print(json.dumps(await page.evaluate(KB_JS), ensure_ascii=False)[:700])
    try:
        res = await ops.click_reply_button("Red")
        print("clicked:", res["clicked"])
    except Exception as e:
        print("click failed:", e)
    await asyncio.sleep(3)
    msgs = await ops.read_messages(5)
    print("last texts:", [(m["id"], m["out"], m["text"][:25]) for m in msgs])
    await page.screenshot(path="spike/out/after-red.png")

    print("=== B: delete/clear popup")
    await page.locator(sel.TOPBAR_MENU_BUTTON).last.click()
    await asyncio.sleep(1)
    menu_items = await page.evaluate(
        """() => Array.from(document.querySelectorAll('.btn-menu-item'))
              .filter(e => e.offsetParent)
              .map(e => (e.innerText || '').trim())"""
    )
    print("menu items:", menu_items)
    import re
    item = page.locator(sel.MENU_ITEM, has_text=re.compile("delete|clear", re.I))
    await item.first.click()
    await asyncio.sleep(1.5)
    print(json.dumps(await page.evaluate(POPUP_JS), ensure_ascii=False, indent=1))
    await page.screenshot(path="spike/out/delete-popup.png")
    await page.keyboard.press("Escape")
    await s.stop()


asyncio.run(main())
