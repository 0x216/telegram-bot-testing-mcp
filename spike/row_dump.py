import asyncio
import json

from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession
from telegram_user_mcp import selectors as sel

DUMP_JS = """
() => {
  const rows = Array.from(document.querySelectorAll('.search-group a[data-peer-id]'));
  return rows.slice(0, 6).map(r => ({
    peer: r.dataset.peerId,
    tree: Array.from(r.querySelectorAll('*')).map(el =>
      el.tagName.toLowerCase() + '.' + String(el.className).split(' ').slice(0,2).join('.')
      + ' => "' + (el.textContent || '').trim().slice(0, 40) + '"').slice(0, 14),
  }));
}
"""


async def main():
    s = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    await s.start()
    page = s.page
    await asyncio.sleep(5)
    await page.locator(sel.SEARCH_INPUT).first.click()
    await page.keyboard.type("BotFather", delay=60)
    await asyncio.sleep(8)
    print(json.dumps(await page.evaluate(DUMP_JS), ensure_ascii=False, indent=1))
    await s.stop()


asyncio.run(main())
