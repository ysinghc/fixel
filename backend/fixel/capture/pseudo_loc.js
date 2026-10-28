// Pseudo-localization stress: accent and double every vowel in each text node (about +35% length),
// keeping word boundaries so wrapping behaves like a real translation. Skips script/style/noscript.
() => {
  const MAP = {a:'áá', e:'éé', i:'íí', o:'óó', u:'úú', A:'ÁÁ', E:'ÉÉ', I:'ÍÍ', O:'ÓÓ', U:'ÚÚ'};
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA']);
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (n.textContent.trim() && !SKIP.has(n.parentElement?.tagName)) nodes.push(n);
  }
  for (const n of nodes) n.textContent = n.textContent.replace(/[aeiouAEIOU]/g, c => MAP[c]);
}
