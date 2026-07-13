from __future__ import annotations

from dataclasses import asdict, dataclass

from . import selectors as sel

MESSAGES_JS = """
(args) => {
  const bubbles = Array.from(document.querySelectorAll(args.bubbleSel)).slice(-args.limit);
  return bubbles.map(b => {
    const textEl = b.querySelector(args.textSel);
    const timeEl = b.querySelector(args.timeSel);
    const rows = [];
    for (const row of b.querySelectorAll(args.rowSel)) {
      const btns = Array.from(row.querySelectorAll(args.btnSel)).map(x => {
        const t = x.querySelector(args.btnTextSel);
        return ((t ? t.innerText : x.innerText) || '').trim();
      });
      if (btns.length) rows.push(btns);
    }
    let media = null;
    for (const [cls, kind] of args.mediaBubbleClasses) {
      if (b.classList.contains(cls)) { media = kind; break; }
    }
    if (!media) {
      for (const [q, kind] of args.mediaInnerSelectors) {
        if (b.querySelector(q)) { media = kind; break; }
      }
    }
    let text = '';
    if (textEl) {
      const clone = textEl.cloneNode(true);
      clone.querySelectorAll(args.timeSel).forEach(t => t.remove());
      text = (clone.innerText || '').trim();
    }
    return {
      mid: Number(b.dataset.mid || 0),
      out: b.classList.contains('is-out'),
      service: b.classList.contains('service'),
      text,
      time: timeEl ? (timeEl.getAttribute('title') || timeEl.innerText || '').trim() : null,
      buttons: rows,
      media,
    };
  });
}
"""


@dataclass
class Message:
    id: int
    out: bool
    service: bool
    text: str
    time: str | None
    buttons: list[list[str]]
    media: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def shape_messages(raw: list[dict]) -> list[Message]:
    return [
        Message(
            id=int(r.get("mid") or 0),
            out=bool(r.get("out")),
            service=bool(r.get("service")),
            text=r.get("text") or "",
            time=r.get("time"),
            buttons=[[str(t) for t in row] for row in (r.get("buttons") or [])],
            media=r.get("media"),
        )
        for r in raw
    ]


def _js_args(limit: int) -> dict:
    return {
        "bubbleSel": sel.BUBBLE,
        "textSel": sel.BUBBLE_TEXT,
        "timeSel": sel.BUBBLE_TIME,
        "rowSel": sel.INLINE_ROW,
        "btnSel": sel.INLINE_BUTTON,
        "btnTextSel": sel.INLINE_BUTTON_TEXT,
        "mediaBubbleClasses": sel.MEDIA_BUBBLE_CLASSES,
        "mediaInnerSelectors": sel.MEDIA_KIND_SELECTORS,
        "limit": limit,
    }


async def read_messages(page, limit: int = 20) -> list[Message]:
    raw = await page.evaluate(MESSAGES_JS, _js_args(limit))
    return shape_messages(raw)
