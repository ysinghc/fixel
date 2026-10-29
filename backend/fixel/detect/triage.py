"""Triage: Muse Spark 1.3 judges one candidate from an annotated crop, with schema-checked output (guide 6.5).

Spark can dismiss a candidate as intentional or flag it for review; it never creates one.
"""
import base64
import hashlib
import io
import json

from PIL import Image, ImageDraw
from pydantic import ValidationError

from ..meta import client as meta
from ..meta.client import EmptyOutput, call
from ..models import Candidate, Capture, PixelEvidence, Triage

DEFECT_TYPES = ("viewport_protrusion", "element_protrusion", "clipped_text", "collision",
                "occlusion", "small_target", "contrast")

TRIAGE_SYSTEM = """You review one candidate layout defect in a web page screenshot.
The red box is element A; the blue box, if present, is element B. The evidence JSON names the
geometric check that fired, its measurements, and pixel checks. Decide whether a typical user at
this viewport would see a defect. Answer "intentional" only for a deliberate pattern: a badge on
an icon, an open dropdown over content, a sticky header over content that can be scrolled into
view. Describe only what is visible in the images. If they do not let you tell, answer "unsure"."""

TRIAGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["verdict", "defect_type", "severity", "what_the_user_sees", "fix_hint", "confidence"],
    "properties": {
        "verdict": {"type": "string", "enum": ["real_defect", "intentional", "not_visible", "unsure"]},
        "defect_type": {"type": "string", "enum": list(DEFECT_TYPES)},
        "severity": {"type": "integer"},
        "what_the_user_sees": {"type": "string"},
        "fix_hint": {"type": "string"},
        "confidence": {"type": "number"},
    },
}

RED, BLUE = (230, 30, 30), (30, 90, 230)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def crop_and_thumb(tile_png: bytes, rects: list[tuple], pad: int = 40, min_short: int = 320) -> tuple[bytes, bytes]:
    """The padded crop around the candidate's elements (A red, B blue, upscaled to >= min_short px on its short
    side) and a whole-viewport thumbnail with the same outlines for context."""
    img = Image.open(io.BytesIO(tile_png)).convert("RGB")
    ann = img.copy()
    d = ImageDraw.Draw(ann)
    for r, colour in zip(rects, (RED, BLUE)):
        d.rectangle([r[0], r[1], r[2] - 1, r[3] - 1], outline=colour, width=2)
    x1 = max(0, int(min(r[0] for r in rects)) - pad)
    y1 = max(0, int(min(r[1] for r in rects)) - pad)
    x2 = min(img.width, int(max(r[2] for r in rects)) + pad)
    y2 = min(img.height, int(max(r[3] for r in rects)) + pad)
    if x2 - x1 < 2 or y2 - y1 < 2:                       # the elements lie outside this viewport shot: show all of it
        x1, y1, x2, y2 = 0, 0, img.width, img.height
    crop = ann.crop((x1, y1, x2, y2))
    short = min(crop.size)
    if short < min_short:
        k = min_short / max(short, 1)
        crop = crop.resize((round(crop.width * k), round(crop.height * k)), Image.LANCZOS)
    thumb = ann.copy()
    thumb.thumbnail((360, 640))
    return _png(crop), _png(thumb)


def evidence_dict(cap: Capture, c: Candidate, px: PixelEvidence) -> dict:
    tile = cap.tiles[c.tile]
    by_id = {e.id: e for e in tile.elements}
    return {"check": c.type, "viewport_px": [cap.vw, cap.vh], "measurements": c.metrics,
            "elements": [{"label": "AB"[i], "tag": by_id[x].tag, "text": by_id[x].text[:60]}
                         for i, x in enumerate(c.elements[:2]) if x in by_id],
            "pixels": px.model_dump(exclude_none=True)}


async def triage(crop: bytes, thumb: bytes, evidence: dict, model: str = "muse-spark-1.3", emit=None) -> Triage:
    async def go():
        r = await meta.get_client().responses.create(
            model=model, instructions=TRIAGE_SYSTEM,          # constant prefix: prompt-cache friendly
            input=[{"role": "user", "content": [
                {"type": "input_text", "text": json.dumps(evidence)},
                {"type": "input_image", "image_url": data_url(crop)},
                {"type": "input_image", "image_url": data_url(thumb)}]}],
            text={"format": {"type": "json_schema", "name": "triage", "schema": TRIAGE_SCHEMA, "strict": True}},
            reasoning={"effort": "low"})
        if not r.output_text.strip():
            raise EmptyOutput()
        try:
            Triage.model_validate_json(r.output_text)       # out-of-range numbers: retry, and never cache the bad answer
        except ValidationError as e:
            raise EmptyOutput(str(e)) from e
        return {"json": r.output_text, "usage": r.usage.model_dump() if r.usage else None}
    key = {"model": model, "v": 3, "crop": sha(crop), "thumb": sha(thumb), "ev": evidence}
    out = await call("spark.triage", key, go, emit)
    return Triage.model_validate_json(out["json"])        # numeric ranges are enforced here


def candidate_rects(cap: Capture, c: Candidate) -> list[tuple]:
    """Outlines for the crop: A (red) then B (blue). Text collisions outline the tight text boxes."""
    by_id = {e.id: e for e in cap.tiles[c.tile].elements}
    els = [by_id[i] for i in c.elements[:2] if i in by_id]
    return [(e.text_rect or e.rect) if c.type == "collision" else e.rect for e in els]


async def triage_candidate(cap: Capture, c: Candidate, px: PixelEvidence, store, model: str = "muse-spark-1.3",
                           emit=None) -> Triage:
    tile = cap.tiles[c.tile]
    crop, thumb = crop_and_thumb(store.get(tile.png_sha), candidate_rects(cap, c))
    return await triage(crop, thumb, evidence_dict(cap, c, px), model, emit)
