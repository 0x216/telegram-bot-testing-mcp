import asyncio
import json

from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession
from telegram_user_mcp.telegram import TelegramOps

STATE_JS = """
() => Array.from(document.querySelectorAll('#column-center .chat.active .bubble[data-mid]'))
  .slice(-4).map(b => ({
    mid: b.dataset.mid,
    cls: b.className.split(' ').filter(c => c.startsWith('is-')).join(','),
    text: (b.innerText || '').split('\\n')[0].slice(0, 30),
  }))
"""

CONN_JS = """
() => (document.querySelector('.connection-status-text') || {innerText: null}).innerText
"""


async def main():
    s = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    ops = TelegramOps(s)
    await ops.open_chat("@tgmcp_dogfood_bot")
    page = s.page
    print("connection status:", await page.evaluate(CONN_JS))
    try:
        sent = await ops.send_message("ping-probe")
        print("send returned:", sent)
    except Exception as e:
        print("send failed:", type(e).__name__, str(e)[:100])
    await asyncio.sleep(8)
    print("bubbles:", json.dumps(await page.evaluate(STATE_JS), ensure_ascii=False, indent=1))
    print("connection status:", await page.evaluate(CONN_JS))
    await page.screenshot(path="spike/out/send-state.png")
    await s.stop()


asyncio.run(main())
