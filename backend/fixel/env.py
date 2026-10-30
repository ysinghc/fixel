"""Minimal .env loader (no dependency): KEY=VALUE lines, # comments, optional quotes. Never overrides the real environment."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value and value[0] in "'\"" and value.count(value[0]) >= 2:
            value = value[1:value.index(value[0], 1)]
        elif value.startswith("#"):
            value = ""                                         # a blank value followed by a comment
        else:
            value = value.split(" #", 1)[0].strip()            # an inline comment needs a space before the #
        if value:
            out[key.strip()] = value
    return out


def load_dotenv(*paths: Path) -> list[Path]:
    """Load the first .env found in the working directory, then the repo root. Returns the files read."""
    loaded = []
    for p in paths or (Path.cwd() / ".env", REPO_ROOT / ".env"):
        if p.is_file():
            for k, v in parse(p.read_text()).items():
                os.environ.setdefault(k, v)
            loaded.append(p)
    return loaded
