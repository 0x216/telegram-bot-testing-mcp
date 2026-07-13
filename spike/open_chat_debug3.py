import asyncio

from telegram_user_mcp import selectors as sel
from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession
from telegram_user_mcp.telegram import TelegramOps


class DebugOps(TelegramOps):
    async def _type_into_search(self, page, text):
        ok = await super()._type_into_search(page, text)
        val = await page.locator(sel.SEARCH_INPUT).first.input_value()
        rows = await page.locator(sel.SEARCH_RESULT_ROW).count()
        print(f"[debug] typed_ok={ok} value={val!r} rows_now={rows}", flush=True)
        return ok


async def main():
    s = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    ops = DebugOps(s)
    try:
        opened = await ops.open_chat("@BotFather")
        print("OK:", str(opened)[:200])
    except Exception as e:
        print("FAIL:", type(e).__name__, e)
        await s.page.screenshot(path="spike/out/debug3-fail.png")
        rows = await s.page.locator(sel.SEARCH_RESULT_ROW).count()
        groups = await s.page.locator(".search-group").count()
        print(f"rows={rows} groups={groups}")
    finally:
        await s.stop()


asyncio.run(main())
