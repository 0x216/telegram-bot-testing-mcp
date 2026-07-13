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
| Environments | Both Telegram **test DC** and **production**, default = `test` | Test DC: accounts auto-created from `99966XYYYY` numbers (code = X×5), zero-touch login, zero risk, CI-able. Prod: for live bots, one-time QR login with (recommended) dedicated account |
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
  - `test` mode: fully automatic — generate `99966XYYYY` number, submit code `XXXXX`,
    account is created by Telegram's test DC. Disposable accounts, no SIM.
  - `prod` mode: `tg_login` / CLI `login` opens a headed window with the QR code;
    user scans once; session persists in the profile.
- **Client choice (WebK vs WebA)** and the exact test-DC switching mechanism
  (URL param / localStorage / debug menu) are resolved by a hands-on spike before
  implementation; result recorded here.
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
- **E2E (the main proof):** against the real test DC — auto-created account talks to
  our own **fixture bot** (small Python bot using Bot API `/test/` endpoint via plain
  HTTP long-polling — bot side legitimately uses Bot API; the *user* side is the
  browser). Fixture bot echoes text, serves inline/reply keyboards, sends media,
  edits messages on callback. E2E runs locally; CI runs lint + unit (test DC is
  too flaky for required CI).
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
