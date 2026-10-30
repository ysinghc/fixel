"""REST + server-sent events (guide section 8.3).

One long-lived event stream per run; every event is already in SQLite when it is sent, so a late or reconnecting client
replays history first (`?after=<seq>`, or the browser's Last-Event-ID) and never misses or repeats an event.
"""
import asyncio
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..bench.labelling import QUESTION, blind_items, list_runs as list_bench_runs, queue
from ..bench.metrics import LABELS, compute as bench_metrics_of, put_label as put_bench_label
from ..env import load_dotenv
from ..meta import client as meta
from ..scan import models_available
from ..store import ArtifactStore
from .db import DB
from .runs import DEFAULT_BUDGET_USD, RunError, RunManager

SHA = re.compile(r"^[0-9a-f]{64}$")


class ScanRequest(BaseModel):
    config: str = "fixel.yaml"
    routes: list[str] | None = None
    widths: list[int] | None = None
    themes: list[str] | None = None
    stress: list[str] | None = None
    height: int | None = None
    models: bool = True
    base_url: str | None = Field(None, description="scan an already running URL instead of the target (nothing can be fixed)")


class FixRequest(BaseModel):
    run_id: str
    key: str
    model: str = "muse-wonder-1.0"
    widths: list[int] | None = None
    themes: list[str] | None = None
    stress: list[str] | None = None


class BenchLabel(BaseModel):
    case_id: str
    label: str


class LabelRequest(BaseModel):
    run_id: str
    key: str
    label: str
    note: str = ""


def create_app(root: Path | str = ".", db_path: Path | str | None = None, store_root: Path | str | None = None,
               config_roots: list[Path] | None = None, llm_factory=None, budget_usd: float = DEFAULT_BUDGET_USD,
               web_dist: Path | str | None = None, bench_root: Path | str | None = None) -> FastAPI:
    root = Path(root).resolve()
    mgr = RunManager(DB(db_path or root / ".fixel" / "fixel.db"), ArtifactStore(store_root or root / ".fixel" / "artifacts"),
                     root, config_roots, llm_factory, budget_usd)
    app = FastAPI(title="Fixel", version="0.1")
    app.state.mgr = mgr

    @app.exception_handler(RunError)
    async def run_error(_: Request, e: RunError):
        return JSONResponse({"detail": str(e)}, status_code=e.status)

    # ------------------------------------------------------------------ config and targets
    @app.get("/api/config")
    def get_config():
        return {"mode": meta.mode(), "models_available": models_available(), "budget_usd": mgr.budget_usd}

    @app.get("/api/targets")
    def get_targets():
        return mgr.targets()

    # ------------------------------------------------------------------ scans and runs
    @app.post("/api/scans")
    async def start_scan(req: ScanRequest):
        return {"run_id": mgr.start_scan(req.model_dump())}

    @app.get("/api/runs")
    def list_runs():
        return mgr.db.runs()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        run = mgr.db.run(run_id)
        if not run:
            raise HTTPException(404, "unknown run")
        return {**run, "findings": mgr.db.findings(run_id), "fixes": mgr.db.fixes(run_id), "labels": mgr.db.labels(run_id),
                "total_usd": round(mgr.cost.get(run_id, 0.0), 6), "active": run_id in mgr.tasks}

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id: str):
        if not mgr.cancel(run_id):
            raise HTTPException(409, "this run is not running")
        return {"cancelled": True}

    @app.get("/api/runs/{run_id}/states/{state_key:path}")
    def get_state(run_id: str, state_key: str):
        """Everything about one rendered state: tiles with their DOM elements, candidates and pixel evidence."""
        cap = mgr.db.capture(run_id, state_key)
        if not cap:
            raise HTTPException(404, "unknown state")
        return cap

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, request: Request, after: int = 0, follow: bool = True):
        if not mgr.db.run(run_id):
            raise HTTPException(404, "unknown run")
        after = max(after, int(request.headers.get("last-event-id") or 0))
        q = mgr.subscribe(run_id) if follow else None            # subscribe BEFORE reading history: no gap

        async def gen():
            last = after
            try:
                for ev in mgr.db.events(run_id, after):
                    last = ev["seq"]
                    yield f"id: {ev['seq']}\ndata: {json.dumps(ev)}\n\n"
                if not follow:
                    return
                while not await request.is_disconnected():
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    if ev["seq"] > last:                           # drop events already sent from history
                        last = ev["seq"]
                        yield f"id: {ev['seq']}\ndata: {json.dumps(ev)}\n\n"
            finally:
                if q is not None:
                    mgr.unsubscribe(run_id, q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------------ findings and fixes
    @app.get("/api/findings/{key:path}")
    def get_finding(key: str, run_id: str):
        f = mgr.db.finding(run_id, key)
        if not f:
            raise HTTPException(404, "unknown finding")
        return {**f, "fixes": [x for x in mgr.db.fixes(run_id) if x["key"] == key],
                "label": next((x for x in mgr.db.labels(run_id) if x["key"] == key), None)}

    @app.post("/api/fix")
    async def start_fix(req: FixRequest):
        fix_id = mgr.start_fix(req.run_id, req.key, req.model, {"widths": req.widths, "themes": req.themes, "stress": req.stress})
        return {"fix_id": fix_id, "run_id": req.run_id}

    @app.get("/api/fixes/{fix_id}")
    def get_fix(fix_id: str):
        fx = mgr.db.fix(fix_id)
        if not fx:
            raise HTTPException(404, "unknown fix")
        return fx

    @app.get("/api/fixes/{fix_id}/patch")
    def get_patch(fix_id: str):
        """The patch as a file, offered only when the verifier passed it: nothing else is shown as fixed."""
        fx = mgr.db.fix(fix_id)
        if not fx:
            raise HTTPException(404, "unknown fix")
        if fx["status"] != "verified":
            raise HTTPException(409, f"this fix is {fx['status']}, not verified: no patch is exported")
        name = re.sub(r"[^A-Za-z0-9]+", "-", fx["key"]).strip("-")[:60] + ".patch"
        return PlainTextResponse(fx["diff"], headers={"Content-Disposition": f'attachment; filename="{name}"'},
                                 media_type="text/x-diff")

    # ------------------------------------------------------------------ labels (the benchmark's human ground truth)
    @app.post("/api/labels")
    def put_label(req: LabelRequest):
        if req.label not in LABELS:
            raise HTTPException(422, f"label must be one of {LABELS}")
        if not mgr.db.finding(req.run_id, req.key):
            raise HTTPException(404, "unknown finding")
        mgr.db.put_label(req.run_id, req.key, req.label, req.note)
        return {"ok": True}

    @app.get("/api/labels")
    def get_labels(run_id: str):
        return mgr.db.labels(run_id)

    # ------------------------------------------------------------------ artifacts
    @app.get("/api/artifacts/{sha}")
    def artifact(sha: str):
        if not SHA.match(sha):
            raise HTTPException(400, "not a content hash")
        p = mgr.store.path(sha)
        if not p.is_file():
            raise HTTPException(404, "no such artifact")
        return FileResponse(p, media_type="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})

    # ------------------------------------------------------------------ not built yet: say so plainly
    @app.post("/api/voice")
    def voice():
        raise HTTPException(501, "voice intake is not built yet")

    # ------------------------------------------------------------------ the benchmark (measured results only; see bench/metrics.py)
    bench_root = Path(bench_root) if bench_root else root / ".fixel" / "bench"

    def bench_run(run: str) -> Path:
        d = (bench_root / run).resolve()
        if "/" in run or not (d / "meta.json").is_file() or bench_root.resolve() not in d.parents:
            raise HTTPException(404, "unknown benchmark run")
        return d

    @app.get("/api/bench")
    def bench():
        runs = list_bench_runs(bench_root)
        return {"available": bool(runs), "runs": runs,
                "reason": None if runs else "no benchmark has been run yet: `fixel bench run --split dev` writes one"}

    @app.get("/api/bench/{run}")
    def bench_metrics(run: str):
        return bench_metrics_of(bench_run(run))

    @app.get("/api/bench/{run}/queue")
    def bench_queue(run: str):
        """The labelling queue, blind: no operator, no kind (mutated or clean) and no detection results."""
        d = bench_run(run)
        items = blind_items(d)
        return {"run": run, "split": json.loads((d / "meta.json").read_text()).get("split"), "question": QUESTION, "items": items,
                "done": sum(i["label"] is not None for i in items)}

    @app.put("/api/bench/{run}/labels")
    def bench_label(run: str, req: BenchLabel):
        d = bench_run(run)
        if req.case_id not in queue(d):
            raise HTTPException(404, "that case is not in this run's labelling queue")
        if req.label not in LABELS:
            raise HTTPException(422, f"label must be one of {LABELS}")
        put_bench_label(d, req.case_id, req.label)
        return {"ok": True}

    # ------------------------------------------------------------------ the built UI, if there is one
    dist = Path(web_dist) if web_dist else root / "web" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app


def app_from_env() -> FastAPI:
    """uvicorn --factory entry point: reads .env, serves the repo it is started in."""
    load_dotenv()
    return create_app(".")
