"""Typed view of fixel.yaml (draft schema; guide sections 2, 8.3, 14.3)."""
from pathlib import Path

import yaml
from pydantic import BaseModel

from .models import StateSpec


class Target(BaseModel):
    name: str = "app"
    path: str | None = None
    dev_cmd: str | None = None
    base_url: str = "http://localhost:5173"
    env: dict[str, str] = {}


class Matrix(BaseModel):
    widths: list[int] = [320, 375, 414, 768, 1024, 1280, 1440]
    themes: list[str] = ["light", "dark"]
    text_stress: list[str] = ["none", "pseudo"]
    height: int = 800


class Concurrency(BaseModel):
    browser_contexts: int = 4
    sam: int = 4
    spark: int = 4
    fix_sessions: int = 1


class Budget(BaseModel):
    max_usd_per_run: float = 10.0


class Models(BaseModel):
    triage: str = "muse-spark-1.3"
    fixer: str = "muse-wonder-1.0"
    fixer_fallback: str = "muse-spark-1.3"
    segmentation: str = "sam-3.1"


class Config(BaseModel):
    target: Target = Target()
    routes: list[str] = ["/"]
    matrix: Matrix = Matrix()
    concurrency: Concurrency = Concurrency()
    budget: Budget = Budget()
    models: Models = Models()

    def states(self) -> list[StateSpec]:
        m = self.matrix
        return [StateSpec(route=r, width=w, height=m.height, theme=t, text_stress=s)
                for r in self.routes for w in m.widths for t in m.themes for s in m.text_stress]


def load(path: str | Path = "fixel.yaml") -> Config:
    return Config.model_validate(yaml.safe_load(Path(path).read_text()) or {})
