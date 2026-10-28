# Fixel — Implementation Plan (Visual Bug Finder and Fixer)

2026-10-28 · Yuvraj

Fixel finds visual layout bugs in a web app across a matrix of viewports, proves each one with pixels, and ships a CSS patch only after a deterministic verifier re-renders every affected state. Submission is due 2026-11-04 at 9:00 PM ET (Nov 5, 6:30 AM IST). “Fixel” is a working title; nothing here is built yet, and every API detail marked **[verify]** must be checked in the first spike.

## 1. Pitch, problem and users

**Pitch.** Point Fixel at a running web app (a dev server or a Storybook). It renders every route or story across a matrix of viewport widths, themes and text-length stress, finds layout failures, confirms each one against the actual pixels, traces it to the line of source that caused it, and proposes a minimal CSS or className patch. A patch is shown as fixed only when a deterministic verifier re-renders the whole matrix and finds the bug gone, nothing new broken, and nothing else moved.

**Problem.** Unit and end-to-end tests check the DOM and behaviour, not what a user sees. Responsive layouts multiply the states to check: every route × every width × every theme × every locale. Research on responsive web design names five common failure types: element collision, element protrusion, viewport protrusion, small-range layouts, and incorrect wrapping ([Walsh et al., ReDeCheck, ISSTA 2017](https://eprints.whiterose.ac.uk/116991/1/c49.pdf)). That line of work also showed that a failure found in the DOM is not always visible on screen, and classified visibility by manipulating element opacity ([VERVE, STVR](https://eprints.whiterose.ac.uk/165542/8/stvr.1756.pdf)). Repair has received far less attention than detection ([Zerin et al., 2025](https://arxiv.org/html/2511.00678v1)).

**Users.**

| User | Situation | What Fixel gives them |
|---|---|---|
| Front-end developer on a small team | No dedicated QA; ships responsive UI weekly | A pre-merge scan with verified patches |
| Design-system maintainer | Many components, many states in Storybook | Every story checked across widths and themes |
| QA engineer | Finds a bug on a phone and has to describe it | Speak the bug; Fixel reproduces, localizes and fixes it |
| Localization team | Translated strings often run much longer than English | Pseudo-localized stress pass before strings ship |

**Scope for the demo.** React apps (Vite dev server) styled with Tailwind or plain CSS, rendered in Chromium. Five defect families: viewport protrusion, element protrusion and clipped text, element collision, occlusion of interactive elements, and small tap targets; contrast comes from axe-core. Small-range layouts and wrapping failures are stretch goals.

**What Fixel will not do.** It never hides a symptom (no `display:none`, no new `overflow:hidden` on the failing element, no `!important`), never edits copy, and never applies a patch to the user’s branch without approval.

## 2. End-to-end flow

One scan turns a URL into confirmed findings; one fix turns a finding into a verified patch.

1. **Plan states.** Read `fixel.yaml`: the routes (or the Storybook `index.json` story list), the width matrix (320, 375, 414, 768, 1024, 1280, 1440), themes (light, dark), and text stress (none, pseudo-localized). Each combination is a *state*.
2. **Explore (optional).** A computer-use agent on Muse Spark 1.3 or Muse Wonder opens menus, modals and forms to reach interactive states, and records each as a replayable step list.
3. **Capture.** Playwright renders each state deterministically (animations frozen, fonts loaded, device scale 1), takes viewport *tiles* while scrolling, and records a DOM snapshot per tile: boxes, tight text boxes, a subset of computed styles, scroll sizes, the `data-loc` source attribute, and axe-core results.
4. **Oracles.** Pure functions over the snapshot emit *candidates*: viewport protrusion, element protrusion, clipped text, collision, occlusion, small targets, contrast.
5. **Pixel evidence.** For each candidate, SAM 3.1 is prompted with the DOM boxes of the elements involved and returns what is actually painted there. A deterministic opacity-diff check runs alongside. A candidate with no visible effect is marked *not observable* and dropped from the defect list.
6. **Triage.** Muse Spark 1.3 looks at an annotated crop plus the evidence and returns a typed verdict (real defect, intentional, not visible, unsure) with severity and a user-facing description. It can dismiss a candidate as intentional but cannot create one.
7. **Group.** The same failure across widths becomes one *finding* with a width range, keyed by source location so it survives re-renders.
8. **Localize.** The finding’s elements map to source through `data-loc` (JSX file:line:column) and, for plain CSS, Chrome DevTools Protocol matched-rule lookup.
9. **Fix.** Muse Wonder (or Spark 1.3) runs a tool-calling loop in an isolated git worktree: read files, propose a unified diff, re-render, inspect, repeat. A deterministic linter rejects symptom-hiding patches before they are applied.
10. **Verify.** Re-render the finding’s route across the full width and theme matrix. Pass only if the target finding is gone everywhere, no new finding appears, no unrelated element moved sideways or changed size, the build passes, and the linter passes.
11. **Report.** The UI shows the finding, the pixel evidence, the patch, a before/after slider, and the verification checklist. Every model call is labelled live or cached.

A spoken bug report enters at step 1: Muse Voice Transcribe turns it into text, and Spark turns the text into a targeted state list and a noun phrase SAM can segment.

## 3. Architecture

> _Diagram omitted in this export: Fixel architecture · capture, detect, repair, report._

Highlighted boxes contain a Meta model; every decision that matters (a finding’s status, whether a patch is allowed, whether it worked) sits in a plain box of ordinary code. Every model call also passes through the cached client, which is what lets the demo replay offline.

## 4. Meta tooling map

Three Meta models carry the core loop (SAM 3.1 sees, Spark 1.3 judges, Wonder repairs); the rest each do one named job, and nothing is included only to appear on the list.

| Tool (API id) | Role in Fixel | Status | Code |
|---|---|---|---|
| SAM 3.1 (`sam-3.1`) | Box prompts built from DOM rects return what is actually painted in each element’s box; concept prompts (“button”) cross-check interactive elements against the DOM | Core | `meta/sam.py`, `detect/pixels.py` |
| Muse Spark 1.3 (`muse-spark-1.3`) | Triage of each candidate from an annotated crop, with schema-checked output; turns a spoken report into target states; cheaper fixer and explorer | Core | `meta/spark.py`, `detect/triage.py` |
| Muse Wonder (`muse-wonder-1.0`) | Fix agent: multi-turn tool calling over the repo with re-render feedback. In preview, so Spark 1.3 is the automatic fallback | Core | `fix/agent.py` |
| Computer tool (Responses API) | Explorer that opens menus, modals and forms to reach interactive states; actions run by our Playwright driver | Supporting | `explore/cua.py` |
| Muse Voice Transcribe (`muse-voice-transcribe-1.0`) | Spoken bug reports from the UI’s mic button | Supporting | `meta/voice.py` |
| Search grounding | Fixer’s `check_css_support` tool returns browser-support facts with citations shown on the patch card | Supporting | `fix/tools.py` |
| Muse Image (`muse-image-1.0`) | Image assets for synthetic benchmark pages, so image-overflow and text-over-image cases look realistic | Supporting (benchmark) | `bench/corpus.py` |
| Muse Spark 1.3 Contributor (`muse-spark-1.3-contributor`) | Generates synthetic pages and runs bulk triage on public or synthetic data only; prompts and completions are used to train Meta models, so never on private code | Supporting (benchmark) | `bench/` |
| Muse Spark 1.2 (`muse-spark-1.2`) | Ablation baseline for triage and fixing | Evaluation | `bench/ablate.py` |
| Muse Glimmer (open weights) | Local private-mode triage behind an OpenAI-compatible local server; same client, different base URL | Stretch | `meta/client.py` |
| Muse Code | Used to build Fixel; stretch: expose `fixel scan` and `fixel fix` as a Muse Code workflow | Build tool / stretch | — |

API capabilities used: Responses API (all model calls), structured output (`text.format` with a JSON schema; Muse requires an object root), function tools, computer tool, prompt caching (stable instruction prefixes), and the official SAM output parser `meta-sam-parser`, whose `build_object_prompt` also writes box prompts.

Not used: Muse Spark Open (needs datacenter GPUs and adds nothing over the hosted Spark here), Meta AI Connectors and the wearables toolkit (preview or sign-up gated, and unrelated to the problem).

## 5. Repository layout and data model

One Python backend (FastAPI, asyncio, Playwright) and one React UI, with every model call behind a single cached client.

```text
fixel/
  fixel.yaml                  # target command, base URL, routes or Storybook, matrix, budgets
  backend/fixel/
    models.py                 # pydantic data model (below)
    meta/client.py            # AsyncOpenAI on api.meta.ai, cache, retries, cost meter
    meta/sam.py               # box and concept prompts, raw-lane capture, parsing
    meta/spark.py             # structured-output helper
    meta/voice.py             # transcription
    meta/image.py             # Muse Image for the synthetic corpus
    capture/browser.py        # Playwright lifecycle, determinism, tiling
    capture/snapshot.js       # in-page DOM walker
    capture/axe.py            # axe-core injection
    detect/oracles.py         # geometry oracles (pure functions)
    detect/occlusion.js       # in-page elementFromPoint sampler
    detect/pixels.py          # SAM metrics + opacity diff
    detect/triage.py          # Spark verdicts
    detect/fuse.py            # decision policy + grouping into findings
    localize/cdp_styles.py    # matched CSS rules via Chrome DevTools Protocol
    fix/worktree.py           # git worktree + dev server per fix session
    fix/agent.py              # tool-calling loop
    fix/tools.py              # read_file, search, apply_patch, rerender, check_css_support
    fix/lint.py               # symptom-hiding patch linter
    verify/matrix.py          # re-render matrix, finding diff
    verify/drift.py           # layout-drift check, line remapping
    explore/cua.py            # computer-use explorer + replayable traces
    bench/mutations.py        # defect injection operators
    bench/corpus.py           # Storybook, app routes, synthetic pages
    bench/run_bench.py        # metrics + ablations
    api/server.py             # REST + server-sent events
  tooling/babel-plugin-data-loc.cjs
  web/                        # React + Vite + Tailwind demo UI
  targets/                    # demo target apps (git submodules)
  tests/                      # pytest + HTML fixtures
```

**Data model.** Everything that crosses a module boundary is a pydantic model, so it serializes to SQLite, the cache and the event stream without glue code.

```python
# backend/fixel/models.py
from typing import Literal
from pydantic import BaseModel, Field

Rect = tuple[float, float, float, float]          # x1, y1, x2, y2 in CSS px (= image px at scale 1)

class StateSpec(BaseModel):
    route: str                                    # "/checkout" or "story:button--primary"
    width: int
    height: int = 800
    theme: Literal["light", "dark"] = "light"
    text_stress: Literal["none", "pseudo"] = "none"
    replay: list[dict] = []                       # explorer steps to reach a modal or menu
    @property
    def key(self) -> str:
        return f"{self.route}|{self.width}|{self.theme}|{self.text_stress}|{len(self.replay)}"

class Element(BaseModel):
    id: int                                       # per-snapshot id (data-fixel-id)
    parent: int | None
    tag: str
    loc: str | None                               # "src/components/Cart.tsx:42:7" from data-loc
    rect: Rect
    text_rect: Rect | None                        # tight box around own text nodes
    text: str
    interactive: bool
    replaced: bool                                # img, svg, input, canvas...
    style: dict[str, str]
    scroll: tuple[int, int, int, int]             # scrollW, clientW, scrollH, clientH

class Tile(BaseModel):
    scroll_y: int
    png_sha: str                                  # content-addressed artifact
    elements: list[Element]
    occlusion: dict[int, dict]                    # element id -> {covered: 0..1, by: id}

class Capture(BaseModel):
    state: StateSpec
    vw: int; vh: int; doc_w: int
    tiles: list[Tile]
    axe: list[dict]

DefectType = Literal["viewport_protrusion", "element_protrusion", "clipped_text",
                     "collision", "occlusion", "small_target", "contrast"]

class Candidate(BaseModel):
    type: DefectType
    state_key: str
    tile: int
    elements: list[int]                           # 1 or 2 element ids
    metrics: dict[str, float]

class PixelEvidence(BaseModel):
    sam_fill: float | None = None                 # mask area inside the DOM box / box area
    sam_spill: float | None = None                # mask area outside the box / mask area
    sam_conf: float | None = None
    opacity_diff: float | None = None             # share of overlap pixels that change when B is hidden
    observable: bool

class Triage(BaseModel):
    verdict: Literal["real_defect", "intentional", "not_visible", "unsure"]
    defect_type: DefectType
    severity: int = Field(ge=1, le=4)
    what_the_user_sees: str
    fix_hint: str
    confidence: float = Field(ge=0, le=1)

class Finding(BaseModel):
    key: str                                      # type + source locations (+ text hash fallback)
    type: DefectType
    status: Literal["confirmed", "needs_review", "dismissed", "not_observable"]
    widths: list[int]                             # where it reproduces
    candidates: list[Candidate]
    evidence: list[PixelEvidence]
    triage: Triage | None
    locs: list[str]

class Verification(BaseModel):
    target_gone: bool
    new_findings: list[str]
    drifted: list[str]
    build_ok: bool
    lint_ok: bool
    @property
    def passed(self) -> bool:
        return self.target_gone and not self.new_findings and not self.drifted and self.build_ok and self.lint_ok

class FixAttempt(BaseModel):
    finding_key: str
    model: str
    diff: str
    lint_errors: list[str]
    verification: Verification | None
    citations: list[str] = []
```

## 6. Detection modules, with code

Detection is geometry first, pixels second, model judgement last: each stage can only narrow what the previous one found, which keeps every confirmed finding explainable.

### 6.1 Meta client: one door for every model call

Every call goes through `call()`, which keys a disk cache on everything that determines the answer (model, prompt, image hashes, schema version). That gives three things at once: replayable demos, cheap re-runs of the benchmark, and an honest live/cached label on every UI event.

```python
# backend/fixel/meta/client.py
import asyncio, hashlib, json, os, random
from pathlib import Path
from openai import AsyncOpenAI, APIConnectionError, APIStatusError

MODE = os.environ.get("FIXEL_MODE", "record")          # live | record | replay
CACHE = Path(".fixel/cache")
client = AsyncOpenAI(base_url=os.environ.get("MODEL_BASE_URL", "https://api.meta.ai/v1"),
                     api_key=os.environ["MODEL_API_KEY"])   # a local Glimmer server only changes the base URL

class CacheMiss(Exception): ...
class EmptyOutput(Exception): ...                       # Spark returned nothing: retryable

def key_of(kind: str, payload: dict) -> str:
    blob = json.dumps({"kind": kind, **payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()

async def call(kind: str, payload: dict, fn, emit=None) -> dict:
    """payload holds image SHAs, never image bytes, so keys stay small and stable."""
    path = CACHE / kind / f"{key_of(kind, payload)}.json"
    if MODE != "live" and path.exists():
        out, src = json.loads(path.read_text()), "cached"
    elif MODE == "replay":
        raise CacheMiss(path.name)                       # replay never spends credits
    else:
        out, src = await retry(fn), "live"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out))
    if emit:
        await emit({"type": "model.call", "kind": kind, "source": src, "usage": out.get("usage")})
    return out

async def retry(fn, attempts: int = 4):
    for i in range(attempts):
        try:
            return await fn()
        except APIStatusError as e:
            if e.status_code < 500 and e.status_code not in (408, 409, 429):
                raise                                    # a 400 is permanent: fix the request, never resend it
        except (APIConnectionError, EmptyOutput):
            pass
        await asyncio.sleep(min(8.0, 0.5 * 2 ** i) + random.random() * 0.3)
    return await fn()
```

Two details matter. An empty SAM lane is a valid answer (zero matches), so only Spark raises `EmptyOutput`. And the cost meter reads `usage` from each live call and multiplies by a price table (Spark per token, SAM per image), so the UI can show dollars spent as the scan runs.

### 6.2 Capture: deterministic renders, tiled like a user scrolls

The capture uses viewport tiles, not one full-page screenshot, because fixed and sticky elements (cookie banners, bottom nav bars) are drawn where the user actually sees them only in viewport shots. Occlusion bugs live exactly there.

```python
# backend/fixel/capture/browser.py
FREEZE_CSS = ("*,*::before,*::after{animation:none!important;transition:none!important;"
              "caret-color:transparent!important}html{scroll-behavior:auto!important}")

async def new_context(browser):
    # scale 1 makes CSS px == screenshot px, so DOM rects can be sent to SAM unchanged
    return await browser.new_context(device_scale_factor=1, reduced_motion="reduce",
                                     locale="en-US", timezone_id="UTC")

async def capture(ctx, base_url: str, s: StateSpec, store, max_tiles: int = 6):
    page = await ctx.new_page()
    await page.set_viewport_size({"width": s.width, "height": s.height})
    await page.emulate_media(color_scheme=s.theme)
    await page.goto(base_url + route_url(s.route), wait_until="networkidle")
    await page.add_style_tag(content=FREEZE_CSS)
    await page.evaluate("() => document.fonts.ready")
    if s.text_stress == "pseudo":
        await page.evaluate(PSEUDO_LOC_JS)              # lengthen and accent every text node
    for step in s.replay:
        await replay_step(page, step)                    # selector-based replay (section 8.2)
    doc_h = await page.evaluate("() => document.documentElement.scrollHeight")
    tiles = []
    for y in range(0, min(doc_h, s.height * max_tiles), s.height):
        await page.evaluate(f"window.scrollTo(0, {y})")
        png = await page.screenshot(animations="disabled")          # viewport only
        snap = await page.evaluate(SNAPSHOT_JS)
        occ = await page.evaluate(OCCLUSION_JS)
        tiles.append(Tile(scroll_y=y, png_sha=store.put(png), elements=snap["elements"], occlusion=occ))
    axe = await run_axe(page)
    return page, Capture(state=s, vw=snap["vw"], vh=snap["vh"], doc_w=snap["doc_w"], tiles=tiles, axe=axe)
```

The page is returned open because the opacity-diff check (6.4) needs it; it closes once the state’s candidates are processed.

The in-page walker records a tight text box with a DOM `Range`, because a block element’s box includes empty space and would make collision checks noisy.

```javascript
// backend/fixel/capture/snapshot.js (evaluated per tile; rects are viewport coordinates)
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
```

Ids are stable across a state’s tiles because the DOM does not change while scrolling and the walk order is fixed.

The occlusion sampler asks the browser what is on top at five points inside each interactive element:

```javascript
// backend/fixel/detect/occlusion.js
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
```

Its blind spot is deliberate to know about: `elementFromPoint` ignores overlays with `pointer-events: none`, which still block the view. The pixel layer (6.4) is what catches those.

axe-core is injected from `node_modules` and its violations are mapped to Fixel ids inside the page:

```python
# backend/fixel/capture/axe.py
async def run_axe(page):
    await page.add_script_tag(path=str(AXE_MIN_JS))
    return await page.evaluate("""async () => {
      const r = await axe.run(document, {runOnly: {type: 'rule', values: ['color-contrast']}});
      return r.violations.flatMap(v => v.nodes.map(n => ({rule: v.id,
        fixel: document.querySelector(n.target[0])?.getAttribute('data-fixel-id') ?? null,
        summary: n.failureSummary})));
    }""")
```

### 6.3 Oracles: pure functions over a snapshot

Each oracle takes a tile and returns candidates, with no I/O, so they are unit-tested against hand-written HTML fixtures.

```python
# backend/fixel/detect/oracles.py
from collections import defaultdict
from itertools import combinations

def area(r): return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])
def inter(a, b): return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
def box(e): return e.text_rect or e.rect
def is_content(e): return e.text_rect is not None or e.replaced or e.interactive

def ancestors(e, by_id):
    p = e.parent
    while p is not None and p in by_id:
        yield p
        p = by_id[p].parent

def viewport_protrusion(cap, tile):
    if cap.doc_w <= cap.vw + 1:
        return []
    by_id = {e.id: e for e in tile.elements}
    scrollers = {e.id for e in tile.elements if e.style["overflowX"] in ("auto", "scroll")}
    over = [e for e in tile.elements if e.rect[2] > cap.vw + 1
            and not any(a in scrollers for a in ancestors(e, by_id))]   # inside a scroller is fine
    parents_of_over = {e.parent for e in over}
    # report the deepest culprits: protruding elements with no protruding child
    return [cand("viewport_protrusion", tile, [e.id], overflow_px=e.rect[2] - cap.vw)
            for e in over if e.id not in parents_of_over]

def collisions(tile, min_px: float = 24, cell: int = 64):
    by_id = {e.id: e for e in tile.elements}
    grid = defaultdict(list)                             # 64 px buckets keep this near-linear
    for e in filter(is_content, tile.elements):
        x1, y1, x2, y2 = box(e)
        for gx in range(int(x1) // cell, int(x2) // cell + 1):
            for gy in range(int(y1) // cell, int(y2) // cell + 1):
                grid[gx, gy].append(e)
    seen, out = set(), []
    for bucket in grid.values():
        for a, b in combinations(bucket, 2):
            k = (min(a.id, b.id), max(a.id, b.id))
            if k in seen:
                continue
            seen.add(k)
            if a.id in set(ancestors(b, by_id)) or b.id in set(ancestors(a, by_id)):
                continue
            ov = area(inter(box(a), box(b)))
            if ov < min_px:
                continue
            out.append(cand("collision", tile, [a.id, b.id], overlap_px=ov,
                            overlap_frac=ov / min(area(box(a)), area(box(b))),
                            stacked=float(is_stacked(a, b, by_id))))   # a hint for triage, not a filter
    return out

def clipped_text(tile):
    out = []
    for e in tile.elements:
        if not e.text:
            continue
        sw, cw, sh, ch = e.scroll
        clip_x = e.style["overflowX"] in ("hidden", "clip") and sw > cw + 1
        clip_y = e.style["overflowY"] in ("hidden", "clip") and sh > ch + 1
        if (clip_x and e.style["textOverflow"] != "ellipsis") or clip_y:   # an ellipsis is deliberate
            out.append(cand("clipped_text", tile, [e.id], hidden_x=max(0, sw - cw), hidden_y=max(0, sh - ch)))
    return out

def element_protrusion(tile, tol: float = 2):
    by_id = {e.id: e for e in tile.elements}
    out = []
    for e in filter(is_content, tile.elements):
        p = by_id.get(e.parent)
        if not p or not is_visual_container(p) or p.style["overflowX"] != "visible":
            continue
        b, pr = box(e), p.rect
        over = max(pr[0] - b[0], b[2] - pr[2], pr[1] - b[1], b[3] - pr[3])
        if over > tol:
            out.append(cand("element_protrusion", tile, [e.id, p.id], protrude_px=over))
    return out

def occlusions(tile, min_cover: float = 0.4):
    return [cand("occlusion", tile, [int(i)] + ([o["by"]] if o["by"] is not None else []), covered=o["covered"])
            for i, o in tile.occlusion.items() if o["covered"] >= min_cover]

def small_targets(tile, min_px: float = 24):
    # approximates WCAG 2.2 SC 2.5.8; inline links in running text and the spacing exception are not modelled
    by_id = {e.id: e for e in tile.elements}
    return [cand("small_target", tile, [e.id], w=e.rect[2] - e.rect[0], h=e.rect[3] - e.rect[1])
            for e in tile.elements if e.interactive
            and min(e.rect[2] - e.rect[0], e.rect[3] - e.rect[1]) < min_px
            and not (e.tag == "a" and by_id.get(e.parent) and by_id[e.parent].text)]

def is_visual_container(p):
    bg = p.style["backgroundColor"]
    border = float(p.style["borderTopWidth"].removesuffix("px") or 0)
    return bg not in ("rgba(0, 0, 0, 0)", "transparent") or border > 0
```

### 6.4 Pixel evidence: SAM 3.1 box prompts and an opacity diff

This is the most distinctive use of Meta tooling in the project. SAM 3.1 accepts box prompts: a box per object under an id you choose, up to 16 objects per request, and it returns a box and pixel mask per id. Fixel sends the DOM boxes of the elements in a candidate and asks, in effect, “what is actually painted in this box?” ([Meta SAM docs](https://dev.meta.ai/docs/sam/segmenting)).

- **High spill** (most of the mask lies outside the DOM box): the visible thing in that box is part of something bigger, such as a banner covering a button, or text painted past its container.
- **Low fill** (little of the box is masked): the DOM says an element is there, but almost nothing distinct is painted, such as white text on white or a parent at zero opacity.

These readings are hypotheses. Thresholds are tuned on the benchmark’s development split, and an ablation measures what SAM adds over geometry plus the opacity diff.

```python
# backend/fixel/meta/sam.py
import base64
import numpy as np
from meta_sam_parser import (CompletedOutcome, image_segmentation_format, build_object_prompt,
                             PromptObject, FramePrompt, PromptBox, decode_mask_to_raster,
                             SegmentationBoxRecord, SegmentationMaskRecord)
from .client import client, call

def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()

async def _raw_lane(text: str, png: bytes) -> dict:
    deltas = []
    stream = await client.responses.create(
        model="sam-3.1", stream=True,
        metadata={"include_confidence": "true"},            # metadata values are strings
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": text},
            {"type": "input_image", "image_url": data_url(png)}]}])
    async for ev in stream:
        if ev.type == "response.output_text.delta":
            deltas.append(ev.delta)
    return {"raw": "".join(deltas)}                         # cache the raw lane; parse offline

def parse(raw: str) -> dict[str, dict]:
    p = image_segmentation_format().create_parser()
    list(p.push(raw))
    result = p.finish(CompletedOutcome()).result
    out: dict[str, dict] = {}
    for rec in result.records:                              # per object: one box record, one mask record
        o = out.setdefault(rec.object_id, {})
        if isinstance(rec, SegmentationMaskRecord):
            o["mask"], o["bounds"], o["conf"] = rec.mask, rec.bounds, rec.confidence
    return out                                              # [verify] field names with dir(rec) in the spike

async def segment_boxes(png: bytes, png_sha: str, size: tuple[int, int], boxes: dict[int, tuple]):
    """boxes: element id -> DOM rect in image px. Returns element id -> (full-size bool mask, confidence)."""
    w, h = size
    objs = []
    for eid, (x1, y1, x2, y2) in list(boxes.items())[:16]:  # API limit: 16 prompted objects
        bx1, by1 = max(0, int(x1)), max(0, int(y1))
        bx2, by2 = min(w, int(x2) + 1), min(h, int(y2) + 1) # PromptBox is half-open
        if bx2 - bx1 >= 4 and by2 - by1 >= 4:
            objs.append(PromptObject(id=eid, prompts=[FramePrompt(frame=0, box=PromptBox(bx1, by1, bx2, by2))]))
    if not objs:
        return {}
    text = build_object_prompt(size=(w, h), objects=objs)
    out = await call("sam.box", {"img": png_sha, "prompt": text}, lambda: _raw_lane(text, png))
    masks = {}
    for oid, o in parse(out["raw"]).items():
        m, b = o["mask"], o["bounds"]                       # mask is local to its box
        local = np.frombuffer(decode_mask_to_raster(m), np.uint8).reshape(m.height, m.width).astype(bool)
        full = np.zeros((h, w), bool)
        full[b.top:b.top + m.height, b.left:b.left + m.width] = local
        masks[int(oid)] = (full, o["conf"])
    return masks

def box_metrics(mask: np.ndarray, r) -> dict:
    x1, y1, x2, y2 = (int(round(v)) for v in r)
    inside = int(mask[max(0, y1):y2, max(0, x1):x2].sum())
    total = int(mask.sum())
    return {"fill": inside / max(1, (x2 - x1) * (y2 - y1)), "spill": (total - inside) / max(1, total)}
```

A second SAM use is a **concept cross-check**: one concept prompt (“button”) per tile returns every painted button. A DOM-visible button with no SAM match nearby, or a SAM button with no DOM element under it, becomes a Spark-reviewed *suggestion* shown in its own lane and never counted in metrics. Concept prompts take one noun phrase per request ([Meta SAM docs](https://dev.meta.ai/docs/sam/segmenting)).

The **opacity diff** is the deterministic partner, after the visibility classification in the ReDeCheck line of work: hide element B and count how many pixels in the overlap change.

```python
# backend/fixel/detect/pixels.py
async def opacity_diff(page, scroll_y: int, a, b) -> float:
    """Share of A∩B pixels that change when B is made transparent; > 0 means B visibly covers A."""
    x1, y1, x2, y2 = (int(v) for v in inter(box(a), box(b)))
    if x2 <= x1 or y2 <= y1:
        return 0.0
    await page.evaluate(f"window.scrollTo(0, {scroll_y})")
    sel = f'[data-fixel-id="{b.id}"]'
    before = to_np(await page.screenshot(animations="disabled"))[y1:y2, x1:x2]
    prev = await page.evaluate("s => { const e = document.querySelector(s); const p = e.style.opacity;"
                               " e.style.setProperty('opacity', '0', 'important'); return p; }", sel)
    after = to_np(await page.screenshot(animations="disabled"))[y1:y2, x1:x2]
    await page.evaluate("([s, p]) => { document.querySelector(s).style.opacity = p; }", [sel, prev])
    changed = np.abs(before.astype(int) - after.astype(int)).sum(axis=2) > 24
    return float(changed.mean())
```

### 6.5 Triage: Muse Spark 1.3 with schema-checked output

Spark sees a crop with element A outlined in red and B in blue (padded, upscaled to at least 320 px on the short side), a viewport thumbnail for context, and the evidence JSON. The schema keeps only types and enums; numeric ranges are checked by pydantic afterwards, since strict-mode schema support for `minimum` and `maximum` is not confirmed.

```python
# backend/fixel/detect/triage.py
TRIAGE_SYSTEM = """You review one candidate layout defect in a web page screenshot.
The red box is element A; the blue box, if present, is element B. The evidence JSON names the
geometric check that fired, its measurements, and pixel checks. Decide whether a typical user at
this viewport would see a defect. Answer "intentional" only for a deliberate pattern: a badge on
an icon, an open dropdown over content, a sticky header over content that can be scrolled into
view. Describe only what is visible in the images. If they do not let you tell, answer "unsure"."""

TRIAGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["verdict", "defect_type", "severity", "what_the_user_sees", "fix_hint", "confidence"],
    "properties": {
        "verdict": {"type": "string", "enum": ["real_defect", "intentional", "not_visible", "unsure"]},
        "defect_type": {"type": "string", "enum": list(DEFECT_TYPES)},
        "severity": {"type": "integer"},
        "what_the_user_sees": {"type": "string"},
        "fix_hint": {"type": "string"},
        "confidence": {"type": "number"},
    },
}

async def triage(crop: bytes, thumb: bytes, evidence: dict, model: str = "muse-spark-1.3") -> Triage:
    async def go():
        r = await client.responses.create(
            model=model, instructions=TRIAGE_SYSTEM,          # constant prefix: prompt-cache friendly
            input=[{"role": "user", "content": [
                {"type": "input_text", "text": json.dumps(evidence)},
                {"type": "input_image", "image_url": data_url(crop)},
                {"type": "input_image", "image_url": data_url(thumb)}]}],
            text={"format": {"type": "json_schema", "name": "triage", "schema": TRIAGE_SCHEMA, "strict": True}},
            reasoning={"effort": "low"})                     # [verify] reasoning-effort parameter name
        if not r.output_text.strip():
            raise EmptyOutput()
        return {"json": r.output_text, "usage": r.usage.model_dump() if r.usage else None}
    key = {"model": model, "v": 3, "crop": sha(crop), "thumb": sha(thumb), "ev": evidence}
    out = await call("spark.triage", key, go)
    return Triage.model_validate_json(out["json"])        # ranges enforced here
```

### 6.6 Fusion and grouping: the decision is code, not a prompt

```python
# backend/fixel/detect/fuse.py
T = {"spill": 0.35, "diff": 0.05}            # starting values; tuned on the dev split only
ALWAYS_OBSERVABLE = {"viewport_protrusion", "clipped_text", "contrast", "small_target"}

def observable(c: Candidate, px: PixelEvidence) -> bool:
    if c.type in ALWAYS_OBSERVABLE:
        return True                          # horizontal scroll or hidden text is visible by definition
    if c.type == "collision":
        return (px.opacity_diff or 0) > T["diff"]
    return (px.sam_spill or 0) > T["spill"] or (px.opacity_diff or 0) > T["diff"]   # occlusion, protrusion

def decide(c: Candidate, px: PixelEvidence, tri: Triage | None) -> str:
    if not px.observable:
        return "not_observable"
    if tri is None:
        return "confirmed"                   # model down: geometry plus pixels still stand
    if tri.verdict == "intentional" and tri.confidence >= 0.7:
        return "dismissed"
    if tri.verdict in ("unsure", "not_visible"):
        return "needs_review"                # disagreement with the pixels goes to a human
    return "confirmed"

def finding_key(c: Candidate, by_id) -> str:
    parts = sorted(by_id[i].loc or f"{by_id[i].tag}#{text_hash(by_id[i].text)}" for i in c.elements)
    return f"{c.type}|{'|'.join(parts)}"
```

Candidates with the same key across states become one finding with a width range. Rows rendered by one `.map()` share a `data-loc`, so they merge into one finding, which matches how the fix is made: once, in that JSX line.

## 7. Repair modules, with code

The model writes the patch; deterministic code decides whether the patch is allowed to exist and whether it worked.

### 7.1 Source localization

**JSX to source.** A 20-line Babel plugin stamps every intrinsic JSX element with `data-loc="file:line:column"` in dev builds only. Custom components are skipped because they only forward the attribute if they spread their props.

```javascript
// tooling/babel-plugin-data-loc.cjs
const path = require('path');
module.exports = function dataLoc({ types: t }) {
  return {
    name: 'data-loc',
    visitor: {
      JSXOpeningElement(p, state) {
        const n = p.node.name;
        if (n.type !== 'JSXIdentifier' || !/^[a-z]/.test(n.name)) return;      // intrinsic tags only
        if (p.node.attributes.some(a => a.type === 'JSXAttribute' && a.name.name === 'data-loc')) return;
        const file = state.filename || state.file.opts.filename;
        const cwd = state.cwd || state.file.opts.cwd || process.cwd();
        const { line, column } = p.node.loc.start;
        p.node.attributes.push(t.jsxAttribute(t.jsxIdentifier('data-loc'),
          t.stringLiteral(`${path.relative(cwd, file)}:${line}:${column + 1}`)));
      },
    },
  };
};
```

```typescript
// target vite.config.ts (dev only, when FIXEL=1)
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react({ babel: { plugins: process.env.FIXEL ? [`${process.env.FIXEL_HOME}/tooling/babel-plugin-data-loc.cjs`] : [] } })],
})
```

**[verify]** that the target’s `@vitejs/plugin-react` version still accepts `babel.plugins`.

**CSS to source.** For plain CSS or CSS modules, Chrome DevTools Protocol lists the author rules that match a node. Vite dev injects stylesheets as `<style data-vite-dev-id="/abs/path.css">`, so the owner node’s attribute gives the file. Served CSS is post-processed, so Fixel finds the rule in the source file by its selector text rather than by line number.

```python
# backend/fixel/localize/cdp_styles.py
async def matched_rules(page, fixel_id: int) -> list[dict]:
    cdp = await page.context.new_cdp_session(page)
    sheets: dict[str, dict] = {}
    cdp.on("CSS.styleSheetAdded", lambda e: sheets.__setitem__(e["header"]["styleSheetId"], e["header"]))
    await cdp.send("DOM.enable")
    await cdp.send("CSS.enable")                   # replays styleSheetAdded for sheets already loaded
    root = await cdp.send("DOM.getDocument", {"depth": 0})
    node = await cdp.send("DOM.querySelector", {"nodeId": root["root"]["nodeId"],
                                                "selector": f'[data-fixel-id="{fixel_id}"]'})
    matched = await cdp.send("CSS.getMatchedStylesForNode", {"nodeId": node["nodeId"]})
    out = []
    for m in matched.get("matchedCSSRules", []):
        rule = m["rule"]
        if rule.get("origin") != "regular":          # skip user-agent styles
            continue
        hdr = sheets.get(rule.get("styleSheetId"), {})
        out.append({"selector": rule["selectorList"]["text"], "css": rule["style"].get("cssText", ""),
                    "file": await sheet_file(cdp, hdr)})
    await cdp.detach()
    return out

async def sheet_file(cdp, hdr: dict) -> str | None:
    if hdr.get("sourceURL"):
        return url_to_repo_path(hdr["sourceURL"])
    if hdr.get("ownerNode"):
        d = await cdp.send("DOM.describeNode", {"backendNodeId": hdr["ownerNode"]})
        attrs = d["node"].get("attributes", [])
        return dict(zip(attrs[::2], attrs[1::2])).get("data-vite-dev-id")
    return None
```

**The fix context** handed to the agent contains: the finding and triage text; the JSX snippet (±15 lines) at each element’s and its parent’s `data-loc`; matched CSS rules; the computed-style difference between the narrowest passing width and the failing width (often the whole diagnosis, such as a fixed `width: 480px`); and two annotated crops, failing and passing.

### 7.2 Isolated workspace per fix

```python
# backend/fixel/fix/worktree.py
class Workspace:
    @classmethod
    async def open(cls, repo: Path, finding_key: str, dev_cmd: str) -> "Workspace":
        wt = repo / ".fixel" / "wt" / slug(finding_key)
        await sh(["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), "HEAD"])
        (wt / "node_modules").symlink_to(repo / "node_modules")   # no reinstall [verify per package manager]
        port = free_port()
        proc = await spawn(dev_cmd.format(port=port), cwd=wt, env={**os.environ, "FIXEL": "1"})
        await wait_http(f"http://localhost:{port}", timeout=90)
        return cls(repo=repo, path=wt, url=f"http://localhost:{port}", proc=proc)

    async def apply(self, diff: str) -> str | None:
        await sh(["git", "checkout", "--", "."], cwd=self.path)  # every attempt starts from HEAD
        chk = await sh(["git", "apply", "--check", "-"], cwd=self.path, stdin=diff, check=False)
        if chk.code:
            return chk.stderr                        # returned to the model as the tool result
        await sh(["git", "apply", "-"], cwd=self.path, stdin=diff)
        return None

    async def close(self):
        self.proc.terminate()
        await sh(["git", "-C", str(self.repo), "worktree", "remove", "--force", str(self.path)])
```

The user’s branch is never touched; an approved patch is exported as a `.patch` file or applied by the user.

### 7.3 Fix agent: Muse Wonder with function tools

The agent runs on the Responses API with function tools and server-held state (`previous_response_id`). Wonder is in preview, so a timeout or `404` switches the session to Spark 1.3; the UI shows which model produced each patch.

```python
# backend/fixel/fix/agent.py
FIX_SYSTEM = """You repair one visual layout defect in a React codebase.
Make the smallest change to CSS or className that removes the defect at every listed width.
Never change visible text, hide or clip content, or use !important.
Prefer intrinsic layout fixes: min-width:0 on flex children, wrapping, max-width:100%,
breaking long tokens, a breakpoint, or gap instead of negative margins.
After every apply_patch, call rerender and read the result. Call finish only after a rerender
shows the target defect gone. If you cannot fix it without breaking these rules, say so in finish."""

def fn(name, desc, props, req):
    return {"type": "function", "name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req, "additionalProperties": False}}

TOOLS = [
    fn("read_file", "Read lines of a repository file",
       {"path": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, ["path", "start", "end"]),
    fn("search", "Search the repository with a regular expression",
       {"pattern": {"type": "string"}, "glob": {"type": "string"}}, ["pattern", "glob"]),
    fn("apply_patch", "Apply a unified diff against HEAD (replaces any earlier attempt)",
       {"diff": {"type": "string"}}, ["diff"]),
    fn("rerender", "Re-render the failing width and its neighbours; returns oracle results and a crop", {}, []),
    fn("check_css_support", "Look up current browser support for a CSS feature, with sources",
       {"feature": {"type": "string"}}, ["feature"]),
    fn("finish", "End the session", {"summary": {"type": "string"}}, ["summary"]),
]

async def fix(f: Finding, ws: Workspace, emit, model="muse-wonder-1.0", max_turns=24, max_patches=4):
    resp = await client.responses.create(model=model, instructions=FIX_SYSTEM, tools=TOOLS,
                                         input=[user_message(fix_context(f, ws))])
    patches = 0
    for _ in range(max_turns):
        calls = [o for o in resp.output if o.type == "function_call"]
        if not calls:
            break                                          # plain message: the model stopped
        outputs, images = [], []
        for c in calls:
            args = json.loads(c.arguments or "{}")
            await emit({"type": "fix.tool", "name": c.name, "args": redact(args)})
            if c.name == "finish":
                return await finalize(f, ws, emit, summary=args["summary"])   # full verifier (7.5)
            if c.name == "apply_patch":
                patches += 1
                errs = lint(args["diff"], ws.allowed_files)
                result = {"rejected": errs} if errs else {"git": await ws.apply(args["diff"]) or "applied"}
                await emit({"type": "fix.patch", "diff": args["diff"], "lint": errs})
            else:
                result, imgs = await dispatch(c.name, args, ws, f)       # read_file, search, rerender, ...
                images += imgs
            outputs.append({"type": "function_call_output", "call_id": c.call_id, "output": json.dumps(result)})
        if patches > max_patches:
            return await finalize(f, ws, emit, summary="patch budget reached")
        extra = [{"role": "user", "content": images}] if images else []  # crops travel as a user message
        resp = await client.responses.create(model=model, previous_response_id=resp.id, tools=TOOLS,
                                             input=outputs + extra)
    return await finalize(f, ws, emit, summary="turn budget reached")
```

Re-rendered crops are sent as a separate user message because image content inside a function output is not confirmed for this API. `rerender` checks only the failing width and its two neighbours, for speed; the full matrix runs once, in `finalize`.

`check_css_support` runs a separate Spark request with search grounding enabled and returns the answer plus its citation URLs, which the patch card shows. **[verify]** the grounding tool’s type name on the search-grounding page.

### 7.4 Patch linter: no symptom hiding

A model rewarded for “the oracle stopped firing” could learn to hide the element. The linter blocks that class of patch before it is applied, and its message goes back to the model as the tool result. It errs on the strict side: a blocked legitimate patch costs one retry, while a symptom-hiding patch that slipped through would undermine the whole tool.

```python
# backend/fixel/fix/lint.py
import re
FORBIDDEN = [
    (r"!important", "no !important"),
    (r"\bdisplay\s*:\s*none\b", "hides the element"),
    (r"\bvisibility\s*:\s*hidden\b", "hides the element"),
    (r"\bopacity\s*:\s*0(\.0+)?\s*[;}\"']", "hides the element"),
    (r"\boverflow(-[xy])?\s*:\s*(hidden|clip)\b", "clipping hides the symptom"),
    (r"(?<![\w-])(hidden|invisible|opacity-0|overflow-hidden|overflow-x-hidden|overflow-y-hidden|overflow-clip)(?![\w-])",
     "Tailwind class that hides or clips"),
    (r"\bfont-size\s*:\s*0\b", "zero font size"),
]
TEXT = re.compile(r">([^<>{}]+)<|\"([^\"]{3,})\"|'([^']{3,})'")

def lint(diff: str, allowed_files: set[str], max_changed: int = 24) -> list[str]:
    errs, files, changed, removed_txt, added_txt = [], set(), 0, set(), set()
    for line in diff.splitlines():
        if line.startswith("+++ "):
            if line.strip() == "+++ /dev/null" or not line.startswith("+++ b/"):
                errs.append("deletes or creates a file")
            files.add(line[6:])
        elif line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            changed += 1
            body = line[1:]
            words = {g.strip() for m in TEXT.finditer(body) for g in m.groups() if g and not is_class_list(g)}
            (added_txt if line[0] == "+" else removed_txt).update(words)
            if line[0] == "+":
                errs += [f"{why}: {body.strip()[:80]}" for pat, why in FORBIDDEN if re.search(pat, body)]
    if files - allowed_files:
        errs.append(f"touches files outside the localized set: {sorted(files - allowed_files)}")
    if changed > max_changed:
        errs.append(f"diff too large: {changed} changed lines")
    if removed_txt - added_txt:
        errs.append("changes visible text")
    return errs
```

`is_class_list` treats a string made only of utility-class-shaped tokens as styling, not copy, so editing a `className` is allowed.

### 7.5 Verifier: model-free by design

The verifier never calls a language model or SAM: it uses the oracles and the opacity diff only, so a pass cannot be argued into existence and re-runs give the same answer. It compares against a baseline scan of the same states, taken with the same model-free settings before the fix.

```python
# backend/fixel/verify/matrix.py
WIDTHS = [320, 375, 414, 768, 1024, 1280, 1440]

async def verify(f: Finding, ws: Workspace, baseline: dict[str, ScanResult]) -> Verification:
    states = [StateSpec(route=f.route, width=w, theme=t, replay=f.replay)
              for w in WIDTHS for t in ("light", "dark")]
    after = await scan(states, ws.url, pixels="opacity_only", triage=False)
    remap = line_remap(ws.diff())                    # the patch shifts data-loc line numbers
    before = {remap_key(k, remap) for s in states for k in baseline[s.key].observable_keys}
    now = {k for s in states for k in after[s.key].observable_keys}
    drifted = sorted({d for s in states for d in
                      layout_drift(baseline[s.key], after[s.key], remap, exclude=f.container_locs)})
    build = await ws.run(["npm", "run", "build"], timeout=240)
    return Verification(target_gone=remap_key(f.key, remap) not in now,
                        new_findings=sorted(now - before), drifted=drifted,
                        build_ok=build.ok, lint_ok=not lint(ws.diff(), ws.allowed_files))
```

A patch adds or removes lines, so every `data-loc` below a hunk moves. The remap reads hunk headers:

```python
# backend/fixel/verify/drift.py
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

def line_remap(diff: str) -> dict[str, list[tuple[int, int]]]:
    """file -> [(first old line after the hunk, net line delta)]"""
    out, cur = {}, None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]; out[cur] = []
        elif (m := HUNK.match(line)) and cur:
            o_start, o_len, n_len = int(m[1]), int(m[2] or 1), int(m[4] or 1)
            out[cur].append((o_start + o_len, n_len - o_len))
    return out

def remap_loc(loc: str, remap) -> str:
    f, ln, col = loc.rsplit(":", 2)
    shift = sum(d for start, d in remap.get(f, []) if int(ln) >= start)
    return f"{f}:{int(ln) + shift}:{col}"

def layout_drift(before, after, remap, exclude: set[str], tol: float = 2) -> set[str]:
    """Elements outside the fixed container that moved sideways or changed size. Pure vertical
    shifts are allowed: fixing an overflow legitimately pushes content below it down."""
    b = identity_index(before, remap)       # (loc, tag, text hash, nth) -> rect in document coordinates
    a = identity_index(after, None)
    moved = set()
    for k, rb in b.items():
        ra = a.get(k)
        if ra is None or k[0] in exclude:
            continue
        if (abs(ra[0] - rb[0]) > tol or abs((ra[2] - ra[0]) - (rb[2] - rb[0])) > tol
                or abs((ra[3] - ra[1]) - (rb[3] - rb[1])) > tol):
            moved.add(k[0])
    return moved
```

`container_locs` is every `data-loc` inside the nearest common container of the finding’s elements: changes there are the fix, while changes elsewhere are side effects.

## 8. Intake, exploration and the API, with code

These modules widen what Fixel can reach (spoken reports, interactive states) and stream everything to the UI.

### 8.1 Voice intake: Muse Voice Transcribe + Spark

The UI’s mic button records a short clip; the backend transcribes it with keyword biasing toward the app’s own vocabulary (route names, component names), then Spark turns the transcript into a targeted scan. The route enum is built from the app’s real route list, so the model can only pick a route that exists.

```python
# backend/fixel/meta/voice.py
async def transcribe(audio: bytes, filename: str, keywords: list[str]) -> dict:
    async def go():
        async with httpx.AsyncClient(timeout=60) as h:
            r = await h.post("https://api.meta.ai/v1/asr/transcribe",
                             headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}"},
                             data={"model": "muse-voice-transcribe-1.0"},   # [verify] form fields + keyword-bias param
                             files={"file": (filename, audio)})
            r.raise_for_status()
            return r.json()
    return await call("voice", {"audio": sha(audio), "kw": sorted(keywords)}, go)

def report_schema(routes: list[str]) -> dict:
    return {"type": "object", "additionalProperties": False,
            "required": ["route", "widths", "theme", "element_phrase", "symptom"],
            "properties": {
                "route": {"type": "string", "enum": routes},           # cannot invent a page
                "widths": {"type": "array", "items": {"type": "integer", "enum": WIDTHS}},
                "theme": {"type": "string", "enum": ["light", "dark", "any"]},
                "element_phrase": {"type": "string"},                  # a short noun phrase SAM can segment
                "symptom": {"type": "string", "enum": list(DEFECT_TYPES) + ["other"]}}}
```

The targeted scan renders only the named route at the named widths (all widths when none are named), prompts SAM with `element_phrase` as a concept to find the element the user meant, and matches it to oracle findings by box overlap. The UI then says either “reproduced: finding X at 320–414 px” or “not reproduced” with the states it checked. It never reports a reproduction it did not find. The browser records `audio/webm`; the backend converts to WAV with ffmpeg if the endpoint does not accept it **[verify accepted formats]**.

### 8.2 Computer-use explorer: reaching menus, modals and forms

Routes and stories cover the default state of each page. Menus, dialogs and validation errors only appear after interaction, and they are where many overlap and occlusion bugs live. The explorer drives Playwright with Meta’s computer tool on the Responses API: the model returns batched actions, the driver executes them and returns a screenshot ([Meta computer-use guide](https://dev.meta.ai/docs/computer-use)). The guide notes that the same loop runs on Muse Spark 1.3 at lower cost than Wonder, so Spark is the default.

Two design rules keep it useful for verification:

- **State boundaries are decided by code, not by the model.** After each batch, the driver computes a DOM signature (open `[role=dialog]`, `[aria-expanded=true]`, open `<details>`, visible element count). A new signature is a new state.
- **Every state is replayable by selector, not by pixel.** Each click is recorded as the `data-loc` and index of the element under the pointer, so the verifier can return to the same modal after a patch has moved things. Line numbers are remapped with the same hunk map as section 7.5.

```python
# backend/fixel/explore/cua.py
SELECTOR_AT_POINT_JS = """([x, y]) => {
  const el = document.elementFromPoint(x, y)?.closest('a,button,input,select,textarea,summary,label,[role],[data-loc]');
  if (!el) return null;
  const loc = el.getAttribute('data-loc');
  if (loc) return {loc, nth: [...document.querySelectorAll(`[data-loc="${loc}"]`)].indexOf(el)};
  return {role: el.getAttribute('role') || el.tagName.toLowerCase(),
          name: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 60)};
}"""

class Driver:
    def __init__(self, page, origin: str):
        self.page, self.origin, self.trace = page, origin, []

    async def screenshot(self) -> bytes:
        return await self.page.screenshot(animations="disabled")

    async def execute(self, actions) -> None:
        for a in actions:
            if a.type == "click":
                sel = await self.page.evaluate(SELECTOR_AT_POINT_JS, [a.x, a.y])
                await self.page.mouse.click(a.x, a.y, button=a.button)
                self.trace.append({"op": "click", "target": sel})
            elif a.type == "type":
                await self.page.keyboard.type(a.text)
                self.trace.append({"op": "type", "text": a.text})
            elif a.type == "keypress":
                await self.page.keyboard.press("+".join(pw_key(k) for k in a.keys))
                self.trace.append({"op": "key", "keys": a.keys})
            elif a.type == "scroll":
                await self.page.mouse.move(a.x, a.y)
                await self.page.mouse.wheel(a.scroll_x, a.scroll_y)
            elif a.type == "wait":
                await self.page.wait_for_timeout(500)
            if not same_origin(self.page.url, self.origin):   # never leave the app under test
                await self.page.go_back()
                raise OffOrigin(self.page.url)

EXPLORE_TASK = ("Open each menu, dialog, drawer, dropdown and tab visible on this page, one at a time, "
                "closing each before opening the next. In forms, type a 60-character value into text "
                "fields and submit to show validation messages. Do not navigate away from this site.")

async def explore(page, route: str, emit, model="muse-spark-1.3", max_steps=25) -> list[StateSpec]:
    drv, states, seen = Driver(page, origin_of(page.url)), [], {await dom_signature(page)}
    resp = await client.responses.create(model=model, instructions=CUA_SYSTEM, tools=[{"type": "computer"}],
        input=[{"role": "user", "content": [{"type": "input_text", "text": EXPLORE_TASK},
               {"type": "input_image", "image_url": data_url(await drv.screenshot())}]}])
    for _ in range(max_steps):
        calls = [o for o in resp.output if o.type == "computer_call"]
        if not calls:
            break
        call_ = calls[0]
        if call_.pending_safety_checks:              # never auto-acknowledge: stop and report
            await emit({"type": "explore.stopped", "reason": [c.code for c in call_.pending_safety_checks]})
            break
        await drv.execute(call_.actions)
        sig = await dom_signature(page)
        if sig not in seen:
            seen.add(sig)
            states.append(StateSpec(route=route, width=page.viewport_size["width"], replay=list(drv.trace)))
            await emit({"type": "explore.state", "route": route, "steps": len(drv.trace)})
        resp = await client.responses.create(model=model, previous_response_id=resp.id, tools=[{"type": "computer"}],
            input=[{"type": "computer_call_output", "call_id": call_.call_id, "acknowledged_safety_checks": [],
                    "output": {"type": "computer_screenshot", "image_url": data_url(await drv.screenshot())}}])
    return states
```

`CUA_SYSTEM` is the strict computer-use system prompt from Meta’s guide (batching rules, wait on loads, finish only when visibly complete). Explorer runs are recorded once and replayed from the trace afterwards; only the first exploration of a route spends credits.

### 8.3 API and live events

The UI talks to a small FastAPI app. Long work streams over server-sent events; every event is also written to SQLite with a sequence number, so a reconnecting or late-joining client replays history first and never misses or duplicates an event.

| Endpoint | Purpose |
|---|---|
| `POST /api/scans` | Start a scan from `fixel.yaml` plus overrides; returns `run_id` |
| `GET /api/runs/{id}/events?after=N` | Server-sent event stream |
| `GET /api/findings/{key}` | Finding detail, evidence, crops |
| `POST /api/findings/{key}/fix` | Start a fix session; events on the same stream |
| `POST /api/voice` | Upload a recording; returns transcript, parsed report, targeted run id |
| `GET /api/artifacts/{sha}` | Screenshots, crops, SVG mask paths |
| `GET /api/bench` | Benchmark results and ablations |

```python
# backend/fixel/api/server.py
subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

async def emit(run_id: str, ev: dict) -> None:
    ev["seq"] = db.append_event(run_id, ev)          # durable first, then fan out to every subscriber
    for q in subs[run_id]:
        q.put_nowait(ev)

@app.get("/api/runs/{run_id}/events")
async def events(run_id: str, request: Request, after: int = 0):
    q: asyncio.Queue = asyncio.Queue()
    subs[run_id].add(q)                              # subscribe before reading history: no gap
    async def gen():
        last = after
        try:
            for ev in db.events(run_id, after=after):
                last = ev["seq"]
                yield f"data: {json.dumps(ev)}\n\n"
            while not await request.is_disconnected():
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if ev["seq"] > last:                 # drop events already sent from history
                    last = ev["seq"]
                    yield f"data: {json.dumps(ev)}\n\n"
        finally:
            subs[run_id].discard(q)
    return StreamingResponse(gen(), media_type="text/event-stream")
```

| Event | Payload | Drives in the UI |
|---|---|---|
| `state.captured` | state key, tile SHAs | Filmstrip thumbnail appears |
| `candidate.found` | type, element boxes | Dashed outline on the canvas |
| `pixels.done` | SAM mask SVG paths, fill, spill, opacity diff | Mask layer fills in |
| `triage.done` | verdict, severity, description | Card gets its verdict chip |
| `finding.updated` | key, status, width range | Findings list re-sorts |
| `model.call` | kind, `live` or `cached`, usage | Model badge pulses; cost meter ticks |
| `explore.state` | route, step count | New state in the filmstrip |
| `fix.tool`, `fix.patch` | tool name, diff, lint errors | Agent timeline, diff view |
| `fix.verify` | each checklist item as it completes | Verification checklist turns green or red |

Work is bounded by semaphores: 4 browser contexts, 4 concurrent SAM calls, 4 concurrent Spark calls, 1 fix session. Triage runs only on observable candidates, which is the main cost control.

## 9. Benchmark harness: unlimited data, honest ground truth

Any rendered page becomes a test case by injecting a known defect, so data is effectively unlimited; the care goes into making sure the score measures visible defects rather than the oracles grading themselves.

### 9.1 Corpora

| Corpus | How states are produced | Scale | License note |
|---|---|---|---|
| Storybook libraries | Every story from `index.json`, rendered via `iframe.html?id=…` | Hundreds of stories per library | Choose MIT or Apache-2.0 projects |
| Open-source apps | Routes from `fixel.yaml`, plus explorer states | Tens of routes per app | Same |
| Synthetic pages | Spark 1.3 Contributor writes React + Tailwind pages from random briefs (domain × layout × components); Muse Image fills every `<img>` slot from its alt text at varied aspect ratios; pages that fail to build or log console errors are discarded | As many as the budget allows | Synthetic, so safe for the Contributor tier |

Each page × 7 widths × 2 themes × 2 text-stress settings gives 28 states, before any mutation. Pick 2 projects for the development split (thresholds tuned here) and 2 different projects plus held-out synthetic seeds for the test split (results reported here only).

### 9.2 Mutation operators

| Operator | Injection on the target element | Counts as a hit | What it tests |
|---|---|---|---|
| `nowrap_long` | `white-space:nowrap` + a 40-character unbroken token | viewport or element protrusion, clipped text | Geometry |
| `fixed_width` | `width:480px; flex-shrink:0` | viewport protrusion | Geometry |
| `clamp_height` | `height:1.25em; overflow:hidden` on multi-line text | clipped text | Geometry |
| `negative_margin` | `margin-top:-24px` | collision | Geometry + opacity diff |
| `nudge` | `position:relative; left:40px` | collision, protrusion | Geometry + opacity diff |
| `font_bump` | font size × 1.6 inside a fixed-width control | clipped text, protrusion | Geometry |
| `no_wrap_row` | `flex-wrap:nowrap` on a row of chips | viewport protrusion | Geometry |
| `img_unbounded` | `max-width:none; width:900px` on an image | viewport protrusion | Geometry |
| `low_contrast` | text colour moved toward its background | contrast | axe-core |
| `tiny_target` | 16 × 16 px on an icon button | small target | Geometry |
| `opaque_banner` | Fixed 120 px bottom banner, `z-index:50` | occlusion | Hit testing + pixels |
| `ghost_banner` | Same banner with `pointer-events:none` | occlusion | **Pixels only**: hit testing is blind here |
| `badge_overlap` (control) | Absolutely positioned badge on an icon corner | must be *dismissed* | Spark triage |
| `open_dropdown` (control) | A menu opened over content | must be *dismissed* | Spark triage |
| `invisible_overlap` (control) | Two transparent wrappers overlapping, nothing painted | must be *not observable* | Pixel layer |

```python
# backend/fixel/bench/mutations.py
@dataclass(frozen=True)
class Mutation:
    name: str
    hits: frozenset[str]                       # defect types that count as detecting it
    applies: Callable[[Element], bool]         # precondition on the target element
    css: str                                   # runtime injection (detection benchmark)
    tw: str | None = None                      # Tailwind classes for source injection (fix benchmark)
    control: str | None = None                 # "dismissed" or "not_observable" for control cases

OPS = [
    Mutation("fixed_width", frozenset({"viewport_protrusion"}),
             lambda e: e.style["display"] in ("block", "flex", "grid") and not e.replaced,
             "width:480px!important;flex-shrink:0!important", "w-[480px] shrink-0"),
    Mutation("ghost_banner", frozenset({"occlusion"}), lambda e: e.interactive,
             "", None),                          # injected as a new element, see inject_banner()
    # ... the rest of the table above
]

def sample(states: list[Capture], n: int, seed: int) -> list[tuple[str, Mutation, int]]:
    rng = random.Random(seed)                  # a seed reproduces the exact benchmark
    out = []
    while len(out) < n:
        cap = rng.choice(states); op = rng.choice(OPS)
        tile = cap.tiles[0]
        targets = [e for e in tile.elements if op.applies(e) and e.loc]
        if targets:
            out.append((cap.state.key, op, rng.choice(targets).id))
    return out

async def inject(page, op: Mutation, target_id: int) -> None:
    if op.name.endswith("banner"):
        await inject_banner(page, pointer_events="none" if op.name == "ghost_banner" else "auto")
    else:
        await page.evaluate("([id, css]) => { document.querySelector(`[data-fixel-id=\"${id}\"]`)"
                            ".style.cssText += ';' + css; }", [target_id, op.css])
```

The `!important` inside the injected CSS is the benchmark breaking the app on purpose; the linter’s ban applies only to Fixel’s own patches.

### 9.3 Ground truth without circularity

If the benchmark labelled a mutation “a defect” by running the same geometry checks Fixel uses, detection recall would be close to 100% by construction. So the headline numbers come from people and from construction, not from the oracles.

1. **Human labels (headline detection numbers).** A stratified sample of 150 mutated and 50 unmutated states, each labelled in Fixel’s labelling view as *visible defect*, *no visible defect* or *unsure*. Plan about two hours. Unmutated states measure the false-positive rate on real pages, and any real pre-existing bugs they surface are reported as found.
2. **By construction.** The banner operators and the three controls have known answers without geometry: an opaque banner over a button is visible; a `ghost_banner` is visible but invisible to hit testing; controls must be dismissed or not observable.
3. **Geometric truth (scale only).** Used for regression tests and to generate fix-benchmark cases at volume, never quoted as detection accuracy.

### 9.4 Metrics and ablations

| Metric | Definition |
|---|---|
| Detection precision and recall | Against human labels, per defect type, test split only |
| Localization accuracy | Share of true findings whose `locs` include the mutated element’s `data-loc` |
| Clean-page false-positive rate | Confirmed findings on unmutated states labelled “no visible defect” |
| Control accuracy | Share of controls correctly dismissed or marked not observable |
| Verified-fix rate | Share of source-mutated cases where a patch passes the full verifier |
| Revert-equivalence | Share of verified fixes whose rendering matches the unmutated original at every width |
| Linter blocks | Symptom-hiding patches the linter stopped, and how many would have satisfied the oracles |
| Regressions caught | Patches that removed the target but failed the matrix |
| Cost and latency | Dollars and seconds per state scanned and per fix |

Ablations, all on the same cached captures:

- **Detection stack:** geometry only → + opacity diff → + SAM → + Spark triage. This isolates what SAM and Spark add.
- **Triage model:** Spark 1.3 vs Spark 1.2 vs Spark 1.3 Contributor (synthetic and public data only).
- **Fixer model:** Muse Wonder vs Spark 1.3 vs Spark 1.2, same cases, same budgets.
- **Guardrail:** fixer with the linter vs without it, counting patches that “pass” only by hiding content.

## 10. Demo UI design

The UI’s job is to make the evidence visible: a judge should see the DOM boxes, the SAM masks, the model’s verdict and the verification grid, and never have to take a claim on trust.

### 10.1 Design principles

1. **Evidence over assertion.** Every finding card shows three chips: Geometry (the oracle and its number), Pixels (SAM spill or fill, opacity diff) and Spark (verdict and confidence). Hovering a chip highlights the matching overlay.
2. **Show what was rejected.** Status tabs list *Dismissed* and *Not observable* findings with counts, and the fix timeline keeps linter-blocked patches visible in red. Seeing the system say “no” builds more trust than a clean list.
3. **Live or cached, always labelled.** Each model event carries a green *live* or grey *cached* dot. In replay mode a banner states that model responses come from the cache.
4. **One screen, one story.** Scan, inspect and fix happen on one screen; the fix opens as a bottom drawer so the finding stays in view.
5. **Dogfood.** Fixel scans its own UI in CI, and the README says so.

### 10.2 Layout (recorded at 1440 × 900)

| Zone | Size | Contents |
|---|---|---|
| Top bar | 48 px tall | Project and route selector, Scan button, mic button, model activity pills (Voice, SAM, Spark, Wonder, Grounding) that pulse while a call is in flight, live cost meter, mode badge (LIVE or REPLAY), tabs for Scan and Benchmark |
| State rail (left) | 240 px | Width filmstrip for the route (320 to 1440) with a red count per thumbnail, theme toggle, text-stress toggle, explored states (“Cart drawer open”) |
| Stage (centre) | Remaining width | The selected tile at true aspect, an SVG overlay with four layer chips (DOM boxes, SAM masks, candidates, findings), and a width scrubber whose track is shaded red over each selected finding’s failing range |
| Findings panel (right) | 380 px | Status tabs (Confirmed, Needs review, Dismissed, Not observable) and finding cards |
| Fix drawer (bottom) | 45% of height, opens on Fix | Agent timeline, diff, and the proof pane |

**Finding card:** severity dot · type chip · Spark’s one-sentence “what the user sees” · width range (“320–414 px”) · the three evidence chips · source link (`Cart.tsx:42`) · **Fix** and **Mark wrong** buttons. Mark wrong feeds the labelling set for the benchmark.

**Fix drawer, three columns:**

- **Agent timeline.** One row per tool call with an icon and short label: `read_file Cart.tsx 30–60`, `apply_patch` (a red row when the linter blocks it, with the reason), `rerender` (target gone at 375 px), `check_css_support` (with a citation chip), `finish`. The header names the model that ran, including a fallback from Wonder to Spark.
- **Diff.** A unified diff with syntax highlighting; each attempt is a tab, so a blocked first attempt stays inspectable.
- **Proof.** A before/after slider at the failing width; a 7 × 2 verification grid (widths × themes) whose cells fill green or red as the verifier re-renders; and a five-item checklist (target gone, no new findings, no drift, build, lint). **Export .patch** activates only when all five pass.

**Voice sheet.** Hold the mic button; a waveform shows while recording; the transcript appears, then the parsed report as editable chips (route, widths, element phrase, symptom). **Run targeted scan** moves the stage to that route and width and ends in one of two banners: “Reproduced: finding #3 at 320–414 px” or “Not reproduced — checked 6 states.”

**Benchmark tab.** The metrics table, an ablation chart (detection F1 for each stack layer), and a **Roll a case** button: it draws a random seed, injects that mutation live, and runs detection and the fix in front of the judges. The seed is printed so anyone can rerun the same case, which shows the demo is not cherry-picked.

### 10.3 Component tree and state

```text
App
├─ TopBar        RouteSelect · ScanButton · MicButton · ModelActivity · CostMeter · ModeBadge · Tabs
├─ ScanView
│  ├─ StateRail      WidthFilmstrip · ThemeToggle · StressToggle · ExploredStates
│  ├─ Stage          TileImage · Overlay{DomBoxes, SamMasks, Candidates, Findings} · LayerChips · WidthScrubber
│  └─ FindingsPanel  StatusTabs · FindingCard[]
├─ FixDrawer      AgentTimeline · DiffTabs · ProofPane{BeforeAfter, VerifyGrid, Checklist}
├─ VoiceSheet
└─ BenchmarkView  MetricsTable · AblationChart · RollACase
```

Stack: React, Vite, Tailwind, Zustand for one store fed by events, `react-diff-viewer-continued` for diffs. One store reduces every event (`applyEvent`), so replaying a recorded run’s events rebuilds the exact same screen.

```typescript
// web/src/hooks/useRunEvents.ts — reconnects with ?after= so no event is lost or repeated
export function useRunEvents(runId: string | null) {
  const apply = useStore(s => s.applyEvent);
  useEffect(() => {
    if (!runId) return;
    let last = 0, stop = false, es: EventSource | null = null;
    const open = () => {
      es = new EventSource(`/api/runs/${runId}/events?after=${last}`);
      es.onmessage = m => { const ev = JSON.parse(m.data); if (ev.seq > last) { last = ev.seq; apply(ev); } };
      es.onerror = () => { es?.close(); if (!stop) setTimeout(open, 1000); };
    };
    open();
    return () => { stop = true; es?.close(); };
  }, [runId, apply]);
}
```

The overlay is an SVG whose `viewBox` equals the tile size, so DOM rects and SAM masks need no scaling maths. Masks arrive as SVG paths from `decode_mask_to_svg_path`, in mask-local coordinates, and are shifted into place with a translate.

```tsx
// web/src/components/Overlay.tsx
export function Overlay({ tile, layers, hoverKey }: OverlayProps) {
  return (
    <svg viewBox={`0 0 ${tile.w} ${tile.h}`} className="pointer-events-none absolute inset-0 h-full w-full">
      {layers.dom && tile.elements.map(e => (
        <rect key={e.id} x={e.rect[0]} y={e.rect[1]} width={e.rect[2] - e.rect[0]} height={e.rect[3] - e.rect[1]}
              className="fill-none stroke-zinc-400/40" strokeWidth={1} />))}
      {layers.sam && tile.masks.map(m => (
        <path key={m.id} d={m.d} transform={`translate(${m.left} ${m.top})`}
              className="fill-teal-400/30 stroke-teal-500" strokeWidth={1} />))}
      {layers.candidates && tile.candidates.map(c => <CandidateBox key={c.id} c={c} />)}
      {layers.findings && tile.findings.map(f => <FindingBox key={f.key} f={f} active={f.key === hoverKey} />)}
    </svg>
  );
}
```

The before/after slider stacks two images and clips the top one with `clip-path: inset(0 calc(100% - var(--x)) 0 0)` driven by a range input; both images come from the same width and theme, so they align pixel for pixel.

**States the UI must handle:** no scan yet (shows the config summary and the state count it will render); scanning (skeleton thumbnails fill in as `state.captured` arrives); a model unavailable (the card reads “Spark unavailable — geometry and pixels only”, matching the fusion rule); and a fix that fails verification (the drawer stays open on the failing checklist item, and Export stays disabled).

**Keyboard:** `j` / `k` move between findings, `f` opens Fix, `v` opens voice, `1`–`4` toggle overlay layers.

## 11. Demo UI wireframe

> _Diagram omitted in this export: Main screen wireframe · scan view with the fix drawer open._

The selected finding is visible three ways at once: the red box on the stage, the shaded SAM mask spilling past it, and the card’s three evidence chips; the drawer below keeps the blocked first attempt in view next to the verified second one. Figures in the wireframe are placeholders, not results.

## 12. Demo script (3 minutes)

The story is “tests check the DOM, users see pixels”, told through one real open-source app and one random benchmark case.

| Time | What happens on screen | Line to say |
|---|---|---|
| 0:00–0:15 | A phone-width screenshot where the checkout button sits under a cookie banner; the app’s test suite shows green | “Every test passes. The button is still unreachable on a phone.” |
| 0:15–0:50 | Press Scan. The filmstrip fills across 7 widths × 2 themes; findings stream in; toggle DOM boxes, then SAM masks | “Fixel renders every width, checks the geometry, then asks SAM 3.1 what is actually painted inside each element’s box.” |
| 0:50–1:10 | Open the injected ghost-banner finding: hit testing says the button is clear, the SAM mask spills far outside the button’s box, the opacity diff confirms | “The DOM says this button is visible. The pixels say otherwise.” |
| 1:10–1:30 | Hold the mic: “On mobile the newsletter field gets cut off.” Transcript → parsed chips → targeted scan → “Reproduced at 320–414 px” | “QA can just say what they saw.” |
| 1:30–2:20 | Press Fix. Wonder reads `Cart.tsx`; attempt 1 adds `overflow-hidden` and the linter blocks it in red; attempt 2 adds `min-w-0` and wrapping; the 7 × 2 grid turns green; before/after slider | “Hiding the symptom is not allowed. The fix ships only when every width re-renders clean, nothing else moves, and the build passes.” |
| 2:20–2:45 | Benchmark tab: Roll a case → seed shown → a random mutation is injected, detected and fixed live; the metrics table and ablation chart | “Any page is a test case, so the data is unlimited. Here is what SAM and Spark each add.” |
| 2:45–3:00 | Closing card: the three Meta models and their jobs; the measured headline numbers | “SAM sees, Spark judges, Wonder repairs, and code decides.” |

Bugs shown are either real findings in the target app or injected mutations, and the UI labels every injected one as injected. Pick the target app on Day 1 partly for whether it has real findings worth showing.

The 1:30 “attempt 1 is blocked” moment cannot be scripted into the model. If the live run does not produce a blocked attempt, show one recorded from the benchmark’s linter-ablation runs and say it is recorded. **Backup:** the whole demo runs in REPLAY mode from the cache with the same commit, and a pre-recorded video of the same build is submitted with the entry.

## 13. Build plan (Oct 28 – Nov 4)

The order protects a working scan-to-verified-fix loop first, then evidence, then the extras; the commit is frozen on Nov 4 afternoon IST, well before the 9:00 PM ET (Nov 5, 6:30 AM IST) deadline.

| Day | Build | Exit criterion |
|---|---|---|
| Oct 28 (tonight) | Repo skeleton, API key, four spikes (below); choose 2 development and 2 test target apps | Each spike has a written go / adapt / drop decision |
| Oct 29 | Data model, cached client, artifact store, capture (tiles, snapshot, occlusion, axe), all oracles with HTML-fixture tests, runtime mutation injection, `fixel scan` CLI | Geometry-only scan of one app across the full matrix; oracle tests pass |
| Oct 30 | SAM box prompts, opacity diff, Spark triage, fusion, grouping; first labelling session (50 states); tune thresholds on the development split | Findings with all three evidence chips; first precision number on labelled states |
| Oct 31 | `data-loc` plugin, CDP rule lookup, fix context, worktree, fix agent, linter | One verified fix of a `fixed_width` case on the demo app |
| Nov 1 | Model-free verifier (matrix, drift, line remap), API and event stream, source-mutation fix cases | `fixel fix` passes or fails with a full checklist; events replay from SQLite |
| Nov 2 | UI: stage and overlays, findings panel, fix drawer with proof pane, replay mode | The whole demo path works in the browser, live and in replay |
| Nov 3 | Voice intake; explorer (time-box 4 hours); synthetic corpus with Muse Image (time-box 3 hours); remaining labels to 150 mutated + 50 clean; full benchmark and ablations | Metrics table and ablation chart filled from the test split |
| Nov 4 | Freeze commit by early afternoon IST; rehearse twice from a clean start; record the video; README with honest limits; submit | Repo, video and write-up match the frozen commit |

### Spikes tonight, with kill criteria

1. **SAM on UI screenshots.** Box-prompt 20 hand-picked buttons, half clear and half covered by a banner. Inspect parsed record fields and decide whether fill and spill separate the two groups. If they do not, SAM moves to the concept cross-check and mask display only, detection rests on the opacity diff, and the write-up says so.
2. **Spark structured triage.** Two images plus evidence JSON with `text.format`; confirm the reasoning-effort parameter and response time. If schema output is unreliable, parse a JSON block and validate with pydantic.
3. **Capture determinism.** Render one page twice and diff the screenshots; any difference means a source of nondeterminism to freeze before oracles are tuned.
4. **Wonder tool loop.** A trivial `apply_patch` round trip. If Wonder is unavailable or slow, Spark 1.3 becomes the default fixer and Wonder an ablation.

### Cut order if behind

Cut first to last: synthetic corpus (use open-source apps only) → explorer → voice intake → grounding chip. Never cut: the model-free verifier, the linter, the human-labelled benchmark, and replay mode, because the demo’s credibility rests on them. Glimmer stays out unless everything else is done.

## 14. Testing, cost and rate limits

The estimated benchmark spend fits inside the $150 credit with room for reruns, because every call is cached and triage runs only on observable candidates; all cost figures below are assumptions until the first spike measures real token counts.

### 14.1 Tests

| Layer | Test | Why |
|---|---|---|
| Oracles | One positive and one negative HTML fixture per oracle via `page.set_content` (for example, overflow inside an `overflow-x:auto` scroller must not fire) | The oracles are pure functions; they should never regress |
| SAM parsing | Golden tests on recorded raw lanes: parse, place masks, compute fill and spill | Catches parser-version changes such as the confidence field |
| Linter | A table of diffs that must pass (`min-w-0`, `flex-wrap`) and must be blocked (`overflow-hidden`, `md:hidden`, copy edits, new files) | The guardrail is the product’s credibility |
| Line remap | Diffs that add and remove lines above, below and inside a hunk | Wrong remaps make the verifier report false new findings |
| Verifier | A fixture app with one bug, one good patch, one symptom-hiding patch and one patch that moves a sibling; the verifier must pass only the good patch | End-to-end proof that “verified” means something |
| Determinism | Render the same state twice; screenshots must hash equal | Nondeterminism would poison every threshold |
| Replay smoke | `FIXEL_MODE=replay make demo-smoke` runs the demo path from the cache with the network off | Guarantees the live demo has a working fallback |
| Dogfood | Fixel scans its own UI in CI | The UI judges see should not have the bugs Fixel finds |

### 14.2 Cost estimate (assumptions)

Prices are from Meta’s model pages as listed in the tooling map; token counts per call are guesses to replace with measured values on Oct 28.

| Item | Assumption | Estimate |
|---|---|---|
| SAM 3.1 at $2.50 per 1,000 images | At most 4 calls per state (box batches plus one concept call per tile), 2,000 benchmark states | Up to about $20 |
| Spark 1.3 triage at $1.25 / $4.25 per million in / out | About 5,000 input and 300 output tokens per triage, 3,000 triages | About $23 standard; about $2 on the Contributor tier for public and synthetic pages |
| Wonder fixer at $4 / $20 per million | About 80,000 cumulative input and 6,000 output tokens per session, 60 cases | About $26 (less with cached input at $0.20 per million) |
| Spark 1.3 fixer ablation | Same sessions at Spark prices | About $8 |
| Computer-use explorer on Spark | 25 steps per route, 5 routes, screenshots dominate | About $4 |
| Muse Image at $0.01 per image | 300 synthetic assets | About $3 |
| Voice | A few minutes of audio | Under $0.05 |

Total is roughly $60–90, depending on tier choices. A per-run budget cap (default $10) aborts a scan when the cost meter crosses it, and the cache means a rerun of the same states costs nothing.

### 14.3 Rate limits

Rate limits for this account are not known yet: read them on the pricing and rate-limits page on Oct 28. Concurrency is set by semaphores in `fixel.yaml`; `429` and `5xx` responses retry with exponential backoff and jitter, and a `400` is never retried.

## 15. Risks and open questions

The biggest technical risk is whether SAM’s box prompts separate covered from clear elements on UI screenshots; tonight’s first spike settles it, and the design survives either answer.

| Risk | Likelihood | Mitigation |
|---|---|---|
| SAM box prompts do not discriminate on UI screenshots | Medium | Opacity diff carries detection; SAM keeps the concept cross-check and mask display; the ablation reports the result either way |
| Benchmark grades itself (geometry labels geometry) | High if ignored | Headline numbers from human labels and construction-based cases only (section 9.3) |
| Wonder unavailable or slow (preview) | Medium | Automatic fallback to Spark 1.3; the UI names the model |
| Patches pass but look worse | Medium | Revert-equivalence metric, drift check, small-diff limit, human approval before export |
| Nondeterministic rendering | Medium | Frozen animations, fonts awaited, scale 1, determinism test in CI |
| `data-loc` plugin incompatible with the target’s toolchain | Low–medium | Fingerprint keys (tag + text hash) and CSS-rule localization still work |
| Page text steers a model (prompt injection) | Low for your own apps | Triage output is schema-bound and can only dismiss; the explorer is origin-locked and never auto-acknowledges safety checks |
| Private code sent to the Contributor tier | Low | The config refuses Contributor models unless the corpus is synthetic or public |
| Credits or rate limits run out | Low–medium | Cache, triage-only-when-observable, per-run budget cap |
| Overclaiming in the submission | Medium | Report test-split numbers only; label every injected bug; mark replay mode |
| Target app license | Low | MIT or Apache-2.0 targets, attributed in the README |

### Open questions to verify on Oct 28

1. SAM: record field names in `meta-sam-parser` 0.1.0 (box and mask bounds, confidence), and whether a box-prompt request bills as one image.
2. Responses API: the reasoning-effort parameter name, and whether a function output may contain images.
3. Search grounding: the tool’s type name and where citations appear in the response.
4. Voice: form fields for `/v1/asr/transcribe`, the keyword-biasing parameter, and accepted audio formats.
5. Muse Image: endpoint and supported sizes for the synthetic corpus.
6. Account rate limits per model, and whether Wonder is enabled for this key.
7. The target’s `@vitejs/plugin-react` version accepts `babel.plugins`.
8. The Official Rules on code written before the build window and on submission format.

## 16. Sources

Read on Oct 28, 2026.

- [Segmenting with prompts — Meta Model API](https://dev.meta.ai/docs/sam/segmenting): box and point prompts, 16-object limit, request shape, confidence and mask-encoding metadata.
- [meta-sam-parser on PyPI](https://pypi.org/project/meta-sam-parser/): output grammar, `build_object_prompt`, mask decoding, stream adapter.
- [Build a computer-use agent — Meta Model API](https://dev.meta.ai/docs/computer-use): computer tool, action vocabulary, safety checks, loop on Wonder or Spark 1.3.
- [Build with Muse Spark — Meta](https://developer.meta.com/ai/resources/blog/build-with-muse-spark/): OpenAI SDK against `api.meta.ai/v1`.
- [Meta provider — promptfoo docs](https://www.promptfoo.dev/docs/providers/meta/): Responses API as the full-feature surface; structured output support.
- [ag-harness Muse provider source](https://docs.rs/crate/ag-harness/latest/source/src/provider/muse.rs): Muse structured output requires an object root schema.
- [Walsh, Kapfhammer and McMinn — ReDeCheck (ISSTA 2017)](https://eprints.whiterose.ac.uk/116991/1/c49.pdf): the five responsive layout failure types.
- [VERVE — Software Testing, Verification and Reliability](https://eprints.whiterose.ac.uk/165542/8/stvr.1756.pdf): visibility classification by manipulating opacity.
- [Zerin et al. — Repairing Responsive Layout Failures Using RAG](https://arxiv.org/html/2511.00678v1): repair has received less attention than detection.

Model prices and IDs come from the Meta tooling map compiled earlier in this project from Meta’s model pages.
