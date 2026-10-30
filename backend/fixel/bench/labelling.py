"""The human-labelling queue: a stratified, shuffled sample of a run's cases, shown to the labeller blind.

The labeller sees only the rendered state (route, width, theme, text setting, screenshots). Not whether the case is an
injected defect, a control or a clean page, and not what Fixel found, so the label cannot be influenced by either
(guide section 9.3). Guide default: 150 mutated + 50 unmutated states, about two hours.
"""
import json
import random
from collections import defaultdict
from pathlib import Path

from . import metrics

QUESTION = ("Is there a visible layout defect in this screen? Content cut off or running off the screen, text overflowing or "
            "overlapping other content, a control covered by something, unreadable low contrast. "
            "Not a defect: design taste, or something clearly intentional such as an open menu or a badge.")


def queue_path(run: Path) -> Path:
    return Path(run) / "label_queue.json"


def build_queue(run: Path, n_mutated: int = 150, n_clean: int = 50, seed: int = 11) -> list[str]:
    """Pick the cases to label: unmutated states plus mutated ones spread evenly over the operators (controls included)."""
    cases = metrics.load_cases(run)
    rng = random.Random(seed)
    clean = sorted(c["id"] for c in cases if c["kind"] == "clean")
    by_op: dict[str, list[str]] = defaultdict(list)
    for c in cases:
        if c["kind"] == "mutated":
            by_op[c["op"]].append(c["id"])
    chosen = rng.sample(clean, min(n_clean, len(clean)))
    pools = {op: rng.sample(sorted(ids), len(ids)) for op, ids in sorted(by_op.items())}
    taken = 0
    while taken < n_mutated and any(pools.values()):
        for op in list(pools):
            if pools[op] and taken < n_mutated:
                chosen.append(pools[op].pop())
                taken += 1
    rng.shuffle(chosen)
    queue_path(run).write_text(json.dumps({"seed": seed, "n_mutated": n_mutated, "n_clean": n_clean, "ids": chosen}, indent=1))
    return chosen


def queue(run: Path, n_mutated: int = 150, n_clean: int = 50) -> list[str]:
    p = queue_path(run)
    return json.loads(p.read_text())["ids"] if p.exists() else build_queue(run, n_mutated, n_clean)


def blind_items(run: Path) -> list[dict]:
    """What the labelling view may show for each queued case, with the label given so far."""
    ids = queue(run)
    by_id = {c["id"]: c for c in metrics.load_cases(run)}
    labels = metrics.load_labels(run)
    out = []
    for n, cid in enumerate(ids):
        c = by_id[cid]
        s = c["state"]
        out.append({"id": cid, "n": n + 1, "route": s["route"], "width": s["width"], "height": s["height"], "theme": s["theme"],
                    "text_stress": s["text_stress"], "target": c["target"], "tiles": c["tiles"], "label": labels.get(cid)})
    return out


def list_runs(root: Path) -> list[dict]:
    """Benchmark runs on disk, newest first."""
    out = []
    for d in sorted(Path(root).glob("*/meta.json"), reverse=True):
        m = json.loads(d.read_text())
        run = d.parent
        q = queue_path(run)
        n_queue = len(json.loads(q.read_text())["ids"]) if q.exists() else None
        out.append({"run": run.name, "split": m.get("split"), "mode": m.get("mode"), "n_cases": m.get("n_cases"),
                    "levels": m.get("levels"), "usd": m.get("usd"), "created": m.get("created"),
                    "labelled": len(metrics.load_labels(run)), "queue": n_queue})
    return out
