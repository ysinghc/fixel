"""A run can be bundled, unpacked on another machine and labelled there; hostile archives are refused."""
import io
import json
import tarfile
from pathlib import Path

import pytest
from PIL import Image

from fixel.bench import bundle, labelling, metrics
from fixel.store import ArtifactStore
from test_bench_metrics import write_run


def png(tmp: Path, colour) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), colour).save(buf, "PNG")
    return buf.getvalue()


def test_round_trip_carries_the_run_and_exactly_its_screenshots(tmp_path):
    src = tmp_path / "src"
    store = ArtifactStore(src / "artifacts")
    run = write_run(src / "bench")
    sha = store.put(png(tmp_path, (1, 2, 3)))
    store.put(png(tmp_path, (9, 9, 9)))                                  # an unrelated screenshot must not travel
    for p in (run / "cases").glob("*.json"):
        c = json.loads(p.read_text())
        c["tiles"] = [sha]
        p.write_text(json.dumps(c))
    metrics.put_label(run, "m1", "visible_defect")                       # labels stay with whoever made them
    archive = bundle.bundle(run, tmp_path / "r.tar.gz", artifacts=src / "artifacts")

    dst = tmp_path / "dst"
    assert bundle.import_bundle(archive, dst) == "r1"
    assert (dst / "artifacts" / sha[:2] / f"{sha}.png").is_file()
    assert len(list((dst / "artifacts").rglob("*.png"))) == 1
    assert not (dst / "bench" / "r1" / "labels.json").exists()
    assert labelling.queue(dst / "bench" / "r1") == labelling.queue(run)     # both machines show the same queue


def test_labels_come_back_as_a_small_file(tmp_path):
    run = write_run(tmp_path / "bench")
    metrics.put_label(run, "m1", "visible_defect")
    metrics.put_label(run, "k1", "no_visible_defect")
    assert bundle.labels_from_file(run / "labels.json") == {"m1": "visible_defect", "k1": "no_visible_defect"}


@pytest.mark.parametrize("name", ["../evil.txt", "/etc/evil.txt", "other/x.txt"])
def test_import_refuses_members_outside_bench_and_artifacts(tmp_path, name):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        data = b"x"
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    with pytest.raises(ValueError, match="refusing"):
        bundle.import_bundle(archive, tmp_path / "dst")
    assert not (tmp_path / "evil.txt").exists()
