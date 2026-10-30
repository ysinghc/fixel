"""Shared test helpers: a real uvicorn server on a free port, and a scripted stand-in for the fix model."""
import json
import subprocess
import threading
import time

import httpx
import uvicorn


class Live:
    def __init__(self, app):
        self.app = app
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                break
            time.sleep(0.05)
        self.url = f"http://127.0.0.1:{self.server.servers[0].sockets[0].getsockname()[1]}"
        self.http = httpx.Client(base_url=self.url, timeout=60)
        return self

    def __exit__(self, *exc):
        self.http.close()
        self.server.should_exit = True
        self.thread.join(timeout=10)

    def events(self, run_id, after=0):
        r = self.http.get(f"/api/runs/{run_id}/events", params={"after": after, "follow": "false"})
        r.raise_for_status()
        return [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]

    def wait(self, run_id, type_, timeout=180, key=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for ev in self.events(run_id):
                if ev["type"] == type_ and (key is None or ev.get("key") == key):
                    return ev
            time.sleep(0.4)
        raise AssertionError(f"no {type_} event within {timeout}s; got {[e['type'] for e in self.events(run_id)][-8:]}")




class Scripted:
    """A scripted stand-in for the fix model (same interface as FixLLM): each step is a list of (tool, args) calls."""

    def __init__(self, steps, model="scripted"):
        self.steps, self.model, self.tokens = list(steps), model, 0

    async def turn(self, items):
        step = self.steps.pop(0)
        return [{"type": "function_call", "call_id": f"c{len(self.steps)}_{i}", "name": n, "arguments": json.dumps(a)}
                for i, (n, a) in enumerate(step)]


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)
