# Telegram User Adapter (MCP) — Design

**Date:** 2026-07-13
**Status:** approved (user delegated remaining decisions)

## Purpose

A public tool that lets an AI agent (Claude Code or any MCP client) test a Telegram
bot **exactly as a real user does** — through the official web client in a real
browser, not through MTProto libraries (telethon etc.). Target scenarios: design
review and functional testing of bots — text/commands, inline & reply keyboards,
media, Mini Apps — "everything a user can do".

## Key decisions

| Decision | Choice | Why |
|---|---|---|
| Form factor | MCP server (stdio) | Same mechanism as browser adapters (claude-in-chrome / Playwright MCP); direct agent integration; publishable |
| Engine | Real browser driving web.telegram.org via Playwright | Official client → the bot sees a real user; DOM gives reliable structured reads + pixel screenshots |
| Language | Python + Playwright | User preference; MCP Python SDK (FastMCP) |
| Architecture | Semantic Telegram tools + generic escape-hatch tools for Mini Apps (option C) | 95% of work cheap/reliable via semantic tools; Mini Apps are arbitrary web apps and need generic iframe interaction |
| Environments | Both Telegram **test DC** and **production**, default = `prod` | **Spike finding (2026-07-13):** deterministic test accounts (`99966XYYYY`, code X×N) are **disabled by Telegram** since ~Oct 2024 (confirmed empirically on DC2/DC3 via WebK and direct MTProto probe; authoritative: TDLib maintainer in tdlib/td#3370 — "Test accounts are disabled currently", registration only via official iOS app with a real number). Zero-touch test login is therefore impossible → default flips to `prod` with a dedicated account (one-time QR login, persistent profile). `test` mode is kept for users who already own a test-DC account; WebK supports it via `?test=1` (verified: connects to `apiws_test`) |
| Desktop client | Not in v1 | No automation API / accessibility tree in tdesktop; bot cannot distinguish clients anyway; possible later as a screenshot-only visual mode |

## Architecture

```
Claude Code ◄─stdio─► MCP server (Python, mcp SDK / FastMCP)
                        server.py    — tool definitions, arg validation
                        session.py   — Playwright lifecycle, persistent context,
                                       mode selection (test/prod), profile dirs
                        telegram.py  — semantic ops: chats, messages, buttons,
                                       structured extraction
                        miniapp.py   — generic iframe interaction (snapshot/click/type)
                        selectors.py — ALL DOM selectors in one place
                             │ drives
                        Chromium (persistent profile ~/.telegram-user-mcp/profile-<mode>)
                             → web.telegram.org (WebK /k or WebA /a — spike decides)
```

- **Own managed browser**, never the user's: Playwright Chromium with a persistent
  profile per mode (`profile-test/`, `profile-prod/`). Session survives restarts.
- **Headless by default**; `--headed` flag to watch. Any tool can return screenshots.
- **Login:**
  - `prod` mode (default): `tg_login` / CLI `login` opens a headed window with the
    QR code; user scans once with a (recommended dedicated) account; session
    persists in the profile.
  - `test` mode: same QR/code login against WebK `?test=1`, but requires an
    already-registered test-DC account (Telegram disabled public test-account
    creation — see tdlib/td#3370). Documented honestly in README.
- **Client choice: WebK (`/k`)** — resolved by spike. WebA's test mode is
  build-time only (`APP_ENV === 'test'`), while WebK switches at runtime via
  `?test=1` and propagates it into the MTProto worker (verified in source:
  `apiManagerProxy` sets `url.searchParams.set('test','1')`; endpoint suffix
  `apiws_test`). Login flow automation verified hands-on: phone form and 5-cell
  code input are scriptable.
- **Security:** the profile dir is an account key. Created with user-only permissions;
  README warns and recommends a dedicated account for prod mode.

## Tool surface (v1)

Session:
- `tg_status` — mode, logged-in?, own identity, current chat
- `tg_login` — test: auto-create account; prod: interactive QR window

Chat & messages (all reads return structured JSON: id, direction, sender, text,
time, button grid, media descriptor, reply-to):
- `tg_open_chat(query)` — @username / t.me link / display name
- `tg_send_message(text)` — text or /command
- `tg_send_file(path, kind=auto|photo|document)`
- `tg_read_messages(limit=20)`
- `tg_wait_for_message(timeout_s=30)` — core test primitive: block until the bot replies
- `tg_click_button(text | row,col, message_id?)` — inline keyboard; default: last message with buttons
- `tg_click_reply_button(text)` — reply keyboard
- `tg_clear_chat` — history wipe for test isolation
- `tg_screenshot(scope=chat|window|message, message_id?)`

Mini Apps (escape hatch):
- `tg_miniapp_open(button_text?)`, `tg_miniapp_snapshot()` (element tree with refs,
  Playwright-MCP style), `tg_miniapp_click(ref)`, `tg_miniapp_type(ref, text)`,
  `tg_miniapp_screenshot()`, `tg_miniapp_close()`

Known v1 limitation: no microphone-style voice recording (candidate for v1.1 via
Playwright fake media stream); audio files can be sent as attachments.

## Error handling

Every tool returns typed errors with actionable hints:
- `not_logged_in` → "run tg_login"
- `chat_not_found` → query echoed back
- `button_not_found` → includes the buttons that ARE present
- `timeout` → includes current last messages so the agent sees the actual state
- `selector_broken` → Telegram markup changed; link to issue template

## Testing strategy

- **Unit:** message/keyboard extraction against saved HTML fixtures of the chosen
  web client; selector table sanity.
- **E2E (the main proof):** a real (dedicated) account on prod talks to our own
  **fixture bot** (small Python bot using plain Bot API HTTP long-polling — the
  bot side legitimately uses Bot API; the *user* side is the browser). Fixture
  bot echoes text, serves inline/reply keyboards, sends media, edits messages on
  callback. Requires a one-time QR login by a human; afterwards the persistent
  profile makes E2E repeatable. CI runs lint + unit only.
- **Self-verification:** drive full scenarios through the MCP tools themselves
  (send /start → wait reply → click button → assert edit → screenshot).

## Distribution

- PyPI package `telegram-user-mcp` (name checked at publish time), MIT license.
- Install/run: `uvx telegram-user-mcp` (stdio MCP); README shows
  `claude mcp add telegram -- uvx telegram-user-mcp`.
- Config via env/flags: `TG_MCP_MODE=test|prod`, `TG_MCP_HEADED=1`,
  `TG_MCP_PROFILE_DIR=...`.
- README in English (public project), with a security note and test-DC explainer
  (including the `/test/` Bot API requirement for bot developers).

## Out of scope (v1)

- Telegram Desktop automation, voice recording, calls, secret chats (bots can't
  use them), groups/channels beyond 1:1 bot chats (tools are chat-generic where
  free, but only 1:1 bot chats are tested), payments UI beyond what inline
  buttons already cover.
