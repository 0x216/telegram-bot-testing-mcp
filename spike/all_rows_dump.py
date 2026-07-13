import asyncio
import json

from telegram_user_mcp import selectors as sel
from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession

ALL_ROWS_JS = """
() => Array.from(document.querySelectorAll('a[data-peer-id]')).map(a => {
  let chain = [];
  let n = a.parentElement;
  while (n && chain.length < 6) {
    const id = n.id ? '#' + n.id : '';
    const cls = String(n.className || '').split(' ').slice(0, 2).join('.');
    chain.push(n.tagName.toLowerCase() + id + (cls ? '.' + cls : ''));
    n = n.parentElement;
  }
  const sub = a.querySelector('.row-subtitle');
  const title = a.querySelector('.peer-title');
  return {
    peer: a.dataset.peerId,
    visible: !!a.offsetParent,
    title: title ? title.textContent.trim().slice(0, 25) : null,
    subtitle: sub ? sub.textContent.trim().slice(0, 30) : null,
    cls: String(a.className).slice(0, 45),
    chain: chain.join(' < '),
  };
})
"""


async def main():
    s = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    await s.start()
    page = s.page
    await asyncio.sleep(5)
    await page.locator(sel.SEARCH_INPUT).first.click()
    await page.keyboard.type("BotFather", delay=60)
    for wait in (3, 6, 12):
        await asyncio.sleep(wait)
        rows = await page.evaluate(ALL_ROWS_JS)
        print(f"--- after ~{wait}s cumulative: {len(rows)} rows")
        for r in rows:
            print(" ", json.dumps(r, ensure_ascii=False))
    await s.stop()


asyncio.run(main())
