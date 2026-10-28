// In-page elementFromPoint sampler: asks the browser what is on top at five points inside each
// interactive element. Run after snapshot.js, which assigns the data-fixel-id attributes.
() => {
  const INTERACTIVE = 'a[href],button,input,select,textarea,summary,[role=button],[role=link]';
  const pts = [[.5,.5],[.2,.2],[.8,.2],[.2,.8],[.8,.8]];
  const res = {};
  for (const el of document.querySelectorAll('[data-fixel-id]')) {
    if (!el.matches(INTERACTIVE)) continue;
    const r = el.getBoundingClientRect();
    if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) continue;
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
    if (covered) res[el.getAttribute('data-fixel-id')] = { covered: covered / n, by: by === null ? null : +by };
  }
  return res;
}
