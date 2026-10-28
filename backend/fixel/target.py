"""Start and stop the target app's dev server for a scan (guide sections 2 and 7.1).

Vite targets are run through tooling/vite.config.fixel.mjs, a wrapper that loads the target's own
config and prepends the data-loc plugin, so the target's files are never edited.
"""
import asyncio
import os
import signal
import socket
import urllib.error
import urllib.request
from pathlib import Path

from .config import Target

FIXEL_HOME = Path(__file__).resolve().parents[2]
VITE_CONFIGS = ("vite.config.ts", "vite.config.mts", "vite.config.js", "vite.config.mjs")

# Default for targets that do not set dev_cmd: a Vite app run through the data-loc wrapper config.
DEFAULT_VITE_CMD = "npx vite --config {fixel_home}/tooling/vite.config.fixel.mjs --port {port} --strictPort"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_vite_config(root: Path) -> Path | None:
    return next((root / n for n in VITE_CONFIGS if (root / n).exists()), None)


async def wait_http(url: str, timeout: float = 90, alive=lambda: True) -> None:
    """Poll until url answers. alive() lets the caller stop early when the server process has already exited."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if not alive():
            raise ProcessLookupError("the dev server process exited before it started listening")
        try:
            await asyncio.to_thread(urllib.request.urlopen, url, None, 2)
            return
        except urllib.error.HTTPError:
            return                                          # the server answered, even if with a 404
        except OSError:
            if loop.time() > deadline:
                raise TimeoutError(f"{url} did not come up within {timeout}s")
            await asyncio.sleep(0.3)


class TargetServer:
    """async with TargetServer(target) as base_url: ... starts target.dev_cmd and stops its process group on exit."""

    def __init__(self, target: Target, timeout: float = 90):
        self.target, self.timeout, self.proc = target, timeout, None

    async def __aenter__(self) -> str:
        t = self.target
        root = Path(t.path or ".").resolve()
        port = free_port()
        cmd = (t.dev_cmd or DEFAULT_VITE_CMD).format(port=port, fixel_home=FIXEL_HOME)
        env = {**os.environ, "FIXEL": "1", "FIXEL_HOME": str(FIXEL_HOME), **t.env}
        cfg = find_vite_config(root)
        if cfg and "FIXEL_TARGET_CONFIG" not in env:
            env["FIXEL_TARGET_CONFIG"] = str(cfg)
        self.log = Path(".fixel/logs") / f"{t.name}.log"
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("wb") as out:
            self.proc = await asyncio.create_subprocess_shell(
                cmd, cwd=root, env=env, start_new_session=True, stdout=out, stderr=asyncio.subprocess.STDOUT)
        url = f"http://127.0.0.1:{port}"
        try:
            await wait_http(url, self.timeout, alive=lambda: self.proc.returncode is None)
        except BaseException as e:
            await self.__aexit__(None, None, None)
            if isinstance(e, (TimeoutError, ProcessLookupError)):
                tail = "\n".join(self.log.read_text(errors="replace").splitlines()[-15:])
                hint = "" if (root / "node_modules").exists() else f"\n(no node_modules in {root}: run `make targets`)"
                raise RuntimeError(f"{t.name} dev server failed: {e}{hint}\n--- {self.log}\n{tail}") from e
            raise
        return url

    async def __aexit__(self, *exc):
        if self.proc and self.proc.returncode is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)    # the shell and the dev server under it
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self.proc.wait(), 10)
            except asyncio.TimeoutError:
                os.killpg(self.proc.pid, signal.SIGKILL)
