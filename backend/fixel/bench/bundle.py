"""Move a benchmark run to another machine so a person can label it there, and bring the labels back.

The screenshots a labeller needs live in the content-addressed artifact store, which is gitignored and local to the machine
that ran the benchmark. A bundle is a tar.gz of the run directory plus exactly the screenshots its cases reference. The
labelling UI stays blind: it serves only the queue API, never the case files, so having them on disk does not leak anything
into the labelling view. Labels come back as the small labels.json written by `fixel bench export`.
"""
import json
import tarfile
from pathlib import Path

from . import labelling, metrics


def bundle(run: Path, dest: Path | None = None, artifacts: Path = Path(".fixel/artifacts")) -> Path:
    run = Path(run)
    labelling.queue(run)                                           # fix the queue now, so both machines agree on it
    dest = Path(dest) if dest else Path(f"{run.name}.bench.tar.gz")
    shas = sorted({s for c in metrics.load_cases(run) for s in c["tiles"]})
    with tarfile.open(dest, "w:gz") as tar:
        for p in sorted(run.rglob("*")):
            if p.is_file() and p.name != "labels.json":            # labels are made on the labelling machine, not shipped
                tar.add(p, arcname=f"bench/{run.name}/{p.relative_to(run)}")
        for s in shas:
            tar.add(artifacts / s[:2] / f"{s}.png", arcname=f"artifacts/{s[:2]}/{s}.png")
    return dest


def import_bundle(archive: Path, fixel_dir: Path = Path(".fixel")) -> str:
    """Unpack a bundle into .fixel/ and return the run name. Refuses anything that would land outside it."""
    fixel_dir = Path(fixel_dir)
    runs = set()
    with tarfile.open(archive) as tar:
        for m in tar.getmembers():
            parts = Path(m.name).parts
            if m.isdir():
                continue
            if m.name.startswith("/") or ".." in parts or not m.isfile() or parts[0] not in ("bench", "artifacts"):
                raise ValueError(f"refusing unexpected bundle member: {m.name}")
            if parts[0] == "bench":
                runs.add(parts[1])
        tar.extractall(fixel_dir, filter="data")
    if len(runs) != 1:
        raise ValueError(f"a bundle holds exactly one run, found {sorted(runs)}")
    return runs.pop()


def labels_from_file(path: Path) -> dict[str, str]:
    """Read a labels.json produced by the labelling machine (`{case_id: {"label": ...}}`)."""
    return {k: v["label"] for k, v in json.loads(Path(path).read_text()).items()}
