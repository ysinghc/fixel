// Injects one benchmark defect (or control) into the page. Evaluated with [id, op]: id is the data-fixel-id the snapshot
// gave the target element. Returns true if the injection was applied. The !important below is the benchmark breaking the
// app on purpose; the patch linter's ban applies only to Fixel's own patches.
([id, op]) => {
  const el = document.querySelector(`[data-fixel-id="${id}"]`);
  if (!el) return false;
  const imp = (e, css) => { for (const [k, v] of Object.entries(css)) e.style.setProperty(k, v, 'important'); };
  const cs = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  const ownText = () => [...el.childNodes].find(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
  const add = (css, html, attrs = {}) => {
    const d = document.createElement('div');
    d.setAttribute('data-fixel-bench', op);
    for (const [k, v] of Object.entries(attrs)) d.setAttribute(k, v);
    d.innerHTML = html;
    imp(d, css);
    document.body.appendChild(d);
    return d;
  };
  const banner = pointerEvents => add({
    position: 'fixed', left: '0', right: '0', bottom: '0', height: '120px', 'z-index': '50', background: '#1f2937',
    color: '#fff', padding: '16px', 'box-sizing': 'border-box', font: '14px sans-serif', 'pointer-events': pointerEvents,
  }, 'We use cookies to improve your experience. Accept all &middot; Manage preferences');
  // the colour a text sits on: the nearest ancestor with a painted background, else white
  // (null when a gradient or image sits behind the text first: the backdrop colour is then unknown)
  const backdrop = () => {
    for (let e = el; e; e = e.parentElement) {
      const st = getComputedStyle(e);
      if (st.backgroundImage !== 'none') return null;
      const c = st.backgroundColor;
      if (c && c !== 'transparent' && !/rgba\(.*,\s*0\)$/.test(c)) return c;
    }
    return 'rgb(255, 255, 255)';
  };
  const sy = scrollY, sx = scrollX;

  switch (op) {
    case 'nowrap_long': {
      imp(el, { 'white-space': 'nowrap' });
      const n = ownText();
      if (!n) return false;
      n.textContent = n.textContent + ' ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmn';   // 40 characters, no break opportunity
      return true;
    }
    case 'fixed_width': imp(el, { width: '480px', 'flex-shrink': '0' }); return true;
    case 'clamp_height': imp(el, { height: '1.25em', overflow: 'hidden' }); return true;
    case 'negative_margin': imp(el, { 'margin-top': '-24px' }); return true;
    case 'nudge': imp(el, { position: 'relative', left: '40px' }); return true;
    case 'font_bump':
      imp(el, { width: `${r.width}px`, 'flex-shrink': '0', 'white-space': 'nowrap', 'font-size': `${parseFloat(cs.fontSize) * 1.6}px` });
      return true;
    case 'no_wrap_row': imp(el, { 'flex-wrap': 'nowrap' }); return true;
    case 'img_unbounded': imp(el, { 'max-width': 'none', width: '900px' }); return true;
    case 'low_contrast': {                                                // text moved 85% of the way to its backdrop colour
      const rgb = c => (c.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
      const bd = backdrop();
      if (!bd) return false;
      const [t, b] = [rgb(cs.color), rgb(bd)];
      imp(el, { color: `rgb(${t.map((v, i) => Math.round(v + (b[i] - v) * 0.85)).join(',')})` });
      return true;
    }
    case 'tiny_target':
      imp(el, { width: '16px', height: '16px', 'min-width': '0', 'min-height': '0', padding: '0', overflow: 'hidden' });
      return true;
    case 'opaque_banner': banner('auto'); return true;
    case 'ghost_banner': banner('none'); return true;                    // paints over the button but hit testing sees through it

    // controls: the pipeline must dismiss the first two and see nothing painted in the third
    case 'badge_overlap': {
      const b = add({ position: 'absolute', left: `${r.right + sx - 10}px`, top: `${r.top + sy - 8}px`, width: '18px', height: '18px',
        'border-radius': '9px', background: '#ef4444', color: '#fff', font: '11px/18px sans-serif', 'text-align': 'center',
        'z-index': '30' }, '3');
      return !!b;
    }
    case 'open_dropdown':
      add({ position: 'absolute', left: `${Math.max(8, Math.min(r.left, innerWidth - 188)) + sx}px`, top: `${r.bottom + sy + 4}px`, width: '180px', 'z-index': '40',
        background: '#fff', color: '#111', border: '1px solid #d4d4d8', 'border-radius': '8px', padding: '6px',
        'box-shadow': '0 8px 24px rgba(0,0,0,.25)', font: '14px sans-serif' },
        '<div style="padding:6px 8px">Profile</div><div style="padding:6px 8px">Settings</div><div style="padding:6px 8px">Sign out</div>');
      return true;
    case 'invisible_overlap':
      for (const dx of [0, 6]) {
        add({ position: 'absolute', left: `${r.left + sx + dx}px`, top: `${r.top + sy}px`, width: `${Math.max(r.width, 80)}px`,
          'z-index': '30', color: 'transparent', background: 'transparent', font: `${cs.fontSize} ${cs.fontFamily}`,
          'pointer-events': 'none' }, 'Hidden words that are never painted');
      }
      return true;
  }
  return false;
}
