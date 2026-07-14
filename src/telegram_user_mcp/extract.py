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
      // WebK renders emoji as <img> (textContent drops them) and line breaks
      // as <br> (lost on detached clones) — restore both explicitly.
      clone.querySelectorAll('br').forEach(b => b.replaceWith('\\n'));
      clone.querySelectorAll('img[alt]').forEach(i => i.replaceWith(i.getAttribute('alt')));
      text = (clone.textContent || '').trim();
    }
    return {
      mid: Number(b.dataset.mid || 0),
      out: b.classList.contains('is-out'),
      service: b.classList.contains('service'),
      // pending messages carry fractional mids (e.g. 208.0001) and is-sending
      sending: b.classList.contains('is-sending') || b.classList.contains('is-outgoing'),
      failed: b.classList.contains('is-error'),
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
    sending: bool = False
    failed: bool = False  # named 'failed', not 'error': tool payloads reserve
                          # the 'error' key for adapter errors
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
        "mediaBubbleClasses": sel.MEDIA_BUBBLE_CLASSES,
        "mediaInnerSelectors": sel.MEDIA_KIND_SELECTORS,
        "limit": limit,
    }


async def read_messages(page, limit: int = 20) -> list[Message]:
    raw = await page.evaluate(MESSAGES_JS, _js_args(limit))
    return shape_messages(raw)
