"""Every JS snippet evaluated inside WebK, in one place.

Conventions: each snippet is a single arrow function taking one `args`
object (or one scalar); selectors come in via args — never hardcoded here.
"""

# Structured read of the last N message bubbles.
# Emoji render as <img alt> and line breaks as <br>, both lost by
# textContent on detached clones — restore them explicitly.
MESSAGES = """
(args) => {
  const bubbles = Array.from(document.querySelectorAll(args.bubbleSel)).slice(-args.limit);
  return bubbles.map(b => {
    const timeEl = b.querySelector(args.timeSel);
    const rows = [];
    for (const row of b.querySelectorAll(args.rowSel)) {
      const btns = Array.from(row.querySelectorAll(args.btnSel))
        .map(x => (x.querySelector(args.btnTextSel)?.innerText ?? x.innerText ?? '').trim());
      if (btns.length) rows.push(btns);
    }
    let media = args.mediaBubbleClasses.find(([cls]) => b.classList.contains(cls))?.[1]
             ?? args.mediaInnerSelectors.find(([q]) => b.querySelector(q))?.[1]
             ?? null;
    let text = '';
    const textEl = b.querySelector(args.textSel);
    if (textEl) {
      const clone = textEl.cloneNode(true);
      clone.querySelectorAll(args.timeSel).forEach(t => t.remove());
      clone.querySelectorAll('br').forEach(t => t.replaceWith('\\n'));
      clone.querySelectorAll('img[alt]').forEach(i => i.replaceWith(i.getAttribute('alt')));
      text = (clone.textContent ?? '').trim();
    }
    return {
      mid: Number(b.dataset.mid ?? 0),
      out: b.classList.contains('is-out'),
      service: b.classList.contains('service'),
      sending: b.classList.contains('is-sending') || b.classList.contains('is-outgoing'),
      failed: b.classList.contains('is-error'),
      text,
      time: (timeEl?.getAttribute('title') ?? timeEl?.innerText ?? null)?.trim() ?? null,
      buttons: rows,
      media,
    };
  });
}
"""

# Locate a chat in the search results. Two dropdown states exist: the quick
# view labels a bot row with subtitle "bot" (no username), the resolved list
# shows "@username" subtitles; row innerText concatenates fields with no
# separator, so match individual descendants. byTitle handles service chats
# ("Telegram Notifications") that have no username at all.
FIND_SEARCH_ROW = """
(args) => {
  const rows = Array.from(document.querySelectorAll(args.rowSel));
  const uname = args.username.toLowerCase();
  const textOf = el => (el?.textContent ?? '').trim().toLowerCase();
  if (args.byTitle) {
    return rows.findIndex(r => textOf(r.querySelector('.peer-title')) === uname);
  }
  const want = '@' + uname;
  const exact = rows.findIndex(r =>
    Array.from(r.querySelectorAll('*')).some(el => {
      const t = textOf(el);
      return t === want || t.startsWith(want + ',');
    }));
  if (exact >= 0) return exact;
  return rows.findIndex(r =>
    textOf(r.querySelector('.row-subtitle')) === 'bot'
    && textOf(r.querySelector('.peer-title')) === uname);
}
"""

# Enumerate inline-keyboard buttons of a message (by mid, or the last
# message that has buttons).
INLINE_BUTTONS = """
(args) => {
  let bubble;
  if (args.mid) {
    bubble = document.querySelector(`${args.bubbleSel}[data-mid="${args.mid}"]`);
  } else {
    const withButtons = Array.from(document.querySelectorAll(args.bubbleSel))
      .filter(b => b.querySelector(args.btnSel));
    bubble = withButtons.at(-1);
  }
  if (!bubble) return [];
  const out = [];
  Array.from(bubble.querySelectorAll(args.rowSel)).forEach((row, ri) => {
    Array.from(row.querySelectorAll(args.btnSel)).forEach((btn, ci) => {
      out.push({
        row: ri, col: ci,
        text: (btn.querySelector(args.btnTextSel)?.innerText ?? btn.innerText ?? '').trim(),
        mid: Number(bubble.dataset.mid ?? 0),
      });
    });
  });
  return out;
}
"""

# Focus the composer (or just read it, focus=false). Several
# .input-message-input nodes coexist; the active one carries data-peer-id
# and sits on top.
COMPOSER = """
(args) => {
  const els = Array.from(document.querySelectorAll(args.sel)).filter(e => e.offsetParent);
  const el = els.find(e => e.dataset.peerId) ?? els.at(-1);
  if (!el) return null;
  if (args.focus) el.focus();
  return el.textContent ?? '';
}
"""

# Number the interactive elements of a Mini App and stamp data-tgmcp-ref
# attributes for later click/type by ref. [id] elements are included so
# agents can read app state (outputs, counters).
MINIAPP_SNAPSHOT = """
(max) => {
  let n = 0;
  const lines = [];
  const interesting = document.querySelectorAll(
    'a, button, input, textarea, select, [role], [onclick], h1, h2, h3, label, [id], [data-tgmcp-ref]');
  for (const el of interesting) {
    if (n >= max) break;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const ref = 'e' + (++n);
    el.setAttribute('data-tgmcp-ref', ref);
    const role = el.getAttribute('role') ?? el.tagName.toLowerCase();
    const text = (el.innerText ?? el.value ?? el.placeholder ?? '').trim().slice(0, 80);
    lines.push(`[${ref}] ${role} "${text}"`);
  }
  return lines.join('\\n');
}
"""
