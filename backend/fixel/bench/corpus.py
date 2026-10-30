"""The benchmark's pages: the app routes of the target repos, split into development and test (guide section 9.1).

Thresholds are tuned on the development split only; results are reported on the test split only. The planted-defect
demo app belongs to neither: it already contains real defects, so it is a demo, not a corpus.
Storybook libraries and synthetic pages (Spark Contributor + Muse Image) are not built yet.
"""
from pathlib import Path

from .. import config as cfg

SPLITS = {"dev": "development", "test": "test"}


def target_configs(split: str, root: str | Path = "targets") -> list[cfg.Config]:
    """Every targets/*.yaml whose target.split is the requested split ('dev' or 'test')."""
    if split not in SPLITS:
        raise ValueError(f"split must be one of {sorted(SPLITS)}")
    out = []
    for p in sorted(Path(root).glob("*.yaml")):
        conf = cfg.load(p)
        if conf.target.split == SPLITS[split]:
            out.append(conf)
    if not out:
        raise FileNotFoundError(f"no target with split '{SPLITS[split]}' under {root}")
    return out


def states(conf: cfg.Config, widths: list[int] | None = None):
    """The target's state matrix (route x width x theme x text stress), optionally restricted to some widths."""
    return [s for s in conf.states() if not widths or s.width in widths]
