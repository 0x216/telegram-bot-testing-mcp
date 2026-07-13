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
LOGIN_PHONE_BUTTON_TEXT = "Log in by phone Number"       # [live] QR page button
PHONE_INPUT = ".input-field-phone .input-field-input"    # [src] telInputField.ts:24 + [live]
AUTH_NEXT_BUTTON = "#auth-pages button.btn-primary.btn-color-primary"  # [src] SignInCard.tsx:260
CODE_SENT_MARKER_TEXT = "sent you an SMS"                # [live] code screen indicator
QR_CANVAS = "#auth-pages canvas"                          # [src] SignQRCard.tsx:226

# --- chat / messages -------------------------------------------------------------
BUBBLE = ".bubble[data-mid]"                 # [src] bubbles.ts:6183/6488
BUBBLE_TEXT = ".message, .service-msg"       # [src] bubbles.ts:6480 / 6356
BUBBLE_TIME = ".time"                        # [src] messageRender.ts:312
INLINE_ROW = ".reply-markup-row"             # [src] replyMarkupLayout.tsx:67
INLINE_BUTTON = ".reply-markup-button"       # [src] replyMarkupLayout.tsx:93
INLINE_BUTTON_TEXT = ".reply-markup-button-text"  # [src] replyMarkupLayout.tsx:107
REPLY_KEYBOARD = ".reply-keyboard"           # [src] replyKeyboard.tsx:21
REPLY_KEYBOARD_BUTTON = ".reply-keyboard-button"  # [src] replyKeyboard.tsx:134
REPLY_KEYBOARD_TOGGLE = ".toggle-reply-markup, .btn-icon.toggle-reply-markup"  # [e2e]

# media kind detection: bubble-level classes checked via classList [src] bubbles.ts
MEDIA_BUBBLE_CLASSES = [
    ["sticker", "sticker"],                  # [src] bubbles.ts:6057
    ["round", "round_video"],                # [src] bubbles.ts:7952
    ["video", "video"],                      # [src] bubbles.ts:8385
    ["photo", "photo"],                      # [src] bubbles.ts:7744
]
# inner containers checked via querySelector, first match wins
MEDIA_KIND_SELECTORS = [
    [".audio.is-voice", "voice"],            # [e2e] refined from [src] .audio
    [".audio", "audio"],                     # [src] bubbles.ts:8479
    [".document", "document"],               # [src] bubbles.ts:8479
]

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
