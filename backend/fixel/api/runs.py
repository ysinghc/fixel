"""Runs: orchestrate scans and fix sessions, persist every event, broadcast it to subscribers (guide section 8.3).

A run is one scan; fix sessions started from its findings append to the SAME event stream, so one connection tells the
whole story. Every event is durable (api/db.py) before it is fanned out, and the UI is a pure function of the log.
"""
import asyncio
import time
import traceback
import uuid
from collections import defaultdict
from pathlib import Path

from .. import config as cfg
from .. import cost
from ..fix.agent import FixLLM, fix_finding
from ..fix.worktree import Workspace
from ..meta import client as meta
from ..models import Finding
from ..detect.fuse import candidate_key
from ..scan import Scanned, findings_of, models_available, scan_states, triage_findings
from ..store import ArtifactStore
from ..target import TargetServer
from ..verify.matrix import matrix_states, route_of
from .db import DB

DEFAULT_BUDGET_USD = 10.0


class RunError(Exception):
    """A request that cannot be served (maps to a 4xx)."""
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class RunManager:
    def __init__(self, db: DB, store: ArtifactStore, root: Path, config_roots: list[Path] | None = None,
                 llm_factory=None, budget_usd: float = DEFAULT_BUDGET_USD):
        self.db, self.store, self.root = db, store, Path(root).resolve()
        self.config_roots = [Path(p).resolve() for p in (config_roots or [self.root / "fixel.yaml", self.root / "targets"])]
        self.llm_factory = llm_factory
        self.budget_usd = budget_usd
        self.subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self.tasks: dict[str, asyncio.Task] = {}
        self.cost: dict[str, float] = defaultdict(float)
        self.stopped: set[str] = set()                     # runs that ran out of budget: nothing new starts
        self.cancelled: set[str] = set()                   # runs the user cancelled
        self.fix_lock = asyncio.Lock()                     # one fix session at a time (a dev server and a browser each)

    # ------------------------------------------------------------------ events
    async def emit(self, run_id: str, ev: dict) -> dict:
        """Durable first, then fan out to every subscriber."""
        if ev.get("type") == "model.call":
            usd = cost.usd(ev.get("kind", ""), ev.get("model"), ev.get("usage"), ev.get("source", "live"))
            self.cost[run_id] += usd
            ev = {**ev, "usd": round(usd, 6), "total_usd": round(self.cost[run_id], 6)}
            if self.cost[run_id] >= self.budget_usd and run_id not in self.stopped:
                self.stopped.add(run_id)                   # in-flight calls finish; nothing new starts
                await self.emit(run_id, {"type": "budget.exceeded", "budget_usd": self.budget_usd,
                                         "total_usd": round(self.cost[run_id], 6)})
        ev = self.db.append_event(run_id, ev)
        for q in list(self.subs[run_id]):
            q.put_nowait(ev)
        return ev

    def emitter(self, run_id: str):
        async def emit(ev: dict) -> None:
            await self.emit(run_id, ev)
        return emit

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subs[run_id].add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        self.subs[run_id].discard(q)

    # ------------------------------------------------------------------ config
    def resolve_config(self, path: str) -> Path:
        """Only fixel.yaml and the files under targets/ (or the configured roots) can be used as a scan config."""
        p = (self.root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if not p.is_file() or not any(p == r or r in p.parents for r in self.config_roots):
            raise RunError(f"unknown config {path!r}: use fixel.yaml or a file under targets/", 404)
        return p

    def build_conf(self, config_path: str, o: dict) -> cfg.Config:
        conf = cfg.load(self.resolve_config(config_path))
        if o.get("routes"):
            conf.routes = o["routes"]
        if o.get("widths"):
            conf.matrix.widths = o["widths"]
        if o.get("themes"):
            conf.matrix.themes = o["themes"]
        if o.get("stress"):
            conf.matrix.text_stress = o["stress"]
        if o.get("height"):
            conf.matrix.height = o["height"]
        # a relative target path is relative to the repo root, not to wherever the server was started
        if conf.target.path and not Path(conf.target.path).is_absolute():
            conf.target.path = str(self.root / conf.target.path)
        return conf

    def targets(self) -> list[dict]:
        out = []
        files = [self.root / "fixel.yaml"] if (self.root / "fixel.yaml").is_file() else []
        for r in self.config_roots:
            if r.is_dir():
                files += sorted(r.glob("*.yaml"))
        for f in files:
            try:
                conf = cfg.load(f)
            except Exception:
                continue
            out.append({"config": str(f.relative_to(self.root)) if self.root in f.parents else str(f),
                        "name": conf.target.name, "split": conf.target.split, "routes": conf.routes,
                        "widths": conf.matrix.widths, "themes": conf.matrix.themes, "text_stress": conf.matrix.text_stress,
                        "height": conf.matrix.height})
        return out

    # ------------------------------------------------------------------ scans
    def start_scan(self, req: dict) -> str:
        o = {k: req.get(k) for k in ("routes", "widths", "themes", "stress", "height")}
        conf = self.build_conf(req.get("config", "fixel.yaml"), o)
        models = bool(req.get("models", True)) and models_available()
        run_id = self.db.create_run("scan", {"config": req.get("config", "fixel.yaml"), "overrides": o,
                                             "base_url": req.get("base_url"), "models": models})
        self.tasks[run_id] = asyncio.create_task(self._scan(run_id, conf, req.get("base_url"), models))
        return run_id

    async def _scan(self, run_id: str, conf: cfg.Config, base_url: str | None, models: bool) -> None:
        emit = self.emitter(run_id)
        stop = lambda: run_id in self.stopped or run_id in self.cancelled
        states = conf.states()
        try:
            await emit({"type": "run.started", "run_id": run_id, "target": conf.target.name, "split": conf.target.split,
                        "routes": conf.routes, "states": len(states), "models": models, "mode": meta.mode(),
                        "budget_usd": self.budget_usd, "widths": conf.matrix.widths, "themes": conf.matrix.themes,
                        "text_stress": conf.matrix.text_stress})

            async def persist(r: Scanned) -> None:
                self.db.put_capture(run_id, r.cap.state.key, {
                    "capture": r.cap.model_dump(), "candidates": [c.model_dump() for c in r.candidates],
                    "evidence": [e.model_dump() for e in r.evidence]})

            par = conf.concurrency.browser_contexts
            if base_url:
                results = await scan_states(states, base_url, self.store, par, sam=models, emit=emit, on_state=persist,
                                            should_stop=stop)
            else:
                server = TargetServer(conf.target)
                async with server as url:
                    for note in server.notes:
                        await emit({"type": "run.note", "note": note})
                    results = await scan_states(states, url, self.store, par, sam=models, emit=emit, on_state=persist,
                                                should_stop=stop)
            findings = findings_of(results)
            await self._publish_findings(run_id, findings)
            if models and not stop():
                triage = await triage_findings(results, findings, self.store, conf.models.triage, emit=emit, should_stop=stop)
                findings = findings_of(results, triage)
                await self._publish_findings(run_id, findings)
            counts = {st: sum(f.status == st for f in findings) for st in ("confirmed", "needs_review", "dismissed", "not_observable")}
            status = "cancelled" if run_id in self.cancelled else ("stopped" if run_id in self.stopped else "done")
            summary = {"counts": counts, "findings": len(findings), "states": len(results), "total_usd": round(self.cost[run_id], 4)}
            self.db.set_run(run_id, status, summary)
            await emit({"type": "run.done", "status": status, **summary})
        except asyncio.CancelledError:
            self.db.set_run(run_id, "cancelled")
            await emit({"type": "run.done", "status": "cancelled"})
            raise
        except Exception as e:
            traceback.print_exc()
            self.db.set_run(run_id, "failed", {"error": str(e)})
            await emit({"type": "run.error", "error": f"{type(e).__name__}: {str(e)[:600]}"})
        finally:
            self.tasks.pop(run_id, None)

    async def _publish_findings(self, run_id: str, findings: list[Finding]) -> None:
        self.db.put_findings(run_id, [f.model_dump() for f in findings])
        for f in findings:
            await self.emit(run_id, {"type": "finding.updated", "finding": f.model_dump()})

    def cancel(self, run_id: str) -> bool:
        t = self.tasks.get(run_id)
        if not t:
            return False
        self.cancelled.add(run_id)
        t.cancel()
        return True

    # ------------------------------------------------------------------ fixes
    def start_fix(self, run_id: str, key: str, model: str = "muse-wonder-1.0", overrides: dict | None = None) -> str:
        run = self.db.run(run_id)
        if not run or run["kind"] != "scan":
            raise RunError("unknown run", 404)
        f = self.db.finding(run_id, key)
        if not f:
            raise RunError("unknown finding for this run", 404)
        if f["status"] != "confirmed":
            raise RunError(f"only confirmed findings can be fixed (this one is {f['status']})", 409)
        if run["config"].get("base_url"):
            raise RunError("this run scanned a bare URL, not a target with source code: there is nothing to fix", 409)
        fix_id = uuid.uuid4().hex[:12]
        self.tasks[fix_id] = asyncio.create_task(self._fix(fix_id, run, Finding(**f), model, overrides or {}))
        return fix_id

    async def _fix(self, fix_id: str, run: dict, f: Finding, model: str, overrides: dict) -> None:
        run_id = run["id"]
        emit = self.emitter(run_id)

        async def fev(ev: dict) -> None:
            await emit({**ev, "fix_id": fix_id})

        conf = self.build_conf(run["config"]["config"], {**run["config"].get("overrides", {}), **{k: v for k, v in overrides.items() if v}})
        route = route_of(f)
        states = matrix_states(route, conf.matrix)
        status = "error"
        try:
            await fev({"type": "fix.started", "key": f.key, "model": model, "states": len(states)})
            if self.fix_lock.locked():
                await fev({"type": "fix.queued", "key": f.key})
            async with self.fix_lock:
                async with await Workspace.open(conf.target, f"api|{run_id}|{f.key}") as ws:
                    await fev({"type": "fix.baseline", "done": 0, "states": len(states)})
                    done = 0

                    async def counted(_: Scanned) -> None:
                        nonlocal done
                        done += 1
                        await fev({"type": "fix.baseline", "done": done, "states": len(states)})

                    # model-free, and no scan events: the baseline must not redraw the scan view
                    base = await scan_states(states, ws.url, self.store, conf.concurrency.browser_contexts, sam=False,
                                             on_state=counted)
                    mine = next((x for x in findings_of(base) if x.key == f.key and x.status == "confirmed"), None)
                    if mine is None:
                        await fev({"type": "fix.error", "error": "this finding does not reproduce on the committed code "
                                   "(the worktree is built from HEAD): nothing to fix"})
                        self.db.put_fix(fix_id, run_id, f.key, "error", {"error": "not reproducible at HEAD"})
                        return
                    mine = mine.model_copy(update={"triage": f.triage})
                    llm = (self.llm_factory or FixLLM)(model, conf.models.fixer_fallback, fev)
                    res = await fix_finding(mine, ws, base, self.store, emit=fev, llm=llm)
                    ti = next((c.tile for r in base for c in r.candidates if candidate_key(r.cap, c) == f.key), 0)
                    before = {r.cap.state.key: r.cap.tiles[min(ti, len(r.cap.tiles) - 1)].png_sha for r in base if r.cap.tiles}
            status = res.status
            payload = {
                "status": res.status, "model": res.model, "summary": res.summary, "diff": res.diff, "turns": res.turns,
                "tokens": res.tokens, "citations": res.citations, "before_shots": before,
                "verification": res.verification.model_dump() if res.verification else None,
                "attempts": [{"model": a.model, "diff": a.diff, "lint_errors": a.lint_errors,
                              "verification": a.verification.model_dump() if a.verification else None} for a in res.attempts],
                "route": route, "states": [s.key for s in states]}
            self.db.put_fix(fix_id, run_id, f.key, res.status, payload)
            await fev({"type": "fix.result", "key": f.key, **payload})
        except asyncio.CancelledError:
            raise
        except Exception as e:
            traceback.print_exc()
            self.db.put_fix(fix_id, run_id, f.key, "error", {"error": str(e)})
            await fev({"type": "fix.error", "error": f"{type(e).__name__}: {str(e)[:600]}"})
        finally:
            self.tasks.pop(fix_id, None)
