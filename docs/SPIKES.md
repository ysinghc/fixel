# Spike results and resolved open questions

Run on 2026-10-29 against the live Meta Model API. Scripts are in `scripts/spikes/`; model calls are cached under
`.fixel/cache`, so reruns are free. Guide section 13 asked for a written go / adapt / drop decision per spike.

## Decisions

| Spike | Decision | Evidence |
|---|---|---|
| 1. SAM on UI screenshots | **Go.** SAM stays central. | 20 buttons, box-prompted with their DOM rects: all 12 clear buttons came back at confidence 0.98 (IoU with the prompt 0.98-1.00); all 8 covered buttons at 0.42-0.61 (IoU 0.77-0.88). Perfect separation on a synthetic page (`scripts/spikes/sam_boxes.py`). Thresholds still need the dev-split labels. |
| 2. Spark structured triage | **Go.** | Strict `json_schema` output with two images works first time; `reasoning={"effort": "low"}` is accepted. 5.6-7.9 s per call; about 715 input and 800 output tokens (705 of them reasoning), far below the guide's 5,000-input guess. 4 of 5 verdicts matched expectation; the miss was a sticky-nav overlap, now decided by code (below). |
| 3. Capture determinism | **Go.** | Same state rendered twice in separate contexts: identical screenshot hashes on the fixtures (light, dark, pseudo-localized) and on four real `iiitu-acm` states from 320 to 1280 px (`tests/test_determinism.py`). |
| 4. Wonder tool loop | **Adapt.** | Function tools, `previous_response_id`, and an image sent as a user message after tool results all work, and Wonder fixed the overflow at 320/375/414 px. But it needed 4 `apply_patch` attempts: hand-written unified diffs get hunk headers wrong. 127 s and 18.6 K tokens for one trivial fix. **Adapt:** give the model a search/replace edit tool (`path`, `old`, `new`), build the unified diff in code for the linter, and apply with `git apply --recount`. Not yet implemented. |

## Findings that changed the design

- **`@vitejs/plugin-react` v6 (Vite 8) has no Babel**, so the guide's `react({ babel: { plugins } })` cannot inject `data-loc`.
  A standalone Vite plugin (`tooling/vite-plugin-data-loc.mjs`) runs Babel itself; verified on both Vite 8 development targets.
- **Scroll tiling makes a sticky nav overlap everything.** On `iiitu-acm`, 8 of 21 raw findings were the sticky header over
  content scrolled under it. Spark disagreed with itself on them (3 intentional, 2 real defect), so the decision moved to code:
  a collision or occlusion between a fixed/sticky element and in-flow content that can be scrolled apart is dismissed
  (`oracles.is_transient`). A cookie banner over the last button cannot be scrolled clear, so it stays a finding.
- **The snapshot lists off-screen elements**, so a long page reported (and triaged) the same element in tiles where it was not
  visible. Candidates are now kept only in tiles where all their elements are on screen.
- **Spark can return an out-of-range number**; the invalid answer used to be cached. It is now validated inside the call, retried,
  and never cached.
- **Masks are not decoded.** The payload is base85 text in a custom alphabet (printable ASCII 33-123 minus `" , ; < > \`) around a
  4-byte length header and an entropy-coded body (not zlib, lzma or bz2). The official `meta-sam-parser` decodes it, but its install
  was refused by the session's permission check. Everything used so far (confidence and returned bounds) is on the wire; mask
  fill/spill is the only thing waiting on the parser.

## Result on the real targets (full pipeline, models live)

| Target (split) | Raw candidates | Final findings |
|---|---|---|
| iiitu-acm, 6 states (development) | 21 | 11 confirmed (5 low-contrast footer texts, 6 small footer links), 1 needs review (Spark disagrees with axe on the "Events" link), 8 dismissed by code (sticky nav), 1 not observable |
| pastebin, 4 states (development) | 5 | 5 confirmed (4 low-contrast texts, 1 small button) |

No layout-breaking defects (protrusion, collision) were found on either app at these widths; the planted-bug fixture site
covers those. These are development-split observations, not benchmark numbers.

## Open questions from the guide, answered

| Question | Answer |
|---|---|
| SAM record fields; does a box-prompt request bill as one image? | Box `x1,y1,x2,y2` (inclusive) with `w,h`, optional `c=` confidence (needs `metadata.include_confidence="true"`); mask `data=H,W,<enc><base85>` local to its box. A request with 2 and with 10 prompted objects each reported `images_processed=1`: **one image per request**, $2.50 per 1,000. Box prompts are half-open in the Python builder (`x2 = right - 1` on the wire), as the guide had it. |
| Reasoning-effort parameter name | `reasoning={"effort": "low"}` works. |
| May a function output contain images? | Untested; images were sent as a separate user message and that works. |
| Search grounding tool type | `{"type": "web_search"}`; citations arrive as `url_citation` annotations on `output_text`; $2.50 per 1,000 queries on top of tokens. |
| Voice endpoint | `POST /v1/asr/transcribe?sessionId=...`, multipart: a `request` JSON part (`mode` `PUSH_TO_TALK` default, `model`, `audioEncoding: "WAV"`, `keywords`, `languageBias`) and an `audio` part. **WAV only**, mono 16-bit PCM at 16 or 24 kHz, so browser audio must go through `ffmpeg -ac 1 -ar 24000 -c:a pcm_s16le`. JSON response has `transcript` and `turns`. Not exercised (no audio clip here). |
| Muse Image | `POST /v1/images/generations` (OpenAI-compatible); `size` sets the aspect ratio only, `output_format` webp/png/jpeg; $0.01 per image; 150 requests per minute. Not exercised. |
| Rate limits | Spark 1.3 and Wonder: 3,000 RPM and 4 M TPM; SAM 3.1: 3,000 RPM; Muse Image and the Contributor tiers: 150 RPM; Voice: 256 concurrent streams. Per team, not per key. |
| Is Wonder enabled for this key? | Yes. |
| `@vitejs/plugin-react` accepts `babel.plugins`? | Not on v6. See above. |
| Official Rules (pre-written code, submission format) | Skipped by the project owner; the submission is the GitHub repository. |

## Measured cost versus the guide's estimates

Triage is about $0.004 per call (the guide assumed about $0.0083), so 3,000 triages are about $12 rather than $23. A Wonder
session was 18.6 K tokens (about $0.10) against the guide's 80 K input assumption. SAM is $0.0025 per request. The $150
credit has far more headroom than the plan assumed.

## Fix loop results (2026-10-30)

`fixel fix` on `targets/demo-shop` (React 19, Vite 8, Tailwind 4, three planted defects), Muse Wonder, verification over
6 widths. All three verified on the first `finish` with no new findings, no drift, build passing and the linter clean.

| Defect | Patch | Turns | Tokens |
|---|---|---|---|
| `PriceCard` fixed 480 px width | `max-w-full` on the card | 3 | 3,253 |
| `Perks` non-wrapping chip row | `flex-nowrap` -> `flex-wrap` | 3 | 8,513 |
| `CookieBanner` covers the Checkout button | `pb-32` on `<main>` in `App.jsx` (the banner is `h-32`) | 5 | 24,377 |

Roughly $0.02-0.15 per fix at Wonder's prices. The planted-bug static page took 4 turns and 11,954 tokens, 35 s end to end.

A first run of the card fix passed only on its second `finish`: the verifier reported a "new finding" that was the pre-existing
cookie-banner defect under a different key (its coverer was keyed by whichever inner element a hit-test sample landed on, and a
duplicate `collision` report became observable once the page reflowed). The model then edited unrelated code to silence it.
Fixed in the oracles (stable coverer key, no duplicate collision); the rerun passed first time.
