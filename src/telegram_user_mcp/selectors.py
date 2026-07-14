"""Every DOM selector for Telegram WebK lives here — the single file to fix
when Telegram changes its markup.

Provenance: [src] = quoted from github.com/morethanwords/tweb sources
(recon 2026-07-13); [live] = verified against deployed web.telegram.org/k;
[e2e] = best guess pending e2e confirmation.

Caveat from recon: auth screens are SolidJS cards with CSS-module (hashed)
classes — anchor auth selectors on #auth-pages + element type + shared
component classes only.
"""

# --- app state ---------------------------------------------------------------
# Both nodes exist in the DOM; visibility decides the state. [live]
LOGGED_IN_MARKER = "#page-chats"
AUTH_PAGES = "#auth-pages"
CHATLIST_ITEM = "a.chatlist-chat"            # [src] appDialogsManager.ts:335, data-peer-id
SEARCH_INPUT = ".input-search input"         # [live] left-column search field
SEARCH_RESULT_ROW = ".search-group a[data-peer-id]"  # [live] global search rows (a.row)

# --- login flow ----------------------------------------------------------------
# Structural (locale-independent) selectors preferred; QR card's only
# transparent-secondary button is "Log in by phone Number".
LOGIN_PHONE_BUTTON = "#auth-pages button.btn-primary.btn-secondary"  # [src] SignQRCard.tsx:233
PHONE_INPUT = ".input-field-phone .input-field-input"    # [src] telInputField.ts:24 + [live]
AUTH_NEXT_BUTTON = "#auth-pages button.btn-primary.btn-color-primary"  # [src] SignInCard.tsx:260
AUTH_PHONE_HEADING = "#auth-pages h4"                    # [live] code screen shows the number
AUTH_ERROR = "#auth-pages .error, #auth-pages .input-field.error"  # [e2e] error state
PASSWORD_INPUT = "#auth-pages input[type=password]"      # structural 2FA marker
QR_CANVAS = "#auth-pages canvas"                          # [src] SignQRCard.tsx:226

# --- locale-sensitive UI text ------------------------------------------------------
# The ONLY place UI wording may be matched. WebK defaults to English on fresh
# profiles and BrowserSession pins the browser locale to en-US; text matchers
# below are fallbacks next to structural checks.
TEXT_LOGIN_PHONE_BUTTON = "Log in by phone Number"       # [live] QR page
TEXT_CODE_SENT = ("code", "sms")                          # [live] code screen body
TEXT_CODE_INVALID = ("invalid",)                          # [live] rejected code
TEXT_PASSWORD_SCREEN = ("password",)                      # [live] 2FA screen
TEXT_PHONE_REJECTED = ("invalid", "banned")               # [live] phone errors
# menu item: match English label or the tgico glyphs (font icons are
# locale-independent; delete =  in the current icon font) [live]
TEXT_DELETE_MENU = r"delete chat|clear history|"

# --- chat / messages -------------------------------------------------------------
# WebK keeps several chat containers in the DOM and reuses them; EVERYTHING
# chat-scoped must be looked up inside the active one, or reads/clicks land
# in a hidden neighbour (message ids even collide across containers). [live]
ACTIVE_CHAT = "#column-center .chat.active"
BUBBLE = ".bubble[data-mid]"                 # [src] bubbles.ts:6183/6488 (scope with ACTIVE_CHAT)
BUBBLE_TEXT = ".message, .service-msg"       # [src] bubbles.ts:6480 / 6356
BUBBLE_TIME = ".time"                        # [src] messageRender.ts:312
INLINE_ROW = ".reply-markup-row"             # [src] replyMarkupLayout.tsx:67
INLINE_BUTTON = ".reply-markup-button"       # [src] replyMarkupLayout.tsx:93
INLINE_BUTTON_TEXT = ".reply-markup-button-text"  # [src] replyMarkupLayout.tsx:107
REPLY_KEYBOARD = ".reply-keyboard"           # [src] replyKeyboard.tsx:21
REPLY_KEYBOARD_BUTTON = ".reply-keyboard-button"  # [src] replyKeyboard.tsx:134
REPLY_KEYBOARD_TOGGLE = ".toggle-reply-markup, .btn-icon.toggle-reply-markup"  # [e2e]

# media kind detection, ORDERED: entries are [how, key, kind] where how is
# "class" (bubble classList) or "inner" (querySelector). Geo must precede the
# "photo" class — locations render as photo bubbles with a map thumbnail.
# Dice renders as a plain animated sticker (no distinct marker). [live 2026-07]
MEDIA_DETECTORS = [
    ["class", "contact-message", "contact"],
    ["class", "poll-message", "poll"],
    ["inner", ".geo-footer", "venue"],
    ["inner", ".geo-container", "location"],
    ["class", "sticker", "sticker"],
    ["class", "round", "round_video"],
    ["class", "video", "video"],             # GIF/animation also lands here
    ["class", "photo", "photo"],
    ["inner", ".audio.is-voice", "voice"],
    ["inner", ".audio", "audio"],
    ["inner", ".document", "document"],
]

# message sub-structures [live 2026-07]
REPLY_TITLE = ".reply .reply-title .peer-title"   # who is being replied to
REPLY_QUOTE = ".reply .reply-subtitle"            # quoted text
NAME_TITLE = ".name .peer-title"                  # forward origin / group sender
POLL_CONTENT = ".poll-message-content"
POLL_TEXTS = ".translatable-message"              # first = question, rest = options

# --- composing / sending ----------------------------------------------------------
MESSAGE_INPUT = ".input-message-input"       # [src] input.ts:2913, contenteditable
START_CONTROL = ".chat-input-control"        # [live] START overlay on un-started bot chats
SEND_BUTTON = "button.btn-send"              # [src] input.ts:1305
ATTACH_BUTTON = ".attach-file"               # [src] input.ts:1256
FILE_INPUT = "input[type=file]"              # [src] input.ts:1268 (hidden, multiple)
ATTACH_POPUP = ".popup-new-media"            # [src] newMedia.ts:166
ATTACH_POPUP_SEND = ".popup-new-media .btn-primary.btn-color-primary"  # [src] popups/index.ts:196

# --- chat chrome --------------------------------------------------------------------
CHAT_CONTAINER = ".bubbles"                  # [src] bubbles.ts:1434
TOPBAR = ".sidebar-header.topbar"            # [src] topbar.ts:128
TOPBAR_MENU_BUTTON = ".sidebar-header.topbar .btn-menu-toggle:visible"  # [live] btnMore; hidden pinned-menu toggles share the class
MENU_ITEM = ".btn-menu-item"                 # [src] ButtonMenu convention
DELETE_POPUP = ".popup-delete-chat"          # [src] deleteDialog.ts:234
POPUP_DANGER_BUTTON = ".popup-button.btn.danger"  # [src] popups/index.ts:263

# --- mini apps -------------------------------------------------------------------------
# Deployed WebK opens web apps in a movable "Browser" window with CSS-module
# (hashed) classes; only these anchors are stable. [live 2026-07]
WEBAPP_WINDOW = ".movable-element"
WEBAPP_IFRAME = 'iframe[src*="tgWebAppData"], .web-app-body iframe'
WEBAPP_HEADER_BUTTONS = ".movable-element .btn-icon:visible"
WEBAPP_MAIN_BUTTON = ".web-app-button"       # [src] webApp.tsx:250
