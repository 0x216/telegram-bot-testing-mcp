# telegram-bot-testing-mcp

**Write test scenarios for your Telegram bot — Claude runs them like a human QA.**

AI agents can already test any website through browser automation. This MCP server
gives them the same power over Telegram bots and Mini Apps: it drives the
**official Telegram Web client** (web.telegram.org) in a real browser. Your agent
gets exactly the input a real user gets — the same rendered chat, the same
keyboards, the same Mini App — so it can verify not just that the bot *responds*,
but that nothing is broken **visually**: keyboards render in the right shape,
edits land, media shows up, the Mini App actually opens.

Instead of clicking through your bot by hand after every deploy, you describe the
scenario once and let the agent execute it — sending /commands, pressing the
buttons, uploading files, comparing what it sees against what you expected, and
attaching screenshots as evidence.

No MTProto libraries, no session-string hacks, no bot token on the user side.
Telegram sees a normal, official web client.

## Why not telethon / Bot API?

- **Bot API** shows you the bot's side, not the user's. You can't see how your
  keyboard renders, whether the edit landed, or what a real user experiences.
- **MTProto userbot libraries** (telethon, gramjs, pyrogram) are custom clients:
  a different code path from real users, and account-ban-prone.
- **This adapter** is a real user session in the official client — what your
  agent sees is pixel-for-pixel what users see, structurally *and* visually.

## Quickstart

```bash
# 1. Install (Python 3.11+; from GitHub until the PyPI release)
uv tool install git+https://github.com/0x216/telegram-bot-testing-mcp
# download the browser (playwright lives inside the tool's env, so go through uvx):
uvx --from git+https://github.com/0x216/telegram-bot-testing-mcp playwright install chromium

# 2. Log in once (opens a browser window — scan the QR with a dedicated account)
telegram-bot-testing-mcp login

# 3. Add to Claude Code
claude mcp add telegram -- telegram-bot-testing-mcp
```

Then hand your agent a scenario instead of testing by hand:

> Run a regression pass on @my_bot:
> 1. `/start` — the welcome message must show the pricing keyboard, 2 rows of 2.
> 2. Press **Buy** — the bot must *edit* that message into a payment summary.
> 3. Send `PROMO2026` — the reply must confirm the discount.
> 4. Open the Mini App from the **Catalog** button and add the first item to cart.
> 5. Screenshot every step and flag anything that renders wrong.

The agent executes it step by step with the same input a human tester would have,
and reports what passed, what failed, and how it looked.

## Tools

| Tool | Purpose |
|------|---------|
| `tg_status` | Mode, login state, profile location |
| `tg_login` | One-time interactive login (QR window) |
| `tg_login_phone` / `tg_login_code` / `tg_login_password` | Headless login by phone number — the code arrives on the account's other devices |
| `tg_send_voice` | Record & send a real voice message through a fake microphone (WAV input) |
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
| `TG_MCP_TIMEOUT_SCALE` | `1` | Multiply all network-bound timeouts (e.g. `2` on slow networks / the congested test DC) |

## Security

The browser profile directory **is your Telegram session** — treat it like a
password. Use a **dedicated test account**, not your personal one: any
automation that can send messages from your account is worth isolating.
The profile stays on your machine; nothing is sent anywhere except to
Telegram itself.

## Headless servers (CI boxes, VPS)

Everything is headless by default, including login:

```bash
telegram-bot-testing-mcp login --phone +42077xxxxxxx
# the confirmation code arrives in the Telegram app on the account's
# other devices (or via SMS) — type it into the terminal prompt
```

Agents can do the same via `tg_login_phone` → `tg_login_code`
(→ `tg_login_password` for 2FA accounts).

Alternatively, log in once on a desktop machine (`login` opens a QR window)
and move the profile — it is just a directory and transfers fine across OSes
(verified Windows → Linux):

```bash
tar -czf tg-profile.tgz -C ~/.telegram-user-mcp profile-prod
scp tg-profile.tgz server:
ssh server 'mkdir -p ~/.telegram-user-mcp && tar -xzf tg-profile.tgz -C ~/.telegram-user-mcp'
```

Treat the archive like a password — it contains your session.

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
