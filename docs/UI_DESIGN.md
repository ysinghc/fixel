# Fixel UI: pages, workflows and the design rules behind them

The first UI was one screen that held everything at once: target picker, model toggles, a filmstrip, the stage with its overlay
layers, the findings list with four status tabs, and a fix drawer that took half the height when open. Each piece worked; together
they competed for attention and space. This redesign splits the product into pages, one task per page, connected by URLs.

## Who uses it, for what

| Person | Comes to | Needs |
|---|---|---|
| A developer | find what breaks in their app and fix it | start a scan quickly, understand one finding at a time, trust the fix |
| A labeller | give blind ground truth | one screen, three answers, no distractions |
| A reviewer / judge | see whether the numbers are honest | a headline, its caveats, then detail on demand |

## Page map

```
Home            /                                  what needs doing next, shortcuts into the three jobs
Scan            /scan                              set up and start a scan (3 numbered steps, one button)
Results         /runs                              every scan, newest first
  Scan run      /runs/:run                         live progress, then the findings list (status filters)
  Screens       /runs/:run/screens                 every rendered state as a grid of thumbnails
  Screen        /runs/:run/screens/:state          one rendered state with its overlay layers
  Finding       /runs/:run/findings/:key           one finding: the screenshot, why Fixel believes it, where in the code, Fix
  Fix           /runs/:run/fixes/:fix              the fix session: progress, result, proof, changes, agent log
Label           /label                             blind labelling, focus mode
Benchmark       /benchmark                         the measured results, one topic per tab
```

Five items in the sidebar. Every page has a URL, so the browser's back button, reload and links work, and a reload rebuilds the
page from the run's event log exactly as before.

## Workflows

1. **Find and fix** (the 80% path): Home → *Scan an app* → pick target (pre-selected) → *Start scan* → the run page shows progress,
   then findings sorted by severity → open one → read the evidence → *Fix this* → the fix page shows each phase, then the verdict →
   *Download .patch* (only when verified) → *Back to findings*, where the finding now says *Fixed*.
2. **Check a finding is real**: Finding page → screenshot with the finding outlined → width scrubber shows where it fails → evidence
   cards in plain words → *Not a defect* records a human label.
3. **Label**: Home shows "N screens left" → Label → `v` / `n` / `u` → a completion screen at the end.
4. **Read results**: Benchmark → one summary (headline or "not a headline, because …") → tabs for human labels, known answers,
   agreement with injected defects, cost.

## The 20 laws and what each changed

| # | Law | In this UI |
|---|---|---|
| 1 | **Jakob's Law**: users expect your product to work like the others they use | Left sidebar, breadcrumbs, tables with clickable rows, URLs per page, back button works |
| 2 | **Hick's Law**: more choices, slower decisions | Five sidebar items; one primary button per page; the scan form has three steps, not twelve controls |
| 3 | **Miller's Law**: about seven items in working memory | At most four summary tiles, four status filters, five checks; long lists are sorted and grouped |
| 4 | **Fitts's Law**: big, near targets are faster | Whole rows are links; primary buttons are large and sit where the eye already is (top right of the task) |
| 5 | **Tesler's Law**: complexity moves, it does not vanish; the system should carry it | The width/theme matrix comes from the target's config and is shown, not asked; the demo target is pre-selected; models default on when a key exists |
| 6 | **Occam's Razor**: remove what is not needed | The model pills and cost meter left the global bar and appear only on the run page, where they mean something |
| 7 | **Pareto Principle**: most use goes to a few features | Scan → findings → fix gets the Home shortcuts and the shortest path; screens, layers and logs are one level down |
| 8 | **Cognitive Load**: every element costs attention | One task per page; overlay layers sit behind a *Layers* control; the fix's proof, changes and log are tabs, not three columns |
| 9 | **Chunking**: group information into meaningful units | Findings grouped by status; a finding's evidence in three cards (Geometry, Pixels, Spark); the fix in four phases |
| 10 | **Law of Proximity**: near things look related | The evidence sits beside the screenshot it explains; each action sits next to the thing it acts on |
| 11 | **Law of Common Region**: a shared boundary groups things | Cards for each evidence type, each summary tile, each scan step |
| 12 | **Law of Similarity**: things that look alike seem to work alike | One colour meaning everywhere: red fails or is a defect, green verified, amber needs a person, teal SAM, violet the fixer model |
| 13 | **Law of Uniform Connectedness**: connected things read as a unit | The fix stepper's line joins its phases; the width scrubber joins the widths and shades the failing range |
| 14 | **Law of Prägnanz**: people read the simplest form | Flat surfaces, few borders, one type scale, plain-language headings ("Overflows the screen", not `viewport_protrusion`) |
| 15 | **Von Restorff Effect**: the one that differs is remembered | One accent colour, used only for the primary action; the test-split and replay warnings have their own distinct style |
| 16 | **Serial Position Effect**: first and last are remembered | Home first and Benchmark last in the sidebar; the most severe finding first; the verdict at the top of the fix page |
| 17 | **Doherty Threshold**: respond within 400 ms | Labels and navigation are instant (optimistic); skeletons while screenshots load; live progress bars and counts during scans and fixes |
| 18 | **Goal-Gradient Effect**: effort rises near the goal | Progress bars for the scan, the fix phases and labelling ("153 of 200") |
| 19 | **Zeigarnik Effect**: unfinished tasks are remembered | Home lists what is unfinished: screens left to label, confirmed findings not yet fixed, a scan still running |
| 20 | **Peak-End Rule**: people judge by the peak and the end | A clear verified moment with the patch download; a completion screen when labelling is done; a failed fix says plainly why |

Two more were applied in passing: **Postel's Law** (deep links with any finding key work, unknown runs get a helpful page, mouse and
keyboard both work) and the **Paradox of the Active User** (help sits next to the thing it explains, in one sentence, not in a manual).

## What did not change

Behaviour and honesty rules stay as they were: the screen is a function of the event log, a fix is shown as fixed and exportable only
when the model-free verifier passed it, labelling is blind, a benchmark headline needs the test split plus human labels, injected
defects are labelled as injected, and replay mode is marked on every page.
