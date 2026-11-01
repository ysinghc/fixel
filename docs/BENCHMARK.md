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
| UI: Label tab (keyboard `v` `n` `u`) and Benchmark tab | `web/src/pages/{LabelPage,BenchmarkPage}.tsx` |
| Fix benchmark: source-level injection, verified-fix rate, revert-equivalence, linter on/off, regressions caught | `bench/{source_mut,fix_bench}.py`, `fixel bench fix` |
| "Roll a case": a seed draws one injected source defect, scans it and fixes it live | `fix_bench.roll`, `POST /api/roll`, Benchmark tab > Fixing |

## Not built yet

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

## Labelling on your own machine

The labelling UI needs the run's screenshots, which live in the gitignored `.fixel/` of the machine that ran it. Pack and move them:

```bash
fixel bench bundle <run>                 # on the machine that ran it: one tar.gz, the run plus exactly its screenshots
fixel bench import <run>.bench.tar.gz    # on the labelling machine: unpacks into .fixel/
make serve                               # label in the Label tab (blind: the queue API never returns the operator, kind or Fixel output)
fixel bench export <run>                 # writes docs/bench/<run>/labels.json (plus metrics) to commit and push back
fixel bench report <run> --labels-file docs/bench/<run>/labels.json    # recompute metrics with those labels
```

A bundle has no labels; labels belong to whoever made them. Importing refuses anything outside `bench/` and `artifacts/`.

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

## The test-split run (seed 7)

Run `20261031-093745-test-s7`: 150 injected + 50 unmodified cases, all four levels, `record` mode, $2.52, 55 minutes, no case crashed.
**Only `e-broker` was run; `aavesh` (the other test target) was excluded.** Its WebGL scene pins the CPU: the first attempt that
included it finished 8 cases in 30 minutes, so it was excluded for feasibility, before any result was read. The test split is therefore one
Next.js app with five routes, which is a weaker claim about generalization than two apps, and the report and the Benchmark tab say so.
An earlier attempt also aborted on a crashing case (fixed: restore is null-safe, cases are guarded and counted). Neither aborted
attempt's results were read.

**One detection fix landed after this run, and its detection numbers must be regenerated before they are quoted.** The collision
rule introduced on the development split (both elements must paint in the overlap) had a bug that a pre-existing unit test
(`test_verify`) caught after the run: a heading covered by the *parent box* of the other text read as unpainted, so a covered heading
was "not visible". It is fixed (each element is probed with the other one's containers hidden). The fix came from a failing unit test,
not from looking at test-split results, but the run's stored detection levels were computed with the buggy rule. The screenshots and
the labelling queue do not depend on detection, so labels made on the bundle stay valid; the detection side should be rerun with the
same seed (`fixel bench run --split test --targets e-broker --mutated 150 --clean 50 --seed 7`) before computing the headline.

Apart from that fix, nothing about detection was changed after this run started, and nothing should be: this run is the test split, so changing detection
code after seeing its numbers makes them no longer clean (use a new seed and fresh labels if that happens).

## Known gaps the benchmark has found (development split)

These came from the first dev runs and are reported, not hidden:

- **Ghost banner** (`pointer-events: none` banner painted over a button): was not detected (0/6 dev, 0/10 test) because occlusion
  starts from hit testing. Now found by a second hit test that makes `pointer-events:none` elements hittable (see the disclosure below).
- **Text overflowing its own box** without clipping (a `font_bump` on a button) is not a defect type any oracle reports.
- **Root-clipped overflow** (`overflow-x: hidden` on the body) is checked only for text and controls that start on screen and
  run off it; decorative blobs, carousels and closed drawers are excluded on purpose, so some real cut-off content is missed.

Fixed because the benchmark exposed them (each has a regression fixture): a collision between visible and invisible text was
"observable"; a fixed bar wider than the screen was never checked; the dropdown control overflowed the viewport by itself; the
low-contrast injector picked a wrong backdrop on gradients.

## Ghost-banner detector: a disclosure about the test split

The ghost detector (`detect/occlusion.js`) was written **after** the test-split run reported 0/10 ghost banners, at the project
owner's request to either build it or cut it from the demo. That is a change to detection after seeing test numbers, which the rule
above says taints them. What limits the damage: it was developed and checked on the development split and on fixtures only (8/8
injected ghost banners found on dev, 0 ghost candidates on real dev pages), it is one generic rule rather than a threshold fitted to
test cases, and the human labels do not depend on it (screens are fixed by the seed, not by detection). Reporting rule: quote the test
detection numbers **both ways**, from the run made before this change (`docs/bench/20261030-194755-dev-s7` is the dev run; the
test run's stored levels predate the change) and from a rerun with the same seed after it, and say which is which. Do not quote only
the better one.

## Fix benchmark

`fixel bench fix --split dev --cases N --seed S` (reports with `fixel bench fix-report <run>`; runs live under `.fixel/fixbench/`).

1. A case is one defect injected into the **source** of a corpus app: Tailwind classes (with the important marker, so the defect wins)
   are added to the className of the JSX element a `data-loc` names (`bench/source_mut.py`, 7 operators that a class list can express:
   `fixed_width`, `no_wrap_row`, `img_unbounded`, `negative_margin`, `nudge`, `tiny_target`, `clamp_height`). The change is committed in
   an isolated worktree, so the fix agent's diff is only its own repair. Apps without Tailwind are skipped and listed.
2. The case counts only if the **model-free scan finds the injected defect** (a new confirmed finding of the operator's type on the
   mutated element). Cases the scan misses are reported (`detected`), never given to the fixer, and are not part of the fix rate.
   Draws where the operator cannot edit any element (a dynamic `className`, no applicable element) are counted separately.
3. Each detected case is fixed once per arm: **linter on** (the product) and **linter off** (the same agent, linter switched off in
   both the edit tool and the verifier). With the linter off the final diff is linted afterwards, only to classify it: a verified
   patch the linter would have blocked is a patch that passes the oracles by hiding the symptom.
4. Reported per arm, with Wilson 95% intervals: verified-fix rate (the model-free verifier passed), revert-equivalence (the fixed
   pages render pixel-identical to the unmutated original at every state of the matrix: strict, since a legitimate fix that is not
   a literal revert counts as not equivalent), linter blocks, patches that removed the target but failed the matrix, failures, cost
   and latency. The verification matrix is smaller than the product's (widths 320/375/768/1280, light and dark, normal text).
5. The second arm replays the first arm's cached model turns until the two transcripts diverge (a blocked edit changes the
   transcript), so it costs nothing extra and differs only where the linter intervened. Its cost is therefore not reported.
6. Every case is labelled injected. A dev-split run is a tuning signal and never a headline; a test-split fix benchmark would need
   the test targets to use Tailwind (e-broker uses Tailwind 3: the important marker goes before the utility, handled; aavesh has none).

## Roll a case

Benchmark tab > Fixing > Roll a case, or `POST /api/roll {seed}`. A seed draws the target, operator, route, state and element, so the
same seed always gives the same case and anyone can rerun it. Draws whose injected defect the scan cannot see are redrawn, and the
UI says how many were skipped. It runs the linter-on arm only and shows the live timeline, the diff and the verifier's verdict.
In replay mode only seeds that were recorded work.
