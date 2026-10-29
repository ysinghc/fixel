"""Spike 1 (guide section 13): do SAM box prompts separate covered from clear buttons on UI screenshots?

20 buttons (10 clear, 10 under an opaque banner) are box-prompted with their DOM rects. Without a mask decoder
this reads what is on the wire: the returned bounds and confidence. Prints a table and group summaries.
"""
import asyncio
import base64
import re
import statistics as st

from fixel.capture.browser import FREEZE_CSS, Browsers, capture_page, new_context
from fixel.meta import client as meta
from fixel.models import StateSpec
from fixel.store import ArtifactStore

LABELS = ["Buy", "Add to cart", "Checkout", "Sign in", "Subscribe", "Download", "Learn more", "Contact us",
          "Pay now", "Continue", "Save", "Cancel", "Next", "Back", "Apply", "Share", "Follow", "Send", "Open", "Help"]
COLORS = ["#06c", "#e33", "#2a7", "#f90", "#63c"]
RECT = re.compile(r"(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=\d+;h=\d+(?:;c=([\d.]+))?\|>")


def page():
    btns = []
    for i, label in enumerate(LABELS):
        row, col = divmod(i, 4)
        covered = row >= 2 and row < 4 or i in (16, 17)
        y = 20 + row * 90
        btns.append(f'<button style="position:absolute;left:{20 + col * 160}px;top:{y}px;width:140px;height:44px;'
                    f'background:{COLORS[i % 5]};color:#fff;border:0;border-radius:6px;font:15px sans-serif">{label}</button>')
    return ("<style>body{margin:0;background:#fff}</style>" + "".join(btns) +
            '<div style="position:fixed;left:0;right:0;top:170px;height:200px;background:#2b2b2b;z-index:9"></div>'
            '<div style="position:fixed;left:0;right:0;top:440px;height:60px;background:#2b2b2b;z-index:9"></div>')


async def main():
    store = ArtifactStore()
    async with Browsers() as browser:
        pg = await (await new_context(browser)).new_page()
        await pg.set_viewport_size({"width": 680, "height": 520})
        await pg.set_content(page())
        await pg.add_style_tag(content=FREEZE_CSS)
        cap = await capture_page(pg, StateSpec(route="/t", width=680, height=520), store)
    tile = cap.tiles[0]
    png = store.get(tile.png_sha)
    banners = [e.rect for e in tile.elements if e.style["position"] == "fixed"]
    btns = [e for e in tile.elements if e.tag == "button"]
    rows = []
    for k in range(0, len(btns), 10):                        # well under the 16-object limit
        group = btns[k:k + 10]
        text = "<0f>" + ",".join(
            f"{e.id}<|box;x1={int(e.rect[0])};y1={int(e.rect[1])};x2={int(e.rect[2]) - 1};y2={int(e.rect[3]) - 1};w=680;h=520|>" for e in group)
        stream = await meta.get_client().responses.create(
            model="sam-3.1", stream=True, metadata={"include_confidence": "true", "mask_encoding": "one_bit"},
            input=[{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": text},
                {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode()}]}])
        raw = "".join([ev.delta async for ev in stream if ev.type == "response.output_text.delta"])
        got = {int(m[1]): m for m in RECT.finditer(raw)}
        for e in group:
            x1, y1, x2, y2 = e.rect
            covered = any(b[1] < (y1 + y2) / 2 < b[3] for b in banners)
            m = got.get(e.id)
            if not m:
                rows.append((e.text, covered, None)); continue
            bx1, by1, bx2, by2 = (int(m[i]) for i in range(2, 6))
            ix = max(0, min(x2, bx2 + 1) - max(x1, bx1)); iy = max(0, min(y2, by2 + 1) - max(y1, by1))
            inter = ix * iy
            barea = (bx2 + 1 - bx1) * (by2 + 1 - by1)
            area = (x2 - x1) * (y2 - y1)
            rows.append((e.text, covered, dict(conf=float(m[6] or 0), spill=1 - inter / barea, iou=inter / (barea + area - inter),
                                               w=bx2 + 1 - bx1, h=by2 + 1 - by1)))
    print(f"{'button':<12}{'covered':<9}{'conf':>6}{'spill':>7}{'iou':>6}{'bounds':>10}")
    for label, cov, r in rows:
        print(f"{label:<12}{str(cov):<9}" + ("no record" if r is None else f"{r['conf']:6.2f}{r['spill']:7.2f}{r['iou']:6.2f}{r['w']:>6}x{r['h']}"))
    for name, flag in (("clear", False), ("covered", True)):
        rs = [r for _, c, r in rows if c == flag and r]
        print(f"{name:<8} n={len(rs)} conf mean {st.mean(r['conf'] for r in rs):.2f} range {min(r['conf'] for r in rs):.2f}-{max(r['conf'] for r in rs):.2f}; "
              f"spill mean {st.mean(r['spill'] for r in rs):.2f} max {max(r['spill'] for r in rs):.2f}; iou mean {st.mean(r['iou'] for r in rs):.2f}")
    print("no-record:", [l for l, _, r in rows if r is None])


asyncio.run(main())
