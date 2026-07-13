"""Every DOM selector for Telegram WebK lives here — the single file to fix
when Telegram changes its markup.

Sources: [live] = verified against web.telegram.org/k during development;
[tweb] = derived from github.com/morethanwords/tweb sources; [e2e] = to be
confirmed by the e2e run (Task 11).
"""

# --- app state --------------------------------------------------------------
# Both nodes are always in the DOM; visibility decides the state. [live]
LOGGED_IN_MARKER = "#page-chats"
AUTH_PAGES = "#auth-pages"
CHATLIST = ".chatlist"                       # [tweb] left column chat list

# --- login flow (all [live], scripted in spike) ------------------------------
LOGIN_PHONE_BUTTON_TEXT = "Log in by phone Number"   # button text on QR page
PHONE_INPUT = "div.input-field-phone .input-field-input"
NEXT_BUTTON_ROLE = ("button", "Next")                # get_by_role args
CODE_SENT_MARKER_TEXT = "sent you an SMS"            # code screen indicator
QR_CANVAS = ".auth-image canvas, .qr-canvas, canvas" # [e2e]

# --- chat / messages ---------------------------------------------------------
BUBBLE = ".bubble[data-mid]"                 # [tweb] one message bubble
BUBBLE_TEXT = ".message"                     # [tweb] text container inside bubble
BUBBLE_TIME = ".time"                        # [tweb] time element inside .message
INLINE_ROW = ".reply-markup-row"             # [tweb] inline keyboard row
INLINE_BUTTON = ".reply-markup-button"       # [tweb] inline keyboard button
REPLY_KEYBOARD = ".reply-keyboard"           # [e2e] reply keyboard panel
REPLY_KEYBOARD_BUTTON = ".btn-text, button"  # [e2e]
REPLY_KEYBOARD_TOGGLE = ".toggle-reply-markup, .btn-icon.chat-input-secondary-button"  # [e2e]

# media kind detection inside a bubble: (selector, kind) pairs, first match wins
MEDIA_KIND_SELECTORS = [
    [".media-photo", "photo"],               # [tweb]
    [".media-video", "video"],               # [tweb]
    [".media-sticker, .sticker", "sticker"], # [tweb]
    [".audio.is-voice", "voice"],            # [tweb]
    [".audio", "audio"],                     # [tweb]
    [".document", "document"],               # [tweb]
]

# --- composing / sending ------------------------------------------------------
MESSAGE_INPUT = ".input-message-input"       # [tweb] contenteditable composer
SEND_BUTTON = ".btn-send"                    # [tweb]
ATTACH_BUTTON = ".attach-file, .btn-icon.attach-file"  # [e2e]
FILE_INPUT = "input[type=file]"              # [tweb] hidden inputs used by attach menu
ATTACH_POPUP = ".popup-new-media"            # [tweb] send-media confirmation popup
ATTACH_POPUP_SEND = ".popup-new-media .btn-primary"    # [e2e]

# --- chat chrome ---------------------------------------------------------------
CHAT_CONTAINER = ".bubbles"                  # [tweb] scrollable message area
TOPBAR_MENU_BUTTON = ".chat-utils .btn-menu-toggle, .sidebar-header .btn-menu-toggle"  # [e2e]
MENU_ITEM = ".btn-menu-item"                 # [tweb] dropdown menu entry
POPUP_BUTTON = ".popup-button, .popup .btn"  # [e2e] confirmation popup buttons

# --- mini apps -------------------------------------------------------------------
WEBAPP_POPUP = ".popup-web-app"              # [tweb] web-app popup container
WEBAPP_IFRAME = ".popup-web-app iframe, iframe.web-app-frame"  # [e2e]
WEBAPP_CLOSE = ".popup-web-app .btn-icon.popup-close, .popup-web-app .popup-header .btn-icon"  # [e2e]
