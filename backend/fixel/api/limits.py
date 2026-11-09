"""Rate limits and spend caps for a public deployment (`fixel serve --public`, or FIXEL_PUBLIC=1).

Everything here is deterministic code, not policy text: a request is either allowed or answered with 429/403 and a plain
reason. The limits protect the Meta model API key, whose spend is the only real cost of a public instance:

- per client IP, sliding windows: all API requests, scans that call models, scans without models, and fix sessions;
- one run (scan or fix) at a time on the whole server, since each one drives a browser and a dev server;
- a daily USD cap over all live model calls, persisted so a restart does not reset it. When it is reached, running work
  stops starting new model calls (the per-run budget mechanism) and new model work is refused until the next UTC day;
- public mode also refuses to scan arbitrary URLs (`base_url`: the server would fetch any address it is given) and
  refuses label writes, which are the benchmark's ground truth and come only from the labeller's own machine.
"""
import json
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Limits:
    requests_per_minute: int = 240         # every /api request, per IP (SSE reconnects and images included)
    model_scans_per_hour: int = 3          # scans with SAM + Spark, per IP
    scans_per_hour: int = 12               # scans without models (free, but each one runs a browser), per IP
    fixes_per_hour: int = 2                # Wonder fix sessions, per IP
    daily_usd: float = 5.0                 # all live model calls on the server, per UTC day
    run_budget_usd: float = 1.0            # one run's model spend (the per-run cap the server already enforces)
    max_active_runs: int = 1               # scans and fixes running at once, server-wide
    trust_proxy: bool = False              # take the client IP from X-Forwarded-For (only behind a proxy you control)

    @classmethod
    def from_env(cls) -> "Limits":
        d = cls()
        return cls(
            requests_per_minute=int(_env_float("FIXEL_RPM", d.requests_per_minute)),
            model_scans_per_hour=int(_env_float("FIXEL_MODEL_SCANS_PER_HOUR", d.model_scans_per_hour)),
            scans_per_hour=int(_env_float("FIXEL_SCANS_PER_HOUR", d.scans_per_hour)),
            fixes_per_hour=int(_env_float("FIXEL_FIXES_PER_HOUR", d.fixes_per_hour)),
            daily_usd=_env_float("FIXEL_DAILY_USD", d.daily_usd),
            run_budget_usd=_env_float("FIXEL_RUN_BUDGET_USD", d.run_budget_usd),
            max_active_runs=int(_env_float("FIXEL_MAX_ACTIVE_RUNS", d.max_active_runs)),
            trust_proxy=os.environ.get("FIXEL_TRUST_PROXY", "") in ("1", "true", "yes"),
        )


class Limited(Exception):
    def __init__(self, message: str, status: int = 429, retry_after: int | None = None):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after


@dataclass
class Window:
    """A sliding-window counter per key."""
    limit: int
    seconds: float
    hits: dict[str, deque] = field(default_factory=lambda: defaultdict(deque))

    def check(self, key: str, now: float) -> int | None:
        """Seconds until the next allowed hit, or None if this one is allowed (and is then counted)."""
        q = self.hits[key]
        while q and q[0] <= now - self.seconds:
            q.popleft()
        if len(q) >= self.limit:
            return max(1, int(q[0] + self.seconds - now) + 1)
        q.append(now)
        return None

    def undo(self, key: str) -> None:
        if self.hits[key]:
            self.hits[key].pop()


class Spend:
    """Live model spend per UTC day, written through to a small JSON file."""

    def __init__(self, path: Path):
        self.path, self.lock = Path(path), threading.Lock()
        try:
            self.days: dict[str, float] = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.days = {}

    @staticmethod
    def today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def add(self, usd: float) -> float:
        with self.lock:
            day = self.today()
            self.days = {day: self.days.get(day, 0.0) + usd}           # only today matters
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.days))
            tmp.replace(self.path)
            return self.days[day]

    def spent_today(self) -> float:
        return self.days.get(self.today(), 0.0)


def seconds_to_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    return int(86400 - (now.hour * 3600 + now.minute * 60 + now.second))


class Limiter:
    def __init__(self, limits: Limits, spend_path: Path, clock=time.monotonic):
        self.limits, self.clock = limits, clock
        self.spend = Spend(spend_path)
        self.requests = Window(limits.requests_per_minute, 60)
        self.model_scans = Window(limits.model_scans_per_hour, 3600)
        self.scans = Window(limits.scans_per_hour, 3600)
        self.fixes = Window(limits.fixes_per_hour, 3600)

    def client_ip(self, headers, peer: str | None) -> str:
        if self.limits.trust_proxy:
            fwd = headers.get("x-forwarded-for") or headers.get("x-real-ip")
            if fwd:
                return fwd.split(",")[0].strip()
        return peer or "unknown"

    def request(self, ip: str) -> None:
        wait = self.requests.check(ip, self.clock())
        if wait:
            raise Limited(f"too many requests: at most {self.limits.requests_per_minute} a minute", retry_after=wait)

    def budget_left(self) -> float:
        return max(0.0, self.limits.daily_usd - self.spend.spent_today())

    def start(self, kind: str, ip: str, models: bool, active_runs: int) -> None:
        """Called before a scan or fix starts. Raises Limited with the reason if it may not."""
        if active_runs >= self.limits.max_active_runs:
            raise Limited("another scan or fix is running on this server; try again in a minute", retry_after=60)
        if models and self.budget_left() <= 0:
            raise Limited(f"today's model budget (${self.limits.daily_usd:.2f}) is used up; "
                          + ("a quick check without models still works" if kind == "scan" else "fixes resume tomorrow (UTC)"),
                          retry_after=seconds_to_utc_midnight())
        win, what = ((self.fixes, f"{self.limits.fixes_per_hour} fixes") if kind == "fix" else
                     (self.model_scans, f"{self.limits.model_scans_per_hour} full checks") if models else
                     (self.scans, f"{self.limits.scans_per_hour} quick checks"))
        wait = win.check(ip, self.clock())
        if wait:
            raise Limited(f"at most {what} an hour from one address; try again in {max(1, wait // 60)} min", retry_after=wait)

    def status(self) -> dict:
        lim = self.limits
        return {"daily_usd": lim.daily_usd, "spent_today_usd": round(self.spend.spent_today(), 4),
                "model_scans_per_hour": lim.model_scans_per_hour, "scans_per_hour": lim.scans_per_hour,
                "fixes_per_hour": lim.fixes_per_hour, "run_budget_usd": lim.run_budget_usd}
