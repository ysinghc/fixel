# Benchmark protocol

What it measures, how to run it, and what may be claimed from it. The plan is `IMPLEMENTATION_GUIDE.md` section 9; this
file records what is built and the rules for reporting.

## The idea

Any rendered page becomes a test case by injecting one known defect into one element. The care goes into the ground
truth: if Fixel's own geometry checks labelled the defects, recall would be near 100% by construction. So the headline
numbers come from **people** (blind human labels) and from **construction** (cases whose answer needs no geometry).

## Built

| Piece | Where |
|---|---|
| 15 operators: 12 defects, 3 controls (guide 9.2) | `backend/fixel/bench/mutations.py`, in-page injection in `inject.js` |
| Corpus: app routes of the target repos, dev and test split | `bench/corpus.py` |
| Runner: four cumulative detection levels per case, cases saved to disk | `bench/run_bench.py` |
| Metrics, Wilson 95% intervals, report, export | `bench/metrics.py` |
| Blind labelling queue, stratified by operator | `bench/labelling.py`, `GET/PUT /api/bench/...` |
| UI: Label tab (keyboard `v` `n` `u`) and Benchmark tab | `web/src/components/{LabelView,BenchmarkView}.tsx` |

## Not built yet

- The **fix benchmark** (source-level mutations, verified-fix rate, revert-equivalence, linter blocks, regressions caught).
- Triage-model and fixer-model ablations (Spark 1.2 / 1.3 Contributor, Wonder vs Spark).
- Storybook and synthetic-page corpora.
- Per-defect-type recall against human labels (labels say whether a screen has a visible defect, not which kind).

## Running it

```bash
fixel bench run --split dev --mutated 60 --clean 20          # tune here; --models none|sam|all (default all; needs the key or replay)
fixel bench report <run> --labels                            # print the report, with human-label metrics if there are labels
make serve                                                   # then label in the Label tab, read results in the Benchmark tab
fixel bench export <run>                                     # copy metrics, labels and a per-case CSV to docs/bench/<run>/ to commit
```

Runs live under `.fixel/bench/<run>/` (gitignored): `meta.json`, `cases/*.json`, `label_queue.json`, `labels.json`.
A run is reproducible from its seed. Every model call is cached, so rerunning costs nothing and `FIXEL_MODE=replay` spends nothing.

## Detection levels (the ablation)

Every case is analysed at four cumulative levels on the *same* captured page, so differences are the layers' alone:

1. **geometry**: oracle candidates, all treated as observable.
2. **+ opacity diff**: a candidate must be observable in pixels (model-free).
3. **+ SAM 3.1**: SAM's confidence on the element boxes joins the evidence.
4. **+ Spark 1.3 triage**: Spark may dismiss or send to review, never create.

A level whose model could not be called is stored as `null` and left out of that level's numbers; it is never copied from the level below.

## Ground truth, in order of trust

1. **Human labels** (headline). Each queued screen is shown blind (route, width, theme, screenshots; no operator, no kind, no
   Fixel output) and labelled *visible defect*, *no visible defect* or *unsure*. Guide default: 150 injected + 50 unmodified
   screens (about two hours). *Unsure* is excluded and counted. Reported per level: precision and recall per screen (a screen
   is flagged when Fixel confirms at least one finding), and the false-positive rate on unmodified screens.
2. **By construction.** An opaque banner over a button is visible; a controls' answers are known: a badge on a button and an
   open menu must be dismissed, invisible overlapping text must be not observable.
3. **Agreement with the injected defect** (geometric truth). A regression signal for tuning; **never quoted as accuracy**.
   Reported as "type-matched" (a new confirmed finding of a type the operator lists) and "involves the target" (any new
   confirmed finding naming the element), each with how often the finding's source location named the changed element.

A finding counts as *new* only if it was absent from the unmodified state at that level: pre-existing defects are not credited to a mutation.

## Reporting rules

- **Headline = test split + human labels.** A development run is never a headline, even with labels. The Benchmark tab and the
  report say so in words.
- **Tune on the development split only** (`iiitu-acm`, `pastebin`). The test split (`aavesh`, `e-broker`) is run for reporting.
  Change detection code after seeing test results and the test numbers are no longer clean: say so, or use a new seed and fresh labels.
- Every non-clean case is labelled **injected**. Nothing here is a bug found in the wild unless a clean screen's finding is
  confirmed by a human, and that is reported separately.
- **Replay mode** is marked on the run and in the UI.
- Intervals are 95% Wilson. With a few hundred cases they are wide; a small difference between levels is not a result.
- A run records the commit and whether `backend/` or `tooling/` had uncommitted changes.

## Known gaps the benchmark has found (development split)

These came from the first dev runs and are reported, not hidden:

- **Ghost banner** (`pointer-events: none` banner painted over a button): not detected. Occlusion starts from hit testing and SAM
  only confirms, so hit testing being blind means no candidate. Pixels-only discovery is not built.
- **Text overflowing its own box** without clipping (a `font_bump` on a button) is not a defect type any oracle reports.
- **Root-clipped overflow** (`overflow-x: hidden` on the body) is checked only for text and controls that start on screen and
  run off it; decorative blobs, carousels and closed drawers are excluded on purpose, so some real cut-off content is missed.

Fixed because the benchmark exposed them (each has a regression fixture): a collision between visible and invisible text was
"observable"; a fixed bar wider than the screen was never checked; the dropdown control overflowed the viewport by itself; the
low-contrast injector picked a wrong backdrop on gradients.
