// In-page elementFromPoint sampler: asks the browser what is on top at five points inside each
// interactive element. Run after snapshot.js, which assigns the data-fixel-id attributes.
//
// Hit testing skips elements with pointer-events:none, so a "ghost" banner that paints over a button but lets clicks
// through is invisible to it. A second pass makes every element hittable (pointer-events does not change paint order) and
// reports a cover as `ghost: true` when the top element, or an ancestor of it, was pointer-events:none. The user sees the
// button covered even though a click would still reach it; the opacity diff and the triage decide whether it matters.
() => {
  const INTERACTIVE = 'a[href],button,input,select,textarea,summary,[role=button],[role=link]';
  const pts = [[.5,.5],[.2,.2],[.8,.2],[.2,.8],[.8,.8]];
  const res = {};
  const targets = [];
  for (const el of document.querySelectorAll('[data-fixel-id]')) {
    if (!el.matches(INTERACTIVE)) continue;
    const r = el.getBoundingClientRect();
    if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) continue;
    targets.push([el, r]);
  }
  const sample = (el, r, ghosts) => {
    let covered = 0, by = null, n = 0;
    for (const [fx, fy] of pts) {
      const x = r.left + fx * r.width, y = r.top + fy * r.height;
      if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
      n++;
      const hit = document.elementFromPoint(x, y);
      if (hit && hit !== el && !el.contains(hit) && !hit.contains(el)) {
        covered++; by = hit.closest('[data-fixel-id]')?.getAttribute('data-fixel-id') ?? by;
      }
    }
    return { covered: n ? covered / n : 0, by: by === null ? null : +by };
  };
  for (const [el, r] of targets) {
    const s = sample(el, r);
    if (s.covered) res[el.getAttribute('data-fixel-id')] = s;
  }
  const none = new Set();
  for (const e of document.querySelectorAll('*')) if (getComputedStyle(e).pointerEvents === 'none') none.add(e);
  if (none.size) {
    // inline, not a stylesheet: an inline !important (like the benchmark's injected banner) would beat a stylesheet rule
    const saved = [...none].map(e => [e, e.style.getPropertyValue('pointer-events'), e.style.getPropertyPriority('pointer-events')]);
    for (const e of none) e.style.setProperty('pointer-events', 'auto', 'important');
    try {
      for (const [el, r] of targets) {
        const id = el.getAttribute('data-fixel-id');
        if (res[id]) continue;
        let covered = 0, by = null, n = 0;
        for (const [fx, fy] of pts) {
          const x = r.left + fx * r.width, y = r.top + fy * r.height;
          if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
          n++;
          const hit = document.elementFromPoint(x, y);
          if (hit && hit !== el && !el.contains(hit) && !hit.contains(el) && none.has(hit.closest('*')) ) {
            covered++; by = hit.closest('[data-fixel-id]')?.getAttribute('data-fixel-id') ?? by;
          }
        }
        if (covered) res[id] = { covered: covered / n, by: by === null ? null : +by, ghost: true };
      }
    } finally {
      for (const [e, v, pr] of saved) { if (v) e.style.setProperty('pointer-events', v, pr); else e.style.removeProperty('pointer-events'); }
    }
  }
  return res;
}
