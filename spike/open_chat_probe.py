import asyncio
import json

from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession

STATE_JS = """() => ({
    hash: location.hash,
    input: !!(document.querySelector('.input-message-input') && document.querySelector('.input-message-input').offsetParent),
    bubbles: document.querySelectorAll('.bubble').length,
    topbar: (document.querySelector('#column-center .chat .topbar, .sidebar-header.topbar') || {innerText: ''}).innerText.split('\\n').join(' | ').slice(0, 60),
})"""

RESULTS_JS = """() => Array.from(document.querySelectorAll('.search-group')).map(g => ({
    group: g.className.slice(0, 50),
    items: Array.from(g.querySelectorAll('a')).slice(0, 4).map(a => ({
        cls: a.className.slice(0, 40),
        peer: a.dataset ? a.dataset.peerId : null,
        text: (a.innerText || '').split('\\n').join(' | ').slice(0, 60),
    })),
}))"""


async def state(page, label):
    st = await page.evaluate(STATE_JS)
    print(label, json.dumps(st, ensure_ascii=False), flush=True)
    return st


async def main():
    s = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    await s.start()
    page = s.page

    await page.goto("https://web.telegram.org/k/?test=1#@BotFather",
                    wait_until="domcontentloaded")
    await asyncio.sleep(10)
    st = await state(page, "boot-with-hash:")

    if not st["input"]:
        search = page.locator(".input-search input, .input-search-input")
        print("search fields:", await search.count())
        await search.first.click()
        await page.keyboard.type("BotFather", delay=80)
        await asyncio.sleep(4)
        await page.screenshot(path="spike/out/search-results.png")
        print(json.dumps(await page.evaluate(RESULTS_JS), ensure_ascii=False, indent=1))
        first = page.locator(".search-group a.chatlist-chat").first
        if await first.count():
            await first.click()
            await asyncio.sleep(3)
            await state(page, "after-search-click:")
            await page.screenshot(path="spike/out/after-search-click.png")
    await s.stop()


asyncio.run(main())
