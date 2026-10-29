"""SAM wire format: the prompt builder against Meta's documented example, the parser against a real response."""
from pathlib import Path

import pytest

from fixel.meta import client, sam

REAL = (Path(__file__).parent / "fixtures" / "sam_raw_one_bit.txt").read_text()


def test_prompt_matches_documented_builder_output():
    # docs: PromptBox(left=444, top=626, right=676, bottom=850) on 1800x1200 -> x2=675, y2=849 (half-open minus one)
    assert sam.build_prompt((1800, 1200), {1: (444, 626, 676, 850)}) == \
        "<0f>1<|box;x1=444;y1=626;x2=675;y2=849;w=1800;h=1200|>"


def test_prompt_joins_objects_with_commas_in_input_order():
    text = sam.build_prompt((100, 50), {7: (0, 0, 10, 10), 3: (20, 20, 40, 30)})
    assert text == ("<0f>7<|box;x1=0;y1=0;x2=9;y2=9;w=100;h=50|>,"
                    "3<|box;x1=20;y1=20;x2=39;y2=29;w=100;h=50|>")


def test_clamp_box_is_half_open_inside_the_image_and_drops_slivers():
    assert sam.clamp_box((16.0, 523.67, 176.0, 567.67), (375, 560)) == (16, 523, 177, 560)
    assert sam.clamp_box((-5, -5, 20, 20), (375, 560)) == (0, 0, 21, 21)
    assert sam.clamp_box((10, 10, 12, 40), (375, 560)) is None            # 3 px wide
    assert sam.clamp_box((10, 600, 80, 640), (375, 560)) is None          # below the image


def test_parse_real_response():
    got = sam.parse(REAL)
    assert sorted(got) == [1, 2]
    b = got[1]
    assert (b.left, b.top, b.right, b.bottom) == (8, 524, 181, 560)       # x2/y2 on the wire are inclusive
    assert b.conf == pytest.approx(0.6015625) and b.mask_hw == (36, 173) and b.mask_encoding == "!"
    assert b.mask_hw == (b.bottom - b.top, b.right - b.left)              # masks are local to their box


def test_parse_empty_lane_is_zero_matches_not_an_error():
    assert sam.parse("") == {}


def test_parse_without_confidence():
    raw = "<0f>4<|box;x1=1;y1=2;x2=10;y2=12;w=50;h=50|><|mask;x=0;y=0;data=11,10,~abc|>"
    assert sam.parse(raw)[4].conf is None


def test_iou_and_spill():
    prompt = (10, 10, 110, 60)
    same = sam.SamBox(1, 10, 10, 110, 60, 0.9, (50, 100), "!", "")
    wide = sam.SamBox(1, 10, 10, 210, 60, 0.9, (50, 200), "!", "")       # object twice as wide as the prompt
    assert sam.iou_and_spill(prompt, same) == (1.0, 0.0)
    iou, spill = sam.iou_and_spill(prompt, wide)
    assert iou == pytest.approx(0.5) and spill == pytest.approx(0.5)


class FakeStream:
    def __init__(self, raw): self.raw = raw
    def __aiter__(self): return self._gen()
    async def _gen(self):
        class Ev: pass
        e = Ev(); e.type = "response.output_text.delta"; e.delta = self.raw
        yield e


async def test_segment_boxes_chunks_at_sixteen_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "CACHE", tmp_path / "cache")
    monkeypatch.setenv("FIXEL_MODE", "record")
    prompts = []

    class Responses:
        async def create(self, **kw):
            prompts.append(kw["input"][0]["content"][0]["text"])
            return FakeStream(REAL)

    class Fake: responses = Responses()
    monkeypatch.setattr(client, "get_client", lambda: Fake())
    boxes = {i: (i * 5, 0, i * 5 + 20, 20) for i in range(20)}
    out = await sam.segment_boxes(b"png", "sha1", (400, 100), boxes)
    assert len(prompts) == 2 and prompts[0].count("<|box") == 16 and prompts[1].count("<|box") == 4
    assert sorted(out) == [1, 2]
    await sam.segment_boxes(b"png", "sha1", (400, 100), boxes)           # second run: all from cache
    assert len(prompts) == 2
