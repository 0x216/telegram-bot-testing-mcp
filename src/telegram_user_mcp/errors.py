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
            hint="Run the tg_login tool (or `telegram-bot-testing-mcp login`) and scan the QR code once.",
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
                         hint="The bot may be slow or not running; check tg_read_messages for current state.")


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
                              "or file an issue at github.com/0x216/telegram-bot-testing-mcp.")
