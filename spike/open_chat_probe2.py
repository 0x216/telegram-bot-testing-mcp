import asyncio
import json

from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession
from telegram_user_mcp.telegram import TelegramOps


async def main():
    s = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    ops = TelegramOps(s)
    await s.start()
    page = s.page
    for attempt in (1, 2, 3):
        try:
            opened = await ops.open_chat("@BotFather")
            print(f"attempt {attempt}: OK", json.dumps(opened, ensure_ascii=False)[:300])
            break
        except Exception as e:
            print(f"attempt {attempt}: {type(e).__name__}: {e}")
            await page.screenshot(path=f"spike/out/openchat-fail-{attempt}.png")
            n_inputs = await page.locator(".input-search input").count()
            n_groups = await page.locator(".search-group").count()
            n_rows = await page.locator(".search-group a[data-peer-id]").count()
            print(f"  search inputs={n_inputs} groups={n_groups} rows={n_rows}")
            rows = await page.evaluate(
                """() => Array.from(document.querySelectorAll('.search-group a')).slice(0,6)
                       .map(a => (a.dataset.peerId || '?') + ' :: ' + (a.innerText||'').split('\\n').join(' | ').slice(0,60))"""
            )
            print("  rows:", json.dumps(rows, ensure_ascii=False))
            await asyncio.sleep(5)
    await s.stop()


asyncio.run(main())
