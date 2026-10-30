"""The fix loop with a scripted model: code, not the model, decides what stays in the tree and what counts as fixed."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from openai import APIStatusError

from fixel.config import Matrix, Target
from fixel.fix.agent import FixLLM, fix_finding
from fixel.fix.worktree import Workspace
from fixel.meta import client
from fixel.scan import findings_of
from fixel.store import ArtifactStore
from fixel.verify.matrix import matrix_states, scan_baseline

SITE = Path(__file__).parent / "fixtures" / "site" / "index.html"
PROMO = ".promo{width:480px;background:#fde;padding:12px}"
GOOD = ".promo{width:100%;max-width:480px;background:#fde;padding:12px}"


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


class Scripted:
    """Stands in for FixLLM: each step is a list of (tool, args) calls, or a plain string for a final message."""

    def __init__(self, *steps):
        self.steps, self.model, self.tokens, self.transcripts, self.seen = list(steps), "scripted", 0, [], []

    async def turn(self, items):
        self.transcripts.append(len(items))
        self.seen.append(json.dumps(items))
        step = self.steps.pop(0)
        if isinstance(step, str):
            return [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": step}]}]
        return [{"type": "function_call", "call_id": f"c{len(self.transcripts)}_{i}", "name": n, "arguments": json.dumps(a)}
                for i, (n, a) in enumerate(step)]


def edit(old, new):
    return ("edit_file", {"path": "index.html", "old": old, "new": new})


@pytest.fixture
async def session(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    shutil.copy(SITE, r / "index.html")
    git(r, "init", "-q"); git(r, "add", "."); git(r, "commit", "-qm", "base")
    t = Target(name="demo", path=str(r), build_cmd=f"{sys.executable} -c pass",
               dev_cmd=f"{sys.executable} -m http.server {{port}} --bind 127.0.0.1")
    store = ArtifactStore(tmp_path / "art")
    async with await Workspace.open(t, "k", root=tmp_path / "wt") as ws:
        states = matrix_states("/index.html", Matrix(widths=[320, 1024], themes=["light"], text_stress=["none"]))
        base = await scan_baseline(ws, states, store)
        f = next(f for f in findings_of(base) if f.type == "viewport_protrusion" and f.status == "confirmed")
        events = []

        async def emit(ev):
            events.append(ev)

        yield f, ws, base, store, events, emit, r


async def test_happy_path_blocked_edit_is_reverted_then_a_good_edit_is_verified(session):
    f, ws, base, store, events, emit, repo = session
    llm = Scripted(
        [("read_file", {"path": "index.html", "start": 1, "end": 20})],
        [edit(PROMO, ".promo{width:480px;background:#fde;padding:12px;overflow:hidden}")],      # symptom-hiding: must bounce
        [edit(PROMO, GOOD)],
        [("rerender", {})],
        [("finish", {"summary": "promo now shrinks to the viewport"})])
    res = await fix_finding(f, ws, base, store, emit=emit, llm=llm)
    assert res.status == "verified" and res.verification.passed and res.turns == 5
    assert "max-width:480px" in res.diff and "overflow:hidden" not in res.diff     # the blocked edit never stayed in the tree
    assert any(e["type"] == "fix.patch" and e["lint"] for e in events)            # ...and was reported to the UI as blocked
    assert any(e["type"] == "fix.patch" and not e["lint"] for e in events)
    assert [e["item"] for e in events if e["type"] == "fix.verify"] == ["lint", "target_gone", "no_new_findings", "no_drift", "build"]
    assert events[-1] == {"type": "fix.done", "status": "verified", "model": "scripted", "turns": 5}
    assert (repo / "index.html").read_text().count("480px") == 1 and "max-width" not in (repo / "index.html").read_text()   # the user's repo is untouched
    assert res.attempts[-1].verification.passed and res.summary.startswith("promo now")


async def test_failed_verification_is_handed_back_and_the_model_can_recover(session):
    f, ws, base, store, events, emit, _ = session
    llm = Scripted(
        [edit(PROMO, ".promo{width:420px;background:#fde;padding:12px}")],       # still overflows a 320px phone
        [("finish", {"summary": "done"})],
        [("reset", {})],
        [edit(PROMO, GOOD)],
        [("finish", {"summary": "really done"})])
    res = await fix_finding(f, ws, base, store, emit=emit, llm=llm)
    assert res.status == "verified" and len(res.attempts) == 2
    assert not res.attempts[0].verification.passed and res.attempts[1].verification.passed
    assert "420px" not in res.diff


async def test_verification_rounds_are_limited_and_the_result_is_failed(session):
    f, ws, base, store, _, emit, _ = session
    llm = Scripted(*[[edit(PROMO, ".promo{width:420px;background:#fde;padding:12px}")], [("finish", {"summary": "x"})],
                     [("reset", {})]] * 3)
    res = await fix_finding(f, ws, base, store, emit=emit, llm=llm, max_verifications=2)
    assert res.status == "failed" and not res.verification.passed and len(res.attempts) == 2


async def test_finish_without_edits_is_gave_up(session):
    f, ws, base, store, _, emit, _ = session
    res = await fix_finding(f, ws, base, store, emit=emit,
                            llm=Scripted([("finish", {"summary": "cannot fix this within the rules"}),]))
    assert res.status == "gave_up" and res.diff == "" and res.verification is None


async def test_a_plain_message_ends_the_session(session):
    f, ws, base, store, _, emit, _ = session
    res = await fix_finding(f, ws, base, store, emit=emit, llm=Scripted("I could not find the cause."))
    assert res.status == "gave_up" and res.summary == "I could not find the cause."


async def test_edit_budget_stops_the_loop_and_verifies_what_is_in_the_tree(session):
    f, ws, base, store, _, emit, _ = session
    # three misses, then a good edit that lands on the 4th (over the budget of 3): the loop stops and checks the tree
    llm = Scripted(*([[edit("text that is not in the file", "x")]] * 3), [edit(PROMO, GOOD)], [edit("never reached", "y")])
    res = await fix_finding(f, ws, base, store, emit=emit, llm=llm, max_edits=3)
    assert res.status == "verified" and res.turns == 4 and len(llm.steps) == 1


async def test_budget_without_a_fix_is_reported_as_budget(session):
    f, ws, base, store, _, emit, _ = session
    llm = Scripted(*([[edit("text that is not in the file", "x")]] * 5))
    res = await fix_finding(f, ws, base, store, emit=emit, llm=llm, max_edits=3)
    assert res.status == "budget" and res.diff == ""


async def test_tool_errors_go_back_to_the_model_not_to_the_user(session):
    f, ws, base, store, _, emit, _ = session
    llm = Scripted([("read_file", {"path": "../../etc/passwd", "start": 1, "end": 3})],
                   [("edit_file", {"path": "index.html"})],                       # missing arguments
                   [("no_such_tool", {})], "stop")
    res = await fix_finding(f, ws, base, store, emit=emit, llm=llm)
    assert res.status == "gave_up"                                                # nothing raised; nothing was edited
    assert "stay inside it" in llm.seen[1]                                        # the path error reached the model
    assert "bad arguments for edit_file" in llm.seen[2] and "unknown tool no_such_tool" in llm.seen[3]


# ----------------------------------------------------------------------------- the model wrapper
@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "CACHE", tmp_path / "cache")
    monkeypatch.setenv("FIXEL_MODE", "record")


class FakeResponse:
    def __init__(self, output):
        self.output = [type("O", (), {"model_dump": lambda self, **k: o})() for o in output]
        self.usage = type("U", (), {"total_tokens": 7, "model_dump": lambda self, **k: {"total_tokens": 7}})()


def fake_client(model_log, fail_models=()):
    class R:
        async def create(self, **kw):
            model_log.append(kw["model"])
            if kw["model"] in fail_models:
                req = httpx.Request("POST", "http://x")
                raise APIStatusError("model not found", response=httpx.Response(404, request=req), body=None)
            return FakeResponse([{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hi"}]}])
    return type("C", (), {"responses": R()})()


async def test_turns_are_cached_by_transcript(cache, monkeypatch):
    log = []
    monkeypatch.setattr(client, "get_client", lambda: fake_client(log))
    llm = FixLLM()
    items = [{"role": "user", "content": [{"type": "input_text", "text": "go"}]}]
    a = await llm.turn(list(items))
    b = await llm.turn(list(items))
    assert a == b and log == ["muse-wonder-1.0"] and llm.tokens == 7              # the second turn was served from the cache
    await llm.turn(items + [{"role": "user", "content": [{"type": "input_text", "text": "more"}]}])
    assert len(log) == 2                                                          # a different transcript is a different call


async def test_wonder_unavailable_falls_back_to_spark_and_drops_reasoning_items(cache, monkeypatch):
    log, events = [], []
    monkeypatch.setattr(client, "get_client", lambda: fake_client(log, fail_models={"muse-wonder-1.0"}))

    async def emit(ev):
        events.append(ev)

    llm = FixLLM(emit=emit)
    items = [{"role": "user", "content": []}, {"type": "reasoning", "id": "r1", "summary": []}]
    await llm.turn(items)
    assert log == ["muse-wonder-1.0", "muse-spark-1.3"] and llm.model == "muse-spark-1.3"
    assert not any(i.get("type") == "reasoning" for i in items)
    assert any(e["type"] == "fix.model_fallback" and e["to"] == "muse-spark-1.3" for e in events)


async def test_fallback_failure_is_raised(cache, monkeypatch):
    monkeypatch.setattr(client, "get_client", lambda: fake_client([], fail_models={"muse-wonder-1.0", "muse-spark-1.3"}))
    with pytest.raises(APIStatusError):
        await FixLLM().turn([{"role": "user", "content": []}])
