from fixel.cli import pick_finding, print_event
from fixel.models import Candidate, Finding


def finding(key, status="confirmed"):
    c = Candidate(type="viewport_protrusion", state_key="/|320|light|none|0", tile=0, elements=[1], metrics={})
    return Finding(key=key, type="viewport_protrusion", status=status, widths=[320], candidates=[c], evidence=[], triage=None, locs=[])


FS = [finding("viewport_protrusion|a"), finding("collision|b", "dismissed"), finding("occlusion|c"), finding("viewport_protrusion|d")]


def test_pick_finding_chooses_among_confirmed_ones_only():
    assert pick_finding(FS, None, None).key == "viewport_protrusion|a"            # default: the first
    assert pick_finding(FS, None, 2).key == "occlusion|c"                          # 1-based, counted over confirmed findings as listed
    assert pick_finding(FS, "occlusion", None).key == "occlusion|c"
    assert pick_finding(FS, "collision", None) is None                             # dismissed findings are not fixable
    assert pick_finding(FS, None, 9) is None and pick_finding([], None, None) is None


def test_print_event_covers_the_agent_events(capsys):
    for ev in ({"type": "fix.tool", "name": "edit_file", "args": {"path": "src/A.jsx"}},
               {"type": "fix.patch", "diff": "", "lint": ["clipping hides the symptom"]},
               {"type": "fix.verify", "item": "build", "ok": False},
               {"type": "fix.model_fallback", "from": "muse-wonder-1.0", "to": "muse-spark-1.3", "reason": "NotFoundError"},
               {"type": "model.call", "kind": "fix.turn", "source": "live", "usage": None}):
        print_event(ev)
    out = capsys.readouterr().out
    assert "edit_file src/A.jsx" in out and "BLOCKED by the linter: clipping" in out
    assert "verify build" in out and "FAILED" in out and "continuing on muse-spark-1.3" in out
