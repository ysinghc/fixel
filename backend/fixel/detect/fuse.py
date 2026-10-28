"""Decision policy and grouping into findings: the decision is code, not a prompt (guide section 6.6)."""
import hashlib
from collections import defaultdict

from ..models import Candidate, Capture, Element, Finding, PixelEvidence, Triage

T = {"spill": 0.35, "diff": 0.05}            # starting values; tuned on the dev split only
ALWAYS_OBSERVABLE = {"viewport_protrusion", "clipped_text", "contrast", "small_target"}
# strongest first: a finding takes the best status any of its candidates reached
STATUS_RANK = ["confirmed", "needs_review", "dismissed", "not_observable"]


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


def text_hash(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:8]


def elem_id(e: Element) -> str:
    """Stable across re-renders: the source location when known, else tag plus a hash of its text."""
    return e.loc or f"{e.tag}#{text_hash(e.text)}"


def finding_key(c: Candidate, by_id: dict[int, Element]) -> str:
    parts = sorted(elem_id(by_id[i]) for i in c.elements if i in by_id)
    return f"{c.type}|{'|'.join(parts)}"


def candidate_key(cap: Capture, c: Candidate) -> str:
    return finding_key(c, {e.id: e for e in cap.tiles[c.tile].elements})


def fuse(items: list[tuple[Capture, Candidate, PixelEvidence]], triage: dict[str, Triage] | None = None) -> list[Finding]:
    """Group candidates with the same key across states into one finding with its width range.

    triage maps a finding key to Spark's verdict for it (one call per finding, not per candidate).
    """
    triage = triage or {}
    groups: dict[str, list[tuple[Capture, Candidate, PixelEvidence, str]]] = defaultdict(list)
    for cap, c, px in items:
        key = candidate_key(cap, c)
        groups[key].append((cap, c, px, decide(c, px, triage.get(key))))
    findings = []
    for key, members in groups.items():
        status = min((m[3] for m in members), key=STATUS_RANK.index)
        shown = [m for m in members if m[3] == status] if status != "not_observable" else members
        by_id = {e.id: e for e in shown[0][0].tiles[shown[0][1].tile].elements}
        findings.append(Finding(
            key=key, type=shown[0][1].type, status=status,
            widths=sorted({m[0].state.width for m in shown}),
            candidates=[m[1] for m in shown], evidence=[m[2] for m in shown], triage=triage.get(key),
            locs=sorted({by_id[i].loc for i in shown[0][1].elements if i in by_id and by_id[i].loc})))
    order = {s: i for i, s in enumerate(STATUS_RANK)}
    return sorted(findings, key=lambda f: (order[f.status], f.type, f.key))
