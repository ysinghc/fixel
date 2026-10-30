"""SQLite store for runs, their durable event log, captures, findings, fixes and human labels.

Every event is written here with a per-run sequence number BEFORE it is broadcast, so a client that connects late or
reconnects replays history first and never misses or repeats an event (guide section 8.3). The UI is a pure function of
the event log, which is also what makes a recorded run replayable.
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL,
  config TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS events (
  run_id TEXT NOT NULL, seq INTEGER NOT NULL, ts REAL NOT NULL, json TEXT NOT NULL, PRIMARY KEY (run_id, seq));
CREATE TABLE IF NOT EXISTS captures (
  run_id TEXT NOT NULL, state_key TEXT NOT NULL, json TEXT NOT NULL, PRIMARY KEY (run_id, state_key));
CREATE TABLE IF NOT EXISTS findings (
  run_id TEXT NOT NULL, key TEXT NOT NULL, json TEXT NOT NULL, PRIMARY KEY (run_id, key));
CREATE TABLE IF NOT EXISTS fixes (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, key TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS labels (
  run_id TEXT NOT NULL, key TEXT NOT NULL, label TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', ts REAL NOT NULL,
  PRIMARY KEY (run_id, key));
"""


class DB:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(SCHEMA)

    def q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def x(self, sql: str, args: tuple = ()) -> None:
        with self.lock:
            self.conn.execute(sql, args)

    # ------------------------------------------------------------------ runs
    def create_run(self, kind: str, config: dict, run_id: str | None = None) -> str:
        rid = run_id or uuid.uuid4().hex[:12]
        self.x("INSERT INTO runs (id, kind, created, status, config) VALUES (?,?,?,?,?)",
               (rid, kind, time.time(), "running", json.dumps(config)))
        return rid

    def set_run(self, run_id: str, status: str | None = None, summary: dict | None = None) -> None:
        if status is not None:
            self.x("UPDATE runs SET status=? WHERE id=?", (status, run_id))
        if summary is not None:
            self.x("UPDATE runs SET summary=? WHERE id=?", (json.dumps(summary), run_id))

    def run(self, run_id: str) -> dict | None:
        rows = self.q("SELECT * FROM runs WHERE id=?", (run_id,))
        return self._run(rows[0]) if rows else None

    def runs(self, limit: int = 30) -> list[dict]:
        return [self._run(r) for r in self.q("SELECT * FROM runs ORDER BY created DESC LIMIT ?", (limit,))]

    @staticmethod
    def _run(r) -> dict:
        return {"id": r["id"], "kind": r["kind"], "created": r["created"], "status": r["status"],
                "config": json.loads(r["config"]), "summary": json.loads(r["summary"])}

    # ------------------------------------------------------------------ events
    def append_event(self, run_id: str, ev: dict) -> dict:
        """Persist first, then return the event with its sequence number and timestamp."""
        with self.lock:
            seq = self.conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
            ev = {**ev, "seq": seq, "ts": round(time.time(), 3)}
            self.conn.execute("INSERT INTO events (run_id, seq, ts, json) VALUES (?,?,?,?)",
                              (run_id, seq, ev["ts"], json.dumps(ev)))
        return ev

    def events(self, run_id: str, after: int = 0) -> list[dict]:
        return [json.loads(r["json"]) for r in
                self.q("SELECT json FROM events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after))]

    # ------------------------------------------------------------------ captures, findings
    def put_capture(self, run_id: str, state_key: str, data: dict) -> None:
        self.x("INSERT OR REPLACE INTO captures (run_id, state_key, json) VALUES (?,?,?)", (run_id, state_key, json.dumps(data)))

    def capture(self, run_id: str, state_key: str) -> dict | None:
        rows = self.q("SELECT json FROM captures WHERE run_id=? AND state_key=?", (run_id, state_key))
        return json.loads(rows[0]["json"]) if rows else None

    def put_findings(self, run_id: str, findings: list[dict]) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM findings WHERE run_id=?", (run_id,))
            self.conn.executemany("INSERT INTO findings (run_id, key, json) VALUES (?,?,?)",
                                  [(run_id, f["key"], json.dumps(f)) for f in findings])

    def findings(self, run_id: str) -> list[dict]:
        return [json.loads(r["json"]) for r in self.q("SELECT json FROM findings WHERE run_id=?", (run_id,))]

    def finding(self, run_id: str, key: str) -> dict | None:
        rows = self.q("SELECT json FROM findings WHERE run_id=? AND key=?", (run_id, key))
        return json.loads(rows[0]["json"]) if rows else None

    # ------------------------------------------------------------------ fixes, labels
    def put_fix(self, fix_id: str, run_id: str, key: str, status: str, data: dict) -> None:
        self.x("INSERT OR REPLACE INTO fixes (id, run_id, key, created, status, json) VALUES (?,?,?,?,?,?)",
               (fix_id, run_id, key, time.time(), status, json.dumps(data)))

    def fix(self, fix_id: str) -> dict | None:
        rows = self.q("SELECT * FROM fixes WHERE id=?", (fix_id,))
        return {**json.loads(rows[0]["json"]), "id": rows[0]["id"], "run_id": rows[0]["run_id"],
                "key": rows[0]["key"], "status": rows[0]["status"]} if rows else None

    def fixes(self, run_id: str) -> list[dict]:
        return [{**json.loads(r["json"]), "id": r["id"], "run_id": r["run_id"], "key": r["key"], "status": r["status"]}
                for r in self.q("SELECT * FROM fixes WHERE run_id=? ORDER BY created", (run_id,))]

    def put_label(self, run_id: str, key: str, label: str, note: str = "") -> None:
        self.x("INSERT OR REPLACE INTO labels (run_id, key, label, note, ts) VALUES (?,?,?,?,?)",
               (run_id, key, label, note, time.time()))

    def labels(self, run_id: str) -> list[dict]:
        return [dict(r) for r in self.q("SELECT run_id, key, label, note, ts FROM labels WHERE run_id=?", (run_id,))]
