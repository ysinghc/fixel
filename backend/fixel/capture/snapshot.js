// In-page DOM walker, evaluated per tile; rects are viewport coordinates.
() => {
  const INTERACTIVE = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[tabindex]:not([tabindex="-1"])';
  const KEEP = ['position','display','overflowX','overflowY','whiteSpace','textOverflow','zIndex',
                'fontSize','color','backgroundColor','borderTopWidth','pointerEvents','opacity'];
  document.querySelectorAll('[data-fixel-id]').forEach(e => e.removeAttribute('data-fixel-id'));
  const out = []; let id = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  for (let el = walker.currentNode; el; el = walker.nextNode()) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const texts = [...el.childNodes].filter(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
    let textRect = null;
    if (texts.length) {
      const range = document.createRange();
      range.setStartBefore(texts[0]); range.setEndAfter(texts.at(-1));
      const b = range.getBoundingClientRect();
      textRect = [b.left, b.top, b.right, b.bottom];
    }
    el.setAttribute('data-fixel-id', id);          // pre-order walk: a parent is tagged before its children
    const style = {}; for (const k of KEEP) style[k] = cs[k];
    out.push({
      id: id++,
      parent: el.parentElement?.closest('[data-fixel-id]')?.getAttribute('data-fixel-id') ?? null,
      tag: el.tagName.toLowerCase(),
      loc: el.closest('[data-loc]')?.getAttribute('data-loc') ?? null,
      rect: [r.left, r.top, r.right, r.bottom], text_rect: textRect,
      text: texts.map(n => n.textContent.trim()).join(' ').slice(0, 160),
      interactive: el.matches(INTERACTIVE),
      replaced: /^(img|svg|video|canvas|input|select|textarea|iframe)$/.test(el.tagName.toLowerCase()),
      style, scroll: [el.scrollWidth, el.clientWidth, el.scrollHeight, el.clientHeight],
    });
  }
  return { vw: innerWidth, vh: innerHeight, doc_w: document.documentElement.scrollWidth, elements: out };
}
