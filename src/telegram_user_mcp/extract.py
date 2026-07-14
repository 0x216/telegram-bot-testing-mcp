from __future__ import annotations

from dataclasses import asdict, dataclass

from . import js
from . import selectors as sel


@dataclass
class Message:
    id: int
    out: bool
    service: bool
    text: str
    time: str | None
    buttons: list[list[str]]
    media: str | None
    sending: bool = False
    failed: bool = False  # named 'failed', not 'error': tool payloads reserve
                          # the 'error' key for adapter errors
    reply_to: dict | None = None       # {"title", "quote"} of the replied message
    forwarded_from: str | None = None  # origin name of a forwarded message
    sender: str | None = None          # shown only in group-like contexts
    poll: dict | None = None           # {"question", "options": [...]}
    # fractional ordering key: pending bubbles have mids like 208.0001
    sort_id: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("sort_id")
        return d


def shape_messages(raw: list[dict]) -> list[Message]:
    out = []
    for r in raw:
        mid = float(r.get("mid") or 0)
        # mid 0 = placeholder bubbles ("No messages here yet"), not messages
        if mid <= 0:
            continue
        out.append(Message(
            id=int(mid),
            out=bool(r.get("out")),
            service=bool(r.get("service")),
            text=r.get("text") or "",
            time=r.get("time"),
            buttons=[[str(t) for t in row] for row in (r.get("buttons") or [])],
            media=r.get("media"),
            sending=bool(r.get("sending")),
            failed=bool(r.get("failed")),
            reply_to=r.get("reply_to"),
            forwarded_from=r.get("forwarded_from"),
            sender=r.get("sender"),
            poll=r.get("poll"),
            sort_id=mid,
        ))
    return out


def _js_args(limit: int) -> dict:
    return {
        "bubbleSel": f"{sel.ACTIVE_CHAT} {sel.BUBBLE}",
        "textSel": sel.BUBBLE_TEXT,
        "timeSel": sel.BUBBLE_TIME,
        "rowSel": sel.INLINE_ROW,
        "btnSel": sel.INLINE_BUTTON,
        "btnTextSel": sel.INLINE_BUTTON_TEXT,
        "mediaDetectors": sel.MEDIA_DETECTORS,
        "replyTitleSel": sel.REPLY_TITLE,
        "replyQuoteSel": sel.REPLY_QUOTE,
        "nameTitleSel": sel.NAME_TITLE,
        "pollContentSel": sel.POLL_CONTENT,
        "pollTextsSel": sel.POLL_TEXTS,
        "limit": limit,
    }


async def read_messages(page, limit: int = 20) -> list[Message]:
    raw = await page.evaluate(js.MESSAGES, _js_args(limit))
    return shape_messages(raw)
