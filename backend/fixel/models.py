from typing import Literal
from pydantic import BaseModel, Field

Rect = tuple[float, float, float, float]          # x1, y1, x2, y2 in CSS px (= image px at scale 1)

class StateSpec(BaseModel):
    route: str                                    # "/checkout" or "story:button--primary"
    width: int
    height: int = 800
    theme: Literal["light", "dark"] = "light"
    text_stress: Literal["none", "pseudo"] = "none"
    replay: list[dict] = []                       # explorer steps to reach a modal or menu
    @property
    def key(self) -> str:
        return f"{self.route}|{self.width}|{self.theme}|{self.text_stress}|{len(self.replay)}"

class Element(BaseModel):
    id: int                                       # per-snapshot id (data-fixel-id)
    parent: int | None
    tag: str
    loc: str | None                               # "src/components/Cart.tsx:42:7" from data-loc
    rect: Rect
    text_rect: Rect | None                        # tight box around own text nodes
    text: str
    interactive: bool
    replaced: bool                                # img, svg, input, canvas...
    style: dict[str, str]
    scroll: tuple[int, int, int, int]             # scrollW, clientW, scrollH, clientH

class Tile(BaseModel):
    scroll_y: int
    png_sha: str                                  # content-addressed artifact
    elements: list[Element]
    occlusion: dict[int, dict]                    # element id -> {covered: 0..1, by: id}

class Capture(BaseModel):
    state: StateSpec
    vw: int; vh: int; doc_w: int
    doc_h: int = 0                                # document height, for scroll reachability
    tiles: list[Tile]
    axe: list[dict]

DefectType = Literal["viewport_protrusion", "element_protrusion", "clipped_text",
                     "collision", "occlusion", "small_target", "contrast"]

class Candidate(BaseModel):
    type: DefectType
    state_key: str
    tile: int
    elements: list[int]                           # 1 or 2 element ids
    metrics: dict[str, float]

class PixelEvidence(BaseModel):
    sam_fill: float | None = None                 # mask area inside the DOM box / box area
    sam_spill: float | None = None                # share of the returned bounds outside the DOM box (mask-based once the parser is installed)
    sam_conf: float | None = None
    sam_iou: float | None = None                  # IoU of the returned bounds with the prompted DOM box
    opacity_diff: float | None = None             # share of overlap pixels that change when B is hidden
    observable: bool

class Triage(BaseModel):
    verdict: Literal["real_defect", "intentional", "not_visible", "unsure"]
    defect_type: DefectType
    severity: int = Field(ge=1, le=4)
    what_the_user_sees: str
    fix_hint: str
    confidence: float = Field(ge=0, le=1)

class Finding(BaseModel):
    key: str                                      # type + source locations (+ text hash fallback)
    type: DefectType
    status: Literal["confirmed", "needs_review", "dismissed", "not_observable"]
    widths: list[int]                             # where it reproduces
    candidates: list[Candidate]
    evidence: list[PixelEvidence]
    triage: Triage | None
    locs: list[str]

class Verification(BaseModel):
    target_gone: bool
    new_findings: list[str]
    drifted: list[str]
    build_ok: bool
    lint_ok: bool
    grid: dict[str, bool] = {}                    # state key -> the target finding is gone in that state
    notes: list[str] = []                         # build output tail, lint errors: what to show when something fails
    @property
    def passed(self) -> bool:
        return self.target_gone and not self.new_findings and not self.drifted and self.build_ok and self.lint_ok

class FixAttempt(BaseModel):
    finding_key: str
    model: str
    diff: str
    lint_errors: list[str]
    verification: Verification | None
    citations: list[str] = []
