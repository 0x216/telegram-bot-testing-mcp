# telegram-user-mcp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A publishable Python MCP server that drives real web.telegram.org (WebK) via Playwright so agents can test Telegram bots exactly as a human user.

**Architecture:** stdio MCP server (FastMCP) → BrowserSession (persistent Chromium profile) → semantic DOM operations on WebK. All selectors centralized; structured message extraction via single `page.evaluate` calls returning plain JSON (no stale handles). Mini Apps get a generic iframe escape hatch.

**Tech Stack:** Python ≥3.11, `mcp` (FastMCP), `playwright` (async), pytest. Spec: `docs/superpowers/specs/2026-07-13-telegram-user-adapter-design.md`.

## Global Constraints

- Default mode `prod`; `test` mode adds `?test=1` to the WebK URL (test-DC accounts can no longer be self-registered — tdlib/td#3370; never claim otherwise in docs/errors).
- Package name `telegram-user-mcp`, import package `telegram_user_mcp`, src layout, MIT.
- User-side interaction ONLY through the browser (no MTProto libraries in the product; `telethon` may appear only under `spike/`).
- Every tool returns typed errors (`code` + `hint`) from `errors.py` — never bare tracebacks across MCP.
- All DOM selectors live in `selectors.py` only. No selector literals in other modules.
- Headless by default; `TG_MCP_HEADED=1` for headed. Env vars: `TG_MCP_MODE`, `TG_MCP_HEADED`, `TG_MCP_PROFILE_DIR`.
- Profile dirs: `~/.telegram-user-mcp/profile-prod` / `profile-test`.
- Windows-first dev box: run Python via `.venv/Scripts/python.exe`, set `PYTHONIOENCODING=utf-8` when console output may contain non-ASCII.

## File Structure

```
pyproject.toml                      — package metadata, entry point, deps
src/telegram_user_mcp/__init__.py   — version only
src/telegram_user_mcp/config.py     — Config dataclass, from_env
src/telegram_user_mcp/errors.py     — AdapterError hierarchy with code/hint/payload
src/telegram_user_mcp/selectors.py  — ALL WebK selectors (single source of truth)
src/telegram_user_mcp/extract.py    — JS extraction snippets + Message shaping
src/telegram_user_mcp/session.py    — Playwright lifecycle, login detection, interactive login
src/telegram_user_mcp/telegram.py   — TelegramOps: semantic chat operations
src/telegram_user_mcp/miniapp.py    — MiniAppOps: generic iframe interaction
src/telegram_user_mcp/server.py     — FastMCP tool definitions (thin mapping layer)
src/telegram_user_mcp/cli.py        — entry point: server (default) / login subcommand
tests/test_config.py                — env parsing
tests/test_errors.py                — error payload shape
tests/test_extract.py               — extraction JS against fixture HTML (headless chromium, set_content, offline)
tests/test_server.py                — in-memory MCP session: tool listing, not_logged_in error shape
tests/fixtures/bubbles.html         — representative WebK chat DOM (from recon/e2e capture)
e2e/fixture_bot.py                  — Bot API long-polling fixture bot (echo, keyboards, media, edits)
e2e/run_scenarios.py                — drives the MCP server as a client through full scenarios
README.md                           — install, login, tools, security note, test-DC reality
```

---

### Task 1: Scaffold + Config

**Files:**
- Create: `pyproject.toml`, `src/telegram_user_mcp/__init__.py`, `src/telegram_user_mcp/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config(mode: str, headed: bool, profile_dir: Path)`, `Config.from_env(env: Mapping[str, str] | None) -> Config`, `Config.base_url -> str`, `DEFAULT_ROOT = Path.home() / ".telegram-user-mcp"`.

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "telegram-user-mcp"
version = "0.1.0"
description = "Test Telegram bots as a real user: MCP server driving web.telegram.org in a real browser"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
dependencies = ["mcp>=1.2", "playwright>=1.49"]

[project.scripts]
telegram-user-mcp = "telegram_user_mcp.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/telegram_user_mcp"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Write the failing test**

`tests/test_config.py`:
```python
from pathlib import Path

from telegram_user_mcp.config import Config, DEFAULT_ROOT


def test_defaults():
    cfg = Config.from_env({})
    assert cfg.mode == "prod"
    assert cfg.headed is False
    assert cfg.profile_dir == DEFAULT_ROOT / "profile-prod"
    assert cfg.base_url == "https://web.telegram.org/k/"


def test_test_mode_url_and_profile():
    cfg = Config.from_env({"TG_MCP_MODE": "test"})
    assert cfg.base_url == "https://web.telegram.org/k/?test=1"
    assert cfg.profile_dir == DEFAULT_ROOT / "profile-test"


def test_overrides():
    cfg = Config.from_env({
        "TG_MCP_MODE": "prod",
        "TG_MCP_HEADED": "1",
        "TG_MCP_PROFILE_DIR": "C:/tmp/prof",
    })
    assert cfg.headed is True
    assert cfg.profile_dir == Path("C:/tmp/prof")


def test_invalid_mode_rejected():
    import pytest
    with pytest.raises(ValueError):
        Config.from_env({"TG_MCP_MODE": "staging"})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: FAIL (ModuleNotFoundError / ImportError)

- [ ] **Step 4: Implement config.py**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_ROOT = Path.home() / ".telegram-user-mcp"
_WEBK = "https://web.telegram.org/k/"


@dataclass(frozen=True)
class Config:
    mode: str = "prod"
    headed: bool = False
    profile_dir: Path = DEFAULT_ROOT / "profile-prod"

    @staticmethod
    def from_env(env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        mode = env.get("TG_MCP_MODE", "prod").lower()
        if mode not in ("prod", "test"):
            raise ValueError(f"TG_MCP_MODE must be 'prod' or 'test', got {mode!r}")
        headed = env.get("TG_MCP_HEADED", "") in ("1", "true", "yes")
        profile = env.get("TG_MCP_PROFILE_DIR")
        profile_dir = Path(profile) if profile else DEFAULT_ROOT / f"profile-{mode}"
        return Config(mode=mode, headed=headed, profile_dir=profile_dir)

    @property
    def base_url(self) -> str:
        return _WEBK + ("?test=1" if self.mode == "test" else "")
```

`src/telegram_user_mcp/__init__.py`:
```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Install editable + run tests**

Run: `uv pip install --python .venv -e ".[dev]" && .venv/Scripts/python.exe -m pytest tests/test_config.py -q`
Expected: 4 passed

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: package scaffold and Config"`

---

### Task 2: Typed errors

**Files:**
- Create: `src/telegram_user_mcp/errors.py`
- Test: `tests/test_errors.py`

**Interfaces:**
- Produces: `AdapterError(Exception)` with attrs `code: str`, `hint: str`, `payload: dict`; method `to_payload() -> dict` returning `{"error": code, "message": str(exc), "hint": hint, **payload}`. Subclasses (exact constructor signatures):
  - `NotLoggedIn()` — code `not_logged_in`
  - `ChatNotFound(query: str)` — code `chat_not_found`
  - `ButtonNotFound(wanted: str, available: list[str])` — code `button_not_found`, payload `{"available_buttons": available}`
  - `WaitTimeout(seconds: float)` — code `timeout`
  - `MiniAppNotOpen()` — code `miniapp_not_open`
  - `SelectorBroken(what: str)` — code `selector_broken`

- [ ] **Step 1: Write the failing test**

`tests/test_errors.py`:
```python
from telegram_user_mcp.errors import AdapterError, ButtonNotFound, NotLoggedIn


def test_payload_shape():
    e = ButtonNotFound("Pay", ["Start", "Help"])
    p = e.to_payload()
    assert p["error"] == "button_not_found"
    assert p["available_buttons"] == ["Start", "Help"]
    assert "Pay" in p["message"]
    assert p["hint"]


def test_not_logged_in_hint_mentions_login():
    assert "tg_login" in NotLoggedIn().to_payload()["hint"]


def test_all_are_adapter_errors():
    assert issubclass(ButtonNotFound, AdapterError)
```

- [ ] **Step 2: Run to verify FAIL**, then implement:

```python
from __future__ import annotations


class AdapterError(Exception):
    code = "adapter_error"
    hint = ""

    def __init__(self, message: str, *, hint: str | None = None, **payload):
        super().__init__(message)
        if hint is not None:
            self.hint = hint
        self.payload = payload

    def to_payload(self) -> dict:
        return {"error": self.code, "message": str(self), "hint": self.hint, **self.payload}


class NotLoggedIn(AdapterError):
    code = "not_logged_in"

    def __init__(self):
        super().__init__(
            "No Telegram session in this profile.",
            hint="Run the tg_login tool (or `telegram-user-mcp login`) and scan the QR code once.",
        )


class ChatNotFound(AdapterError):
    code = "chat_not_found"

    def __init__(self, query: str):
        super().__init__(f"Chat not found for query {query!r}.",
                         hint="Use @username, a t.me link, or an exact chat title.")


class ButtonNotFound(AdapterError):
    code = "button_not_found"

    def __init__(self, wanted: str, available: list[str]):
        super().__init__(f"No button matching {wanted!r}.",
                         hint="Pick one of the available buttons (listed in available_buttons).",
                         available_buttons=available)


class WaitTimeout(AdapterError):
    code = "timeout"

    def __init__(self, seconds: float):
        super().__init__(f"No new message from the bot within {seconds:g}s.",
                         hint="The bot may be slow or not running; check read_messages for current state.")


class MiniAppNotOpen(AdapterError):
    code = "miniapp_not_open"

    def __init__(self):
        super().__init__("No Mini App is currently open.",
                         hint="Call tg_miniapp_open first (a message must offer a web-app button).")


class SelectorBroken(AdapterError):
    code = "selector_broken"

    def __init__(self, what: str):
        super().__init__(f"Could not locate {what} in the Telegram Web UI.",
                         hint="Telegram may have changed its markup; update selectors.py "
                              "or report at the project issue tracker.")
```

- [ ] **Step 3: Run tests (PASS), commit** — `git commit -m "feat: typed adapter errors"`

---

### Task 3: selectors.py + DOM fixtures

**Files:**
- Create: `src/telegram_user_mcp/selectors.py`, `tests/fixtures/bubbles.html`

**Interfaces:**
- Produces: module-level constants used by all later tasks (exact names):
  `CHATLIST`, `AUTH_PAGES`, `LOGIN_PHONE_BUTTON_TEXT`, `PHONE_INPUT`, `NEXT_BUTTON`, `CODE_SENT_MARKER_TEXT`, `QR_CANVAS`,
  `BUBBLE`, `BUBBLE_TEXT`, `BUBBLE_TIME`, `INLINE_BUTTON`, `INLINE_ROW`,
  `REPLY_KEYBOARD`, `REPLY_KEYBOARD_BUTTON`,
  `MESSAGE_INPUT`, `SEND_BUTTON`, `ATTACH_BUTTON`, `FILE_INPUT`, `ATTACH_POPUP`, `ATTACH_POPUP_SEND`,
  `CHAT_CONTAINER`, `BUBBLES_SCROLL`, `TOPBAR_MENU_BUTTON`, `MENU_ITEM`, `POPUP_BUTTON`,
  `WEBAPP_POPUP`, `WEBAPP_IFRAME`, `WEBAPP_CLOSE`.
- **Content comes from the tweb source recon report (appended to this plan as Appendix A).** Every constant carries a comment with the source file it was derived from.

- [ ] **Step 1:** Write `selectors.py` from Appendix A. **Step 2:** Write `tests/fixtures/bubbles.html` from Appendix A markup samples (one incoming text bubble with 2×2 inline keyboard, one outgoing bubble, one service bubble, one photo bubble). **Step 3:** Commit — `git commit -m "feat: centralized WebK selectors + DOM fixtures"`.

---

### Task 4: extract.py — structured message extraction

**Files:**
- Create: `src/telegram_user_mcp/extract.py`
- Test: `tests/test_extract.py` (headless chromium + `page.set_content`, offline)

**Interfaces:**
- Produces:
  - `MESSAGES_JS: str` — JS `(args) => [...]` taking `{bubbleSel, textSel, timeSel, btnSel, limit}` and returning raw dicts `{mid, out, service, text, time, buttons: [[{text}]], media}`.
  - `@dataclass Message: id: int, out: bool, service: bool, text: str, time: str | None, buttons: list[list[str]], media: str | None` with `to_dict() -> dict`.
  - `shape_messages(raw: list[dict]) -> list[Message]`
  - `async read_messages(page, limit=20) -> list[Message]` — the one entry point used by TelegramOps.

- [ ] **Step 1: Write the failing test**

`tests/test_extract.py`:
```python
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from telegram_user_mcp import extract

FIXTURE = (Path(__file__).parent / "fixtures" / "bubbles.html").read_text(encoding="utf-8")


@pytest.fixture()
async def page():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        pg = await browser.new_page()
        await pg.set_content(FIXTURE)
        yield pg
        await browser.close()


async def test_reads_text_and_direction(page):
    msgs = await extract.read_messages(page)
    incoming = [m for m in msgs if not m.out and not m.service]
    outgoing = [m for m in msgs if m.out]
    assert incoming and outgoing
    assert incoming[0].text
    assert isinstance(incoming[0].id, int)


async def test_reads_inline_keyboard_grid(page):
    msgs = await extract.read_messages(page)
    with_buttons = [m for m in msgs if m.buttons]
    assert with_buttons, "fixture has a 2x2 keyboard"
    grid = with_buttons[0].buttons
    assert len(grid) == 2 and len(grid[0]) == 2


async def test_limit(page):
    msgs = await extract.read_messages(page, limit=1)
    assert len(msgs) == 1
```

- [ ] **Step 2: Run to verify FAIL**, then implement `extract.py`:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass

from . import selectors as sel

MESSAGES_JS = """
(args) => {
  const bubbles = Array.from(document.querySelectorAll(args.bubbleSel)).slice(-args.limit);
  return bubbles.map(b => {
    const textEl = b.querySelector(args.textSel);
    const timeEl = b.querySelector(args.timeSel);
    const rows = [];
    for (const row of b.querySelectorAll(args.rowSel)) {
      const btns = Array.from(row.querySelectorAll(args.btnSel)).map(x => (x.innerText || '').trim());
      if (btns.length) rows.push(btns);
    }
    let media = null;
    for (const [cls, kind] of args.mediaClasses) {
      if (b.querySelector(cls)) { media = kind; break; }
    }
    let text = '';
    if (textEl) {
      const clone = textEl.cloneNode(true);
      clone.querySelectorAll(args.timeSel).forEach(t => t.remove());
      text = (clone.innerText || '').trim();
    }
    return {
      mid: Number(b.dataset.mid || 0),
      out: b.classList.contains('is-out'),
      service: b.classList.contains('service'),
      text,
      time: timeEl ? (timeEl.getAttribute('title') || timeEl.innerText || '').trim() : null,
      buttons: rows,
      media,
    };
  });
}
"""


@dataclass
class Message:
    id: int
    out: bool
    service: bool
    text: str
    time: str | None
    buttons: list[list[str]]
    media: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def shape_messages(raw: list[dict]) -> list[Message]:
    return [
        Message(
            id=int(r.get("mid") or 0),
            out=bool(r.get("out")),
            service=bool(r.get("service")),
            text=r.get("text") or "",
            time=r.get("time"),
            buttons=[[str(t) for t in row] for row in (r.get("buttons") or [])],
            media=r.get("media"),
        )
        for r in raw
    ]


def _js_args(limit: int) -> dict:
    return {
        "bubbleSel": sel.BUBBLE,
        "textSel": sel.BUBBLE_TEXT,
        "timeSel": sel.BUBBLE_TIME,
        "rowSel": sel.INLINE_ROW,
        "btnSel": sel.INLINE_BUTTON,
        "mediaClasses": sel.MEDIA_KIND_SELECTORS,
        "limit": limit,
    }


async def read_messages(page, limit: int = 20):
    raw = await page.evaluate(MESSAGES_JS, _js_args(limit))
    return shape_messages(raw)
```

(`sel.MEDIA_KIND_SELECTORS` is a `list[tuple[str, str]]` like `[(".media-photo", "photo"), (".document", "document"), ...]` — exact values from Appendix A; add it to Task 3's constant list.)

- [ ] **Step 3: Run tests (PASS), commit** — `git commit -m "feat: structured message extraction"`

---

### Task 5: session.py — browser lifecycle & login

**Files:**
- Create: `src/telegram_user_mcp/session.py`
- Test: manual smoke (network): `.venv/Scripts/python.exe -m telegram_user_mcp.smoke` is NOT created; instead run the inline snippet in Step 3.

**Interfaces:**
- Produces: `class BrowserSession` with:
  - `__init__(self, config: Config)`
  - `async start(headed: bool | None = None) -> None` — launches persistent context (`config.profile_dir`, viewport 1280×900), navigates to `config.base_url`, waits for either `sel.CHATLIST` or `sel.AUTH_PAGES` (up to 60s).
  - `async stop() -> None`
  - `page` property (raises `RuntimeError` if not started)
  - `async is_logged_in() -> bool` — `sel.CHATLIST` count > 0
  - `async ensure_logged_in() -> None` — raises `NotLoggedIn`
  - `async ensure_started() -> None` — lazy start guard used by ops
  - `async login_interactive(timeout_s: int = 300) -> dict` — if already logged in return `{"status": "already_logged_in"}`; else relaunch headed, poll `is_logged_in()` every 2s until timeout (return `{"status": "logged_in"}`) or raise `WaitTimeout`; relaunch back to configured headless mode afterwards.

- [ ] **Step 1: Implement**

```python
from __future__ import annotations

import asyncio

from playwright.async_api import BrowserContext, Page, async_playwright

from . import selectors as sel
from .config import Config
from .errors import NotLoggedIn, WaitTimeout


class BrowserSession:
    def __init__(self, config: Config):
        self.config = config
        self._pw = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("session not started")
        return self._page

    async def ensure_started(self) -> None:
        if self._page is None:
            await self.start()

    async def start(self, headed: bool | None = None) -> None:
        await self.stop()
        headed = self.config.headed if headed is None else headed
        self.config.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            str(self.config.profile_dir),
            headless=not headed,
            viewport={"width": 1280, "height": 900},
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        await self._page.goto(self.config.base_url, wait_until="domcontentloaded")
        await self._page.wait_for_selector(
            f"{sel.CHATLIST}, {sel.AUTH_PAGES}", state="attached", timeout=60_000
        )

    async def stop(self) -> None:
        if self._ctx is not None:
            await self._ctx.close()
            self._ctx = self._page = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None

    async def is_logged_in(self) -> bool:
        await self.ensure_started()
        return await self.page.locator(sel.CHATLIST).count() > 0

    async def ensure_logged_in(self) -> None:
        if not await self.is_logged_in():
            raise NotLoggedIn()

    async def login_interactive(self, timeout_s: int = 300) -> dict:
        if await self.is_logged_in():
            return {"status": "already_logged_in"}
        await self.start(headed=True)
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            if await self.page.locator(sel.CHATLIST).count() > 0:
                await self.start()  # back to configured (headless) mode
                return {"status": "logged_in"}
            await asyncio.sleep(2)
        await self.start()
        raise WaitTimeout(timeout_s)
```

- [ ] **Step 2: Live smoke test (network, no login needed)**

Run:
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "
import asyncio
from telegram_user_mcp.config import Config
from telegram_user_mcp.session import BrowserSession

async def main():
    s = BrowserSession(Config.from_env({'TG_MCP_PROFILE_DIR': 'spike/out/smoke-profile'}))
    print('logged_in:', await s.is_logged_in())
    await s.stop()

asyncio.run(main())"
```
Expected: `logged_in: False` (fresh profile shows auth page), no exception.

- [ ] **Step 3: Commit** — `git commit -m "feat: browser session lifecycle and login detection"`

---

### Task 6: telegram.py — core ops (open/send/read/wait)

**Files:**
- Create: `src/telegram_user_mcp/telegram.py`

**Interfaces:**
- Consumes: `BrowserSession`, `extract.read_messages`, selectors, errors.
- Produces: `class TelegramOps` with:
  - `__init__(self, session: BrowserSession)`
  - `async open_chat(query: str) -> dict` — normalizes `@user` / `https://t.me/user` / `t.me/user` to a username, navigates `location.hash = '#@username'` (Appendix A confirms format), waits for `sel.MESSAGE_INPUT`; raises `ChatNotFound` if WebK shows no chat within 10s. Returns `{"chat": username, "messages": [last 5 as dicts]}`.
  - `async send_message(text: str) -> dict` — focuses `sel.MESSAGE_INPUT`, types with 30ms delay, Enter; waits until an `is-out` bubble containing the text appears (5s); returns it as dict.
  - `async read_messages(limit: int = 20) -> list[dict]`
  - `async wait_for_message(timeout_s: float = 30, after_id: int | None = None) -> list[dict]` — baseline = max incoming id (or `after_id`); polls every 500 ms for incoming bubbles with `id > baseline`; returns the new ones or raises `WaitTimeout`.
- All ops call `await self.session.ensure_started()` then `await self.session.ensure_logged_in()` first (extract to `async def _ready(self)`).

- [ ] **Step 1: Implement** (complete code)

```python
from __future__ import annotations

import asyncio
import re

from . import extract
from . import selectors as sel
from .errors import ChatNotFound, SelectorBroken, WaitTimeout
from .session import BrowserSession

_USERNAME_RE = re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_]{3,})|@?([A-Za-z0-9_]{3,})$")


def _to_username(query: str) -> str:
    q = query.strip()
    m = _USERNAME_RE.match(q)
    if not m:
        raise ChatNotFound(query)
    return (m.group(1) or m.group(2))


class TelegramOps:
    def __init__(self, session: BrowserSession):
        self.session = session

    async def _ready(self):
        await self.session.ensure_started()
        await self.session.ensure_logged_in()
        return self.session.page

    async def open_chat(self, query: str) -> dict:
        page = await self._ready()
        username = _to_username(query)
        await page.evaluate("u => { location.hash = '#@' + u }", username)
        try:
            await page.wait_for_selector(sel.MESSAGE_INPUT, state="visible", timeout=10_000)
        except Exception:
            raise ChatNotFound(query)
        msgs = await extract.read_messages(page, limit=5)
        return {"chat": username, "messages": [m.to_dict() for m in msgs]}

    async def read_messages(self, limit: int = 20) -> list[dict]:
        page = await self._ready()
        return [m.to_dict() for m in await extract.read_messages(page, limit=limit)]

    async def send_message(self, text: str) -> dict:
        page = await self._ready()
        inp = page.locator(sel.MESSAGE_INPUT).last
        if not await inp.count():
            raise SelectorBroken("message input (is a chat open?)")
        await inp.click()
        await page.keyboard.type(text, delay=30)
        await page.keyboard.press("Enter")
        deadline = asyncio.get_event_loop().time() + 5
        while asyncio.get_event_loop().time() < deadline:
            msgs = await extract.read_messages(page, limit=10)
            mine = [m for m in msgs if m.out and text.strip() in m.text]
            if mine:
                return mine[-1].to_dict()
            await asyncio.sleep(0.3)
        raise SelectorBroken("sent message bubble")

    async def wait_for_message(self, timeout_s: float = 30, after_id: int | None = None) -> list[dict]:
        page = await self._ready()
        if after_id is None:
            msgs = await extract.read_messages(page, limit=30)
            after_id = max((m.id for m in msgs), default=0)
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            msgs = await extract.read_messages(page, limit=30)
            fresh = [m for m in msgs if not m.out and not m.service and m.id > after_id]
            if fresh:
                return [m.to_dict() for m in fresh]
            await asyncio.sleep(0.5)
        raise WaitTimeout(timeout_s)
```

- [ ] **Step 2: Commit** — `git commit -m "feat: core chat operations"` (live verification happens in Task 11 e2e; extraction logic already unit-tested).

---

### Task 7: telegram.py — buttons, files, screenshots, clear

**Files:**
- Modify: `src/telegram_user_mcp/telegram.py` (extend TelegramOps)

**Interfaces:**
- Produces (added methods):
  - `async click_button(text: str | None = None, row: int | None = None, col: int | None = None, message_id: int | None = None) -> dict` — targets inline keyboard of `message_id` or the last message that has buttons; matches by case-insensitive substring, or exact (row, col) 0-based; raises `ButtonNotFound(wanted, available)`; after click waits 1.5s and returns `{"clicked": label, "messages": last 5}`.
  - `async click_reply_button(text: str) -> dict` — same matching against `sel.REPLY_KEYBOARD_BUTTON` inside `sel.REPLY_KEYBOARD`.
  - `async send_file(path: str, caption: str | None = None) -> dict` — `page.set_input_files(sel.FILE_INPUT, path)`; waits for `sel.ATTACH_POPUP`; optionally types caption; clicks `sel.ATTACH_POPUP_SEND`; waits for new `is-out` bubble (10s).
  - `async clear_chat() -> dict` — clicks `sel.TOPBAR_MENU_BUTTON`, then menu item whose text contains "Clear"? (exact label from Appendix A), checks the "Delete for all"-style checkbox if present, confirms via `sel.POPUP_BUTTON` containing "Clear"/"Delete"; returns `{"status": "cleared"}`.
  - `async screenshot(scope: str = "chat", message_id: int | None = None) -> bytes` — `chat` → `sel.CHAT_CONTAINER` locator screenshot; `message` → `f'{sel.BUBBLE}[data-mid="{message_id}"]'`; `window` → full page.
- Button clicking uses one `page.evaluate` to enumerate buttons (returns flat list `{row, col, text}`), then clicks via `locator.nth()` — enumeration and click both go through selectors from `selectors.py`.

- [ ] **Step 1: Implement** (complete code — enumerate + match helper `_match_button(buttons, text, row, col)` raising `ButtonNotFound`; keep under 120 lines).

```python
    async def _buttons_of_target(self, page, message_id: int | None):
        js = """
        (args) => {
          let bubble = null;
          if (args.mid) bubble = document.querySelector(`${args.bubbleSel}[data-mid="${args.mid}"]`);
          else {
            const all = Array.from(document.querySelectorAll(args.bubbleSel)).filter(b => b.querySelector(args.btnSel));
            bubble = all[all.length - 1] || null;
          }
          if (!bubble) return null;
          const out = [];
          Array.from(bubble.querySelectorAll(args.rowSel)).forEach((row, ri) => {
            Array.from(row.querySelectorAll(args.btnSel)).forEach((btn, ci) => {
              out.push({row: ri, col: ci, text: (btn.innerText || '').trim(), mid: Number(bubble.dataset.mid || 0)});
            });
          });
          return out;
        }
        """
        return await page.evaluate(js, {
            "mid": message_id, "bubbleSel": sel.BUBBLE,
            "rowSel": sel.INLINE_ROW, "btnSel": sel.INLINE_BUTTON,
        })

    async def click_button(self, text=None, row=None, col=None, message_id=None) -> dict:
        page = await self._ready()
        buttons = await self._buttons_of_target(page, message_id)
        if not buttons:
            raise ButtonNotFound(text or f"({row},{col})", [])
        target = None
        if text is not None:
            matches = [b for b in buttons if text.lower() in b["text"].lower()]
            target = matches[0] if matches else None
        elif row is not None and col is not None:
            matches = [b for b in buttons if b["row"] == row and b["col"] == col]
            target = matches[0] if matches else None
        if target is None:
            raise ButtonNotFound(text or f"({row},{col})", [b["text"] for b in buttons])
        bubble = page.locator(f'{sel.BUBBLE}[data-mid="{target["mid"]}"]')
        idx = [b for b in buttons].index(target)
        await bubble.locator(sel.INLINE_BUTTON).nth(idx).click()
        await asyncio.sleep(1.5)
        msgs = await extract.read_messages(page, limit=5)
        return {"clicked": target["text"], "messages": [m.to_dict() for m in msgs]}
```

(click_reply_button / send_file / clear_chat / screenshot follow the same structure with the exact selectors; implement fully in this task.)

- [ ] **Step 2: Commit** — `git commit -m "feat: buttons, attachments, screenshots, clear chat"`

---

### Task 8: miniapp.py — escape hatch

**Files:**
- Create: `src/telegram_user_mcp/miniapp.py`

**Interfaces:**
- Produces: `class MiniAppOps`:
  - `__init__(self, session: BrowserSession)`
  - `async open(button_text: str | None = None) -> dict` — clicks a web-app inline button (reuses TelegramOps.click_button when `button_text` given, else the last bubble button flagged web-app in Appendix A), waits for `sel.WEBAPP_IFRAME` (15s), returns `{"status": "open", "url": iframe.url}`.
  - `_frame()` — returns the Playwright `Frame` for `sel.WEBAPP_IFRAME`, raises `MiniAppNotOpen`.
  - `async snapshot(max_elements: int = 150) -> str` — numbered tree of interactive/visible elements inside the frame: `[ref] role/tag "text"` lines, refs are `data-tgmcp-ref` attributes stamped by the snapshot JS.
  - `async click(ref: str) -> dict`, `async type(ref: str, text: str) -> dict` — locate by stamped attribute inside frame.
  - `async screenshot() -> bytes` — iframe element screenshot.
  - `async close() -> dict` — clicks `sel.WEBAPP_CLOSE`, waits for iframe detach.

- [ ] **Step 1: Implement** — snapshot JS stamps sequential refs:

```python
SNAPSHOT_JS = """
(max) => {
  let n = 0;
  const lines = [];
  const interesting = document.querySelectorAll(
    'a, button, input, textarea, select, [role], [onclick], h1, h2, h3, label, [data-tgmcp-ref]');
  for (const el of interesting) {
    if (n >= max) break;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const ref = 'e' + (++n);
    el.setAttribute('data-tgmcp-ref', ref);
    const role = el.getAttribute('role') || el.tagName.toLowerCase();
    const text = (el.innerText || el.value || el.placeholder || '').trim().slice(0, 80);
    lines.push(`[${ref}] ${role} "${text}"`);
  }
  return lines.join('\\n');
}
"""
```

- [ ] **Step 2: Commit** — `git commit -m "feat: Mini App escape hatch"`

---

### Task 9: server.py — FastMCP tools

**Files:**
- Create: `src/telegram_user_mcp/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `build_server(config: Config | None = None) -> FastMCP` and module-level `mcp = build_server()` for `mcp run`. Tools (names exactly): `tg_status`, `tg_login`, `tg_open_chat`, `tg_send_message`, `tg_send_file`, `tg_read_messages`, `tg_wait_for_message`, `tg_click_button`, `tg_click_reply_button`, `tg_clear_chat`, `tg_screenshot`, `tg_miniapp_open`, `tg_miniapp_snapshot`, `tg_miniapp_click`, `tg_miniapp_type`, `tg_miniapp_screenshot`, `tg_miniapp_close`.
- Every tool body: `try: ... except AdapterError as e: return json.dumps(e.to_payload())`. Screenshots return `mcp.server.fastmcp.Image(data=png, format="png")`. JSON results via `json.dumps(..., ensure_ascii=False)`.
- Session/ops are lazy singletons created at first tool call (`_state = {"session": None, ...}`).

- [ ] **Step 1: Write the failing test**

`tests/test_server.py`:
```python
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from telegram_user_mcp.config import Config
from telegram_user_mcp.server import build_server

EXPECTED_TOOLS = {
    "tg_status", "tg_login", "tg_open_chat", "tg_send_message", "tg_send_file",
    "tg_read_messages", "tg_wait_for_message", "tg_click_button",
    "tg_click_reply_button", "tg_clear_chat", "tg_screenshot",
    "tg_miniapp_open", "tg_miniapp_snapshot", "tg_miniapp_click",
    "tg_miniapp_type", "tg_miniapp_screenshot", "tg_miniapp_close",
}


@pytest.fixture()
def server(tmp_path):
    cfg = Config.from_env({"TG_MCP_PROFILE_DIR": str(tmp_path / "profile")})
    return build_server(cfg)


async def test_all_tools_listed(server):
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tools = await client.list_tools()
        assert EXPECTED_TOOLS <= {t.name for t in tools.tools}


async def test_status_reports_mode_without_browser(server):
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        res = await client.call_tool("tg_status", {})
        payload = json.loads(res.content[0].text)
        assert payload["mode"] == "prod"
        assert payload["logged_in"] is False
```

(`tg_status` must not launch the browser when the profile dir has no `Default` subdir — report `logged_in: false` cheaply. This keeps the test offline.)

- [ ] **Step 2: Implement server.py** — pattern (full body in repo, one tool shown):

```python
import json
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from .config import Config
from .errors import AdapterError
from .miniapp import MiniAppOps
from .session import BrowserSession
from .telegram import TelegramOps


def build_server(config: Config | None = None) -> FastMCP:
    cfg = config or Config.from_env()
    mcp = FastMCP("telegram-user")
    state: dict[str, Any] = {}

    def session() -> BrowserSession:
        if "session" not in state:
            state["session"] = BrowserSession(cfg)
        return state["session"]

    def ops() -> TelegramOps:
        if "ops" not in state:
            state["ops"] = TelegramOps(session())
        return state["ops"]

    def apps() -> MiniAppOps:
        if "apps" not in state:
            state["apps"] = MiniAppOps(session())
        return state["apps"]

    def _json(data) -> str:
        return json.dumps(data, ensure_ascii=False)

    @mcp.tool()
    async def tg_status() -> str:
        """Report adapter mode, login state and profile location."""
        s = session()
        has_profile = (cfg.profile_dir / "Default").exists()
        logged_in = False
        if has_profile:
            try:
                logged_in = await s.is_logged_in()
            except AdapterError as e:
                return _json(e.to_payload())
        return _json({"mode": cfg.mode, "logged_in": logged_in,
                      "profile_dir": str(cfg.profile_dir)})

    @mcp.tool()
    async def tg_send_message(text: str) -> str:
        """Send a text message or /command to the currently open chat."""
        try:
            return _json(await ops().send_message(text))
        except AdapterError as e:
            return _json(e.to_payload())

    # ... same pattern for every remaining tool ...
    return mcp


mcp = build_server()
```

- [ ] **Step 3: Run tests (PASS), commit** — `git commit -m "feat: MCP server with full tool surface"`

---

### Task 10: cli.py + entry point

**Files:**
- Create: `src/telegram_user_mcp/cli.py`

**Interfaces:**
- Produces: `main() -> None` (entry point `telegram-user-mcp`):
  - no args → `server.mcp.run()` (stdio MCP)
  - `login` → runs `BrowserSession(Config.from_env()).login_interactive()` via `asyncio.run`, prints status JSON
  - `status` → prints `tg_status`-equivalent JSON

```python
import argparse
import asyncio
import json


def main() -> None:
    parser = argparse.ArgumentParser(prog="telegram-user-mcp")
    sub = parser.add_subparsers(dest="cmd")
    login = sub.add_parser("login", help="open a browser window to log in once (QR)")
    login.add_argument("--timeout", type=int, default=300)
    sub.add_parser("status", help="print login/mode status")
    args = parser.parse_args()

    if args.cmd == "login":
        from .config import Config
        from .session import BrowserSession

        async def run():
            s = BrowserSession(Config.from_env())
            try:
                print(json.dumps(await s.login_interactive(args.timeout)))
            finally:
                await s.stop()

        asyncio.run(run())
    elif args.cmd == "status":
        from .config import Config
        from .session import BrowserSession

        async def run():
            cfg = Config.from_env()
            s = BrowserSession(cfg)
            try:
                print(json.dumps({"mode": cfg.mode, "logged_in": await s.is_logged_in()}))
            finally:
                await s.stop()

        asyncio.run(run())
    else:
        from .server import mcp
        mcp.run()
```

- [ ] **Step: Verify** `.venv/Scripts/telegram-user-mcp.exe status` prints `{"mode": "prod", "logged_in": false}`; commit — `git commit -m "feat: CLI entry point with login/status"`.

---

### Task 11: E2E — fixture bot + scenarios (requires user: one QR scan + bot token)

**Files:**
- Create: `e2e/fixture_bot.py`, `e2e/run_scenarios.py`

**Interfaces:**
- `fixture_bot.py`: plain `urllib` long-polling Bot API client (no external deps). Env `BOT_TOKEN`. Behaviors: `/start` → text + 2×2 inline keyboard (`A1 A2 / B1 B2`); callback press → `editMessageText` to `you pressed <label>`; `/kb` → reply keyboard (`Red / Green`); any text → echo `echo: <text>`; `/photo` → sends a generated PNG.
- `run_scenarios.py`: connects to the MCP server over stdio (`mcp` client SDK), runs: status → open_chat → send `/start` → wait → assert keyboard grid → click `A2` → wait for edit → assert text contains `you pressed A2` → send `hello` → wait → assert `echo: hello` → screenshot saved to `e2e/out/`. Prints PASS/FAIL per step, non-zero exit on failure.

- [ ] **Step 1:** Implement both files (complete code in repo).
- [ ] **Step 2:** Ask the user once for: (a) QR scan via `telegram-user-mcp login`, (b) a bot token for the fixture bot (from @BotFather).
- [ ] **Step 3:** Run fixture bot + `run_scenarios.py`; fix selectors against reality (this is where Appendix A guesses get corrected); update `tests/fixtures/bubbles.html` with REAL captured DOM (`page.content()` snippet) so unit tests pin reality.
- [ ] **Step 4:** Commit — `git commit -m "test: e2e fixture bot and scenario runner"`

---

### Task 12: README + packaging

**Files:**
- Create: `README.md`; Modify: `pyproject.toml` (classifiers, urls), `LICENSE` (MIT).

- [ ] **Step 1:** README (EN): what/why, quickstart (`uvx telegram-user-mcp`, `claude mcp add telegram -- uvx telegram-user-mcp`, one-time `login`), tool table, modes (prod default; test-DC reality + tdlib/td#3370 link), security note (profile = account key; dedicated account recommended), limitations (no voice recording, 1:1 bot chats), troubleshooting (`selector_broken` → issue template).
  README must include a **Test-DC runbook** section: (1) deterministic 99966 test accounts are disabled by Telegram; (2) register a test-DC account with a REAL phone number via official iOS app — tap Settings icon 10×, Accounts → Login to another account → Test; (3) log the adapter in with `TG_MCP_MODE=test telegram-user-mcp login` (QR scannable by the test-mode iOS app); (4) create the bot under test by messaging @BotFather *inside the test DC* from that account; (5) run the bot's code against `https://api.telegram.org/bot<token>/test/` (the bot is a token, not a phone number — the same single test account can both create the bot and act as the test user).
- [ ] **Step 2:** `uv build` succeeds; `uvx --from dist/telegram_user_mcp-0.1.0-py3-none-any.whl telegram-user-mcp status` works.
- [ ] **Step 3:** Commit — `git commit -m "docs: README and packaging polish"`. (Actual PyPI publish: user decision.)

---

## Appendix A: WebK selector recon (source-derived)

*(filled from the tweb source recon report — see below)*
