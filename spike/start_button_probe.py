import asyncio
import json

from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession
from telegram_user_mcp import selectors as sel

BOTTOM_JS = """
() => {
  const inp = document.querySelector('.input-message-input');
  const chatInput = document.querySelector('.chat-input');
  const buttons = chatInput ? Array.from(chatInput.querySelectorAll('button')).map(b =>
      b.className.slice(0, 80) + ' => "' + (b.innerText || '').trim().slice(0, 30) + '"' +
      (b.offsetParent ? ' [visible]' : ' [hidden]')) : [];
  return {
    inputExists: !!inp,
    inputVisible: !!(inp && inp.offsetParent),
    chatInputClasses: chatInput ? chatInput.className.slice(0, 100) : null,
    buttons: buttons.slice(0, 10),
  };
}
"""


async def main():
    s = BrowserSession(Config.from_env({"TG_MCP_MODE": "test"}))
    await s.start()
    page = s.page
    await asyncio.sleep(5)
    await page.locator(sel.SEARCH_INPUT).first.click()
    await page.keyboard.type("botfather", delay=60)
    await asyncio.sleep(8)
    idx = await page.evaluate("""
      () => {
        const rows = Array.from(document.querySelectorAll('.search-group a[data-peer-id]'));
        for (let i = 0; i < rows.length; i++)
          for (const el of rows[i].querySelectorAll('*'))
            if ((el.textContent || '').trim().toLowerCase() === '@botfather') return i;
        return -1;
      }
    """)
    print("row idx:", idx)
    if idx < 0:
        await s.stop()
        return
    await page.locator(".search-group a[data-peer-id]").nth(idx).click()
    await asyncio.sleep(4)
    print(json.dumps(await page.evaluate(BOTTOM_JS), ensure_ascii=False, indent=1))
    await page.screenshot(path="spike/out/botfather-chat.png")
    await s.stop()


asyncio.run(main())
