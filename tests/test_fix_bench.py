"""The fix benchmark end to end on the planted-defect demo-shop, with a scripted stand-in for the fix model (no spend).

Real: the worktree, the source injection and its commit, Chromium, the oracles, the linter, the model-free verifier, the
equivalence check and the metrics. Scripted: the model, which first tries a symptom-hiding edit, then reverts the injection.
"""
import json
from pathlib import Path

import pytest

from fixel import config as cfg
from fixel.bench import fix_bench as fb, source_mut

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "targets" / "demo-shop"

pytestmark = pytest.mark.skipif(not (DEMO / "node_modules").exists(), reason="run `make targets` first")


class Reverter:
    """Step 1 appends overflow-hidden to the injected classes (the linter must bounce it); then it removes the injection,
    trying the text shapes the injection can leave behind until one matches."""

    def __init__(self, seen):
        self.seen, self.model, self.tokens = seen, "scripted", 0
        self.step, self.i, self.tried = "hide", 0, False

    def call(self, name, **args):
        return [{"type": "function_call", "call_id": f"c{name}{self.i}{self.step}", "name": name, "arguments": json.dumps(args)}]

    async def turn(self, items):
        file, classes = self.seen["file"], self.seen["classes"]
        shapes = [f" {classes} overflow-hidden", f" {classes}", f' className="{classes}"', f' className="{classes} overflow-hidden"']
        last = json.dumps(items[-1]) if items else ""
        if self.step == "hide":
            self.step = "remove"
            return self.call("edit_file", path=file, old=classes, new=classes + " overflow-hidden")
        if self.step == "remove":
            if self.tried and "applied" in last:
                self.step = "rerender"
            else:
                self.i += 1 if self.tried and "old text not found" in last else 0
                self.tried = True
                return self.call("edit_file", path=file, old=shapes[self.i], new="")
        if self.step == "rerender":
            self.step = "finish"
            return self.call("rerender")
        return self.call("finish", summary="removed the injection")


async def test_fix_bench_injects_detects_fixes_and_measures_both_arms(tmp_path, monkeypatch):
    seen = {}
    real = source_mut.add_classes

    def spy(text, loc, classes):
        new, why = real(text, loc, classes)
        if new is not None:
            seen.update(file=loc.rsplit(":", 2)[0], classes=classes)
        return new, why
    monkeypatch.setattr(fb, "add_classes", spy)
    conf = cfg.load("targets/demo-shop.yaml")
    conf.target.path = str(DEMO)
    fc = fb.FixBenchConfig(n_cases=1, seed=5, ops=["fixed_width"], widths=[320, 768], themes=["light"],
                           routes_per_target=1, out=tmp_path / "run")
    monkeypatch.chdir(REPO)
    out = await fb.run_fix_bench(fc, say=lambda *_: None, llm_factory=lambda model, emit: Reverter(seen), confs=[conf])

    m = fb.compute(out)
    assert m["headline"] is False and m["n_cases"] == 1
    case = json.loads(next((out / "cases").glob("*.json")).read_text())
    assert case["kind"] == "injected_source" and case["detected"], case.get("other_new")
    on, off = case["arms"]["lint_on"], case["arms"]["lint_off"]
    assert on["blocked"] >= 1 and on["blocked_examples"], "the linter must bounce the overflow-hidden edit"
    assert on["status"] == "verified" and on["equivalent"]["identical"], on
    assert off["blocked"] == 0, "with the linter off the same edit is let through"
    assert off["status"] == "verified" and off["symptom_hiding"] == [], "the final diff is the revert, so nothing hides the symptom"
    assert m["arms"]["lint_on"]["verified"]["k"] == 1 and m["recorded_blocked_attempt"]
    assert "lint_off" in fb.render(m)
