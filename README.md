# telegram-bot-testing-mcp

**Test Telegram bots and Mini Apps as a real user — from Claude Code or any MCP client.**

AI agents can already test any website through browser automation. This MCP server
gives them the same power over Telegram: it drives the **official Telegram Web
client** (web.telegram.org) in a real browser, so your agent interacts with your
bot exactly the way a human does — opens the chat, sends messages and files,
presses inline buttons, reads structured replies, opens Mini Apps, and takes
screenshots for design review.

No MTProto libraries, no session-string hacks, no bot token on the user side.
The Telegram servers see a normal, official web client.

## Why not telethon / Bot API?

- **Bot API** shows you the bot's side, not the user's. You can't see how your
  keyboard renders, whether the edit landed, or what a real user experiences.
- **MTProto userbot libraries** (telethon, gramjs, pyrogram) are custom clients:
  a different code path from real users, and account-ban-prone.
- **This adapter** is a real user session in the official client — what your
  agent sees is pixel-for-pixel what users see, structurally *and* visually.

## Quickstart

```bash
# 1. Install (Python 3.11+)
uv tool install telegram-bot-testing-mcp   # or: pipx install telegram-bot-testing-mcp
playwright install chromium

# 2. Log in once (opens a browser window — scan the QR with a dedicated account)
telegram-bot-testing-mcp login

# 3. Add to Claude Code
claude mcp add telegram -- telegram-bot-testing-mcp
```

Then just ask your agent: *"open a chat with @my_bot, send /start, press the
Pay button and show me a screenshot of the result."*

## Tools

| Tool | Purpose |
|------|---------|
| `tg_status` | Mode, login state, profile location |
| `tg_login` | One-time interactive login (QR window) |
| `tg_open_chat` | Open chat by `@username` / t.me link |
| `tg_send_message` | Send text or /command |
| `tg_send_file` | Attach & send photo/document (with caption) |
| `tg_read_messages` | Last N messages as structured JSON (text, buttons grid, media kind, ids) |
| `tg_wait_for_message` | Block until the bot replies — the core test primitive |
| `tg_click_button` | Press an inline button by text or row/col |
| `tg_click_reply_button` | Press a reply-keyboard button |
| `tg_clear_chat` | Wipe history (test isolation) |
| `tg_screenshot` | Screenshot chat / single message / window |
| `tg_miniapp_open` | Open a Mini App from a web-app button |
| `tg_miniapp_snapshot` | List interactive elements inside the Mini App (`[ref] role "text"`) |
| `tg_miniapp_click` / `tg_miniapp_type` | Interact with Mini App elements by ref |
| `tg_miniapp_screenshot` / `tg_miniapp_close` | Capture / close the Mini App |

All tools return typed errors with actionable hints (`not_logged_in`,
`button_not_found` + the buttons that *are* present, `timeout` + current chat
state, `selector_broken` when Telegram changes markup).

## Configuration

| Env var | Default | Meaning |
|---------|---------|---------|
| `TG_MCP_MODE` | `prod` | `prod` or `test` (Telegram test DC, adds `?test=1`) |
| `TG_MCP_HEADED` | off | `1` = show the browser window during operations |
| `TG_MCP_PROFILE_DIR` | `~/.telegram-user-mcp/profile-<mode>` | Browser profile location |

## Security

The browser profile directory **is your Telegram session** — treat it like a
password. Use a **dedicated test account**, not your personal one: any
automation that can send messages from your account is worth isolating.
The profile stays on your machine; nothing is sent anywhere except to
Telegram itself.

## Testing against the Telegram test DC

Telegram runs a separate test environment, and `TG_MCP_MODE=test` targets it.
Reality check as of 2026:

1. **Auto-created test accounts are disabled.** The documented `99966XYYYY`
   numbers with deterministic codes no longer work
   ([tdlib/td#3370](https://github.com/tdlib/td/issues/3370) — "Test accounts
   are disabled currently"). Don't believe older tutorials.
2. **Register with a real phone number via the official iOS app:** tap the
   Settings icon 10 times → Accounts → *Login to another account* → **Test**.
3. **Log the adapter in:** `TG_MCP_MODE=test telegram-bot-testing-mcp login` —
   scan the QR with the test-mode iOS app.
4. **Create your bot inside the test DC:** message `@BotFather` *from the test
   account* — it's a separate BotFather with separate tokens.
5. **Point your bot's code at the test Bot API route:**
   `https://api.telegram.org/bot<token>/test/METHOD` (the bot is a token, not
   a phone number — one test account can create the bot *and* act as the user).

For most workflows the default `prod` mode with a dedicated account is simpler.

## Limitations (v1)

- Voice-message *recording* is not supported (audio files send fine as attachments).
- Designed for 1:1 bot chats; groups/channels are untested.
- One server instance per profile (Chromium locks the profile directory).
- Telegram Web markup changes can break selectors — they live in one file
  (`selectors.py`), and every breakage surfaces as a typed `selector_broken`
  error. PRs welcome.

## Development

```bash
uv venv && uv pip install -e ".[dev]" && playwright install chromium
python -m pytest             # unit tests (offline, fixture DOM)
python e2e/fixture_bot.py    # BOT_TOKEN=... — the e2e fixture bot
python e2e/run_scenarios.py  # BOT=@your_fixture_bot — full scenario run
```

MIT license.
