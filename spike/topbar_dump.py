import asyncio
import json

from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession
from telegram_user_mcp.telegram import TelegramOps

TOPBAR_JS = """
() => {
  const bars = Array.from(document.querySelectorAll('.sidebar-header, .topbar'));
  return bars.filter(b => b.offsetParent).map(b => ({
    cls: b.className.slice(0, 60),
    buttons: Array.from(b.querySelectorAll('button')).map(x =>
      x.className.slice(0, 60) + (x.offsetParent ? ' [visible]' : ' [hidden]')),
  }));
}
"""


async def main():
    s = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    ops = TelegramOps(s)
    await ops.open_chat("@tgmcp_fixture_bot")
    print(json.dumps(await s.page.evaluate(TOPBAR_JS), ensure_ascii=False, indent=1))
    await s.stop()


asyncio.run(main())
