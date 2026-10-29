"""SAM 3.1 box prompts: build the prompt, stream the raw lane through the cache, parse the records (guide 6.4).

Written against the documented wire grammar (dev.meta.ai/docs/sam), so it needs no extra package. Masks are
not decoded here: their payload is entropy-coded and decoded by the official meta-sam-parser, which is not
installed. What the records already give is enough for evidence: a confidence per box and the bounds of the
segmented object. Mask fill/spill can be added once the parser is available.
"""
import base64
import re
from dataclasses import dataclass

from . import client as meta
from .client import call

MAX_OBJECTS = 16                                  # API limit for prompted objects per request
MIN_BOX_PX = 4                                    # boxes thinner than this carry no signal
METADATA = {"include_confidence": "true", "mask_encoding": "one_bit"}
RECORD = re.compile(
    r"(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)(?:;c=([0-9.]+))?\|>"
    r"<\|mask;x=0;y=0(?:;c=[0-9.]+)?;data=(\d+),(\d+),(.)([^|]*)\|>")


@dataclass(frozen=True)
class SamBox:
    id: int
    left: int
    top: int
    right: int                                    # half-open, like the prompt
    bottom: int
    conf: float | None
    mask_hw: tuple[int, int]
    mask_encoding: str
    mask_payload: str                             # base85 text; decode with meta-sam-parser when needed

    @property
    def area(self) -> int:
        return max(0, self.right - self.left) * max(0, self.bottom - self.top)


def clamp_box(rect, size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    """Integer half-open box inside the image, or None when it is too small to prompt."""
    w, h = size
    left, top = max(0, int(rect[0])), max(0, int(rect[1]))
    right, bottom = min(w, int(rect[2]) + 1), min(h, int(rect[3]) + 1)
    return (left, top, right, bottom) if right - left >= MIN_BOX_PX and bottom - top >= MIN_BOX_PX else None


def build_prompt(size: tuple[int, int], boxes: dict[int, tuple[int, int, int, int]]) -> str:
    """<0f>id<|box;...|>,id<|box;...|> with x2/y2 inclusive (the half-open right/bottom minus one)."""
    w, h = size
    return "<0f>" + ",".join(f"{i}<|box;x1={l};y1={t};x2={r - 1};y2={b - 1};w={w};h={h}|>"
                             for i, (l, t, r, b) in boxes.items())


def parse(raw: str) -> dict[int, SamBox]:
    """Records keyed by object id. Zero matches is a valid answer (empty dict)."""
    out = {}
    for m in RECORD.finditer(raw):
        i = int(m[1])
        out[i] = SamBox(i, int(m[2]), int(m[3]), int(m[4]) + 1, int(m[5]) + 1,
                        float(m[8]) if m[8] else None, (int(m[9]), int(m[10])), m[11], m[12])
    return out


def iou_and_spill(prompt: tuple[int, int, int, int], got: SamBox) -> tuple[float, float]:
    """IoU of the returned bounds with the prompted box, and the share of the returned bounds outside it."""
    l, t, r, b = prompt
    ix = max(0, min(r, got.right) - max(l, got.left))
    iy = max(0, min(b, got.bottom) - max(t, got.top))
    inter, parea = ix * iy, (r - l) * (b - t)
    union = parea + got.area - inter
    return (inter / union if union else 0.0), (1 - inter / got.area if got.area else 0.0)


async def segment_boxes(png: bytes, png_sha: str, size: tuple[int, int],
                        boxes: dict[int, tuple[int, int, int, int]], emit=None) -> dict[int, SamBox]:
    """Box-prompt every object (in requests of at most 16). boxes: object id -> half-open pixel box."""
    ids = list(boxes)
    result: dict[int, SamBox] = {}
    for k in range(0, len(ids), MAX_OBJECTS):
        chunk = {i: boxes[i] for i in ids[k:k + MAX_OBJECTS]}
        text = build_prompt(size, chunk)

        async def go(text=text):
            stream = await meta.get_client().responses.create(
                model="sam-3.1", stream=True, metadata=METADATA,
                input=[{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": text},
                    {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode()}]}])
            parts, images = [], None
            async for ev in stream:                      # cache the raw lane; parse offline
                if ev.type == "response.output_text.delta":
                    parts.append(ev.delta)
                elif ev.type == "response.completed" and getattr(ev.response, "usage", None):
                    images = getattr(ev.response.usage, "images_processed", None)
            return {"raw": "".join(parts), "usage": {"images": images}}

        out = await call("sam.box", {"img": png_sha, "prompt": text, "md": METADATA, "v": 1}, go, emit)
        result.update(parse(out["raw"]))
    return result
