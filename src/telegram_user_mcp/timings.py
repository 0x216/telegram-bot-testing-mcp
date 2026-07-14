"""Every wait, delay and timeout in one place.

Two kinds of values:
  * settle delays — short pauses for UI re-render; fixed.
  * timeouts — how long we're willing to wait for Telegram/network; these
    scale with TG_MCP_TIMEOUT_SCALE (e.g. 2.0 on slow networks or the
    congested test DC).
"""
from __future__ import annotations

import os

_SCALE = max(0.1, float(os.environ.get("TG_MCP_TIMEOUT_SCALE", "1") or 1))


def _t(seconds: float) -> float:
    return seconds * _SCALE


# --- typing ------------------------------------------------------------------
TYPE_DELAY_MS = 50            # per-character delay for search/phone fields
CODE_TYPE_DELAY_MS = 150      # login confirmation code cells

# --- settle delays (UI re-render pauses) --------------------------------------
UI_SETTLE_S = 0.3             # after typing/clicking before reading state
HISTORY_RENDER_S = 1.0        # after opening a chat
MID_SETTLE_S = 1.0            # optimistic message id -> server id
CALLBACK_SETTLE_S = 1.5       # after pressing an inline button
START_OVERLAY_S = 1.5         # after pressing the START control
KEYBOARD_TOGGLE_S = 0.7       # after toggling the reply keyboard
MENU_OPEN_S = 1.0             # after opening a dropdown/confirm popup
CARD_TRANSITION_S = 1.5       # auth card slide (QR -> phone form)
MINIAPP_BOOT_S = 1.5          # web app iframe boot
MINIAPP_ACTION_S = 0.5        # after click/type inside a mini app
SPA_RETRY_PAUSE_S = 2.0       # boot swallowed our keystrokes; wait and retry

# --- polling intervals ----------------------------------------------------------
POLL_FAST_S = 0.3
POLL_S = 0.5
POLL_SLOW_S = 1.0
LOGIN_POLL_S = 2.0

# --- timeouts (scaled) -----------------------------------------------------------
BOOT_TIMEOUT_MS = int(_t(60) * 1000)          # app shell becomes visible
SEARCH_ROUND_TIMEOUT_S = _t(15)               # one search round (rows appear)
SEARCH_ROUNDS = 3
CHAT_OPEN_TIMEOUT_MS = int(_t(10) * 1000)     # composer after opening a chat
SEND_CONFIRM_TIMEOUT_S = _t(10)               # our bubble appears after Enter
REPLY_CLICK_CONFIRM_S = _t(5)                 # reply-button press sends its label
WAIT_MESSAGE_DEFAULT_S = 30                   # tool default; caller-visible, unscaled
ATTACH_POPUP_TIMEOUT_MS = int(_t(10) * 1000)
FILE_CHOOSER_TIMEOUT_MS = int(_t(10) * 1000)
MENU_ITEM_TIMEOUT_MS = int(_t(5) * 1000)
UPLOAD_CONFIRM_TIMEOUT_S = _t(15)
VOICE_CONFIRM_TIMEOUT_S = _t(15)
VOICE_MAX_RECORD_S = 55                       # Telegram-side sanity cap, unscaled
MINIAPP_IFRAME_TIMEOUT_MS = int(_t(15) * 1000)
MINIAPP_CONFIRM_TIMEOUT_MS = int(_t(4) * 1000)
MINIAPP_CLOSE_TIMEOUT_MS = int(_t(4) * 1000)
LOGIN_CODE_SCREEN_TIMEOUT_S = _t(25)
LOGIN_STEP_TIMEOUT_S = _t(20)
