"""Content-addressed artifact store for screenshots, crops and masks.

Callers pass SHAs (never image bytes) into model-call cache keys, so keys stay small and stable.
"""
import hashlib
from pathlib import Path

ROOT = Path(".fixel/artifacts")


class ArtifactStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else ROOT

    def path(self, sha: str) -> Path:
        return self.root / sha[:2] / f"{sha}.png"

    def put(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        p = self.path(sha)
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return sha

    def get(self, sha: str) -> bytes:
        return self.path(sha).read_bytes()
