"""The verifier must pass only the good patch (guide 14.1): one bug, one good patch, one symptom-hiding patch, one patch
that moves a sibling, one that creates a new defect, one that breaks the build."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fixel.config import Matrix, Target
from fixel.fix.worktree import Workspace
from fixel.scan import findings_of
from fixel.store import ArtifactStore
from fixel.verify.matrix import confirmed_keys, matrix_states, route_of, scan_baseline, verify

SITE = Path(__file__).parent / "fixtures" / "site" / "index.html"
PROMO = ".promo{width:480px;background:#fde;padding:12px}"
GOOD = ".promo{width:100%;max-width:480px;background:#fde;padding:12px}"


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    shutil.copy(SITE, r / "index.html")
    git(r, "init", "-q")
    git(r, "add", ".")
    git(r, "commit", "-qm", "base")
    return r


def target(repo):
    return Target(name="demo", path=str(repo), build_cmd=f"{sys.executable} -c pass",
                  dev_cmd=f"{sys.executable} -m http.server {{port}} --bind 127.0.0.1")


async def test_verifier_passes_only_the_good_patch(repo, tmp_path):
    store = ArtifactStore(tmp_path / "art")
    async with await Workspace.open(target(repo), "viewport_protrusion|p", root=tmp_path / "wt") as ws:
        ws.allowed_files = {"index.html"}
        states = matrix_states("/index.html", Matrix(widths=[320, 1024], themes=["light", "dark"], text_stress=["none"]))
        base = await scan_baseline(ws, states, store)
        f = next(f for f in findings_of(base) if f.type == "viewport_protrusion" and f.status == "confirmed")
        assert route_of(f) == "/index.html" and f.widths == [320]

        async def attempt(*edits, build_cmd=None):
            await ws.reset()
            ws.target = target(repo).model_copy(update={"build_cmd": build_cmd or f"{sys.executable} -c pass"})
            for old, new in edits:
                assert ws.edit("index.html", old, new)[0] is None
            return await verify(f, ws, base, store)

        # 1. the good patch: the box shrinks to fit narrow viewports and keeps its desktop width
        v = await attempt((PROMO, GOOD))
        assert v.passed, v
        assert v.target_gone and not v.new_findings and not v.drifted and v.build_ok and v.lint_ok
        assert v.grid == {s.key: True for s in states}

        # 2. an insufficient patch: still wider than a 320px phone
        v = await attempt((PROMO, ".promo{width:420px;background:#fde;padding:12px}"))
        assert not v.passed and not v.target_gone
        assert v.grid["/index.html|320|light|none|0"] is False and v.grid["/index.html|1024|light|none|0"] is True

        # 3. a symptom-hiding patch: clipping the page may silence the oracle, but the linter refuses it
        v = await attempt((PROMO, GOOD), ("main{padding:16px}", "main{padding:16px;overflow-x:hidden}"))
        assert not v.passed and not v.lint_ok
        assert any("clipping" in n for n in v.notes)

        # 4. a patch that fixes the target but moves a sibling sideways
        v = await attempt((PROMO, GOOD), (".row{display:flex;gap:8px;margin-top:16px}",
                                         ".row{display:flex;flex-direction:column;align-items:flex-start;gap:8px;margin-top:16px}"))
        assert not v.passed and v.target_gone and v.drifted and not v.new_findings

        # 5. a patch that creates a new defect: the promo is pulled up over the heading
        v = await attempt((PROMO, ".promo{width:100%;max-width:480px;background:#fde;padding:12px;margin-top:-100px;position:relative}"))
        assert not v.passed and v.target_gone and any(k.startswith("collision|") for k in v.new_findings)

        # 6. a patch that breaks the build
        v = await attempt((PROMO, GOOD), build_cmd="echo 'error: cannot resolve' >&2; exit 3")
        assert not v.passed and v.target_gone and not v.build_ok
        assert any("cannot resolve" in n for n in v.notes)


async def test_confirmed_keys_are_model_free_and_stable(repo, tmp_path):
    store = ArtifactStore(tmp_path / "art")
    async with await Workspace.open(target(repo), "k", root=tmp_path / "wt") as ws:
        states = matrix_states("/index.html", Matrix(widths=[320], themes=["light"], text_stress=["none"]))
        a = confirmed_keys(await scan_baseline(ws, states, store))
        b = confirmed_keys(await scan_baseline(ws, states, store))
        assert a == b and any(k.startswith("viewport_protrusion|") for k in a)


async def test_events_are_emitted_for_each_checklist_item(repo, tmp_path):
    store = ArtifactStore(tmp_path / "art")
    events = []

    async def emit(ev):
        events.append(ev)

    async with await Workspace.open(target(repo), "k", root=tmp_path / "wt") as ws:
        ws.allowed_files = {"index.html"}
        states = matrix_states("/index.html", Matrix(widths=[320], themes=["light"], text_stress=["none"]))
        base = await scan_baseline(ws, states, store)
        f = next(f for f in findings_of(base) if f.type == "viewport_protrusion")
        ws.edit("index.html", PROMO, GOOD)
        await verify(f, ws, base, store, emit=emit)
    items = [e for e in events if e["type"] == "fix.verify"]
    assert [e["item"] for e in items] == ["lint", "target_gone", "no_new_findings", "no_drift", "build"] and all(e["ok"] for e in items)
    cells = [e for e in events if e["type"] == "fix.verify.state"]
    assert [e["state_key"] for e in cells] == ["/index.html|320|light|none|0"] and cells[0]["ok"]        # one cell per re-rendered state


def test_matrix_defaults_cover_the_guides_grid():
    assert len(matrix_states("/x")) == 7 * 2 * 2 and {s.width for s in matrix_states("/x")} == {320, 375, 414, 768, 1024, 1280, 1440}
