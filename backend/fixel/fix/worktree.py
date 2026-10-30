"""Isolated workspace per fix session: a git worktree plus a dev server (guide section 7.2).

The user's branch and working tree are never touched. The worktree lives under Fixel's own .fixel/wt/ (not inside the
target repo, which would show up as untracked files there). All file access goes through methods that keep paths inside
the worktree's app directory and out of node_modules, which is a symlink back to the original install.
"""
import asyncio
import fnmatch
import hashlib
import re
import shutil
from pathlib import Path

from ..config import Target
from ..target import TargetServer

WT_ROOT = Path(".fixel/wt")
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".vite", ".fixel"}


class WorkspaceError(Exception): ...


async def sh(*cmd: str, cwd: Path | None = None, stdin: str | None = None, timeout: float = 120) -> tuple[int, str]:
    """Run a command, return (exit code, combined output)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd, stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(stdin.encode() if stdin is not None else None), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"timed out after {timeout}s"
    return proc.returncode, out.decode(errors="replace")


def slug(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", key).strip("-")[:48] + "-" + hashlib.sha1(key.encode()).hexdigest()[:6]


class Workspace:
    def __init__(self, target: Target, repo: Path, rel: Path, path: Path):
        self.target, self.repo, self.rel, self.path = target, repo, rel, path
        self.app = path / rel                                # the app directory inside the worktree
        self.server: TargetServer | None = None
        self.allowed_files: set[str] = set()                  # the localized set the linter allows a patch to touch
        self.url = ""

    # ------------------------------------------------------------------ lifecycle
    @classmethod
    async def open(cls, target: Target, key: str, root: Path = WT_ROOT, serve: bool = True) -> "Workspace":
        app = Path(target.path or ".").resolve()
        code, out = await sh("git", "rev-parse", "--show-toplevel", cwd=app)
        if code:
            raise WorkspaceError(f"{app} is not inside a git repository: {out.strip()}")
        repo = Path(out.strip()).resolve()
        rel = app.relative_to(repo)
        path = (root / target.name / slug(key)).resolve()
        if path.exists():                                    # a leftover from a crashed session
            await sh("git", "worktree", "remove", "--force", str(path), cwd=repo)
            shutil.rmtree(path, ignore_errors=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        code, out = await sh("git", "worktree", "add", "--detach", str(path), "HEAD", cwd=repo)
        if code:
            raise WorkspaceError(f"git worktree add failed: {out.strip()}")
        ws = cls(target, repo, rel, path)
        for nm in {repo / "node_modules", app / "node_modules"}:  # share the installed dependencies, no reinstall
            if nm.is_dir():
                link = path / nm.relative_to(repo)
                if not link.exists():
                    link.symlink_to(nm, target_is_directory=True)
        if serve:
            ws.server = TargetServer(target.model_copy(update={"path": str(ws.app), "name": f"{target.name}-fix"}))
            try:
                ws.url = await ws.server.__aenter__()
            except BaseException:
                await ws.close()
                raise
        return ws

    async def close(self) -> None:
        if self.server:
            await self.server.__aexit__(None, None, None)
            self.server = None
        await sh("git", "worktree", "remove", "--force", str(self.path), cwd=self.repo)
        await sh("git", "worktree", "prune", cwd=self.repo)
        shutil.rmtree(self.path, ignore_errors=True)

    async def __aenter__(self) -> "Workspace":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    # ------------------------------------------------------------------ safe file access
    def resolve(self, rel_path: str) -> Path:
        """An app-relative path inside the worktree, never node_modules, .git or anywhere outside."""
        p = Path(rel_path)
        if p.is_absolute() or ".." in p.parts:
            raise WorkspaceError(f"path must be relative to the app and stay inside it: {rel_path}")
        if set(p.parts) & {"node_modules", ".git"}:
            raise WorkspaceError(f"not editable: {rel_path}")
        full = (self.app / p).resolve()
        if self.app.resolve() not in full.parents and full != self.app.resolve():
            raise WorkspaceError(f"path escapes the workspace: {rel_path}")
        return full

    def read(self, rel_path: str, start: int = 1, end: int = 400) -> str:
        full = self.resolve(rel_path)
        if not full.is_file():
            raise WorkspaceError(f"no such file: {rel_path}")
        lines = full.read_text(errors="replace").splitlines()
        start, end = max(1, start), min(len(lines), max(start, end))
        return "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))

    def search(self, pattern: str, glob: str = "*", limit: int = 40) -> list[str]:
        rx = re.compile(pattern)
        hits: list[str] = []
        for f in sorted(self.app.rglob("*")):
            rel = f.relative_to(self.app)
            if not f.is_file() or SKIP_DIRS & set(rel.parts) or not fnmatch.fnmatch(f.name, glob or "*"):
                continue
            try:
                text = f.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()[:160]}")
                    if len(hits) >= limit:
                        return hits
        return hits

    def edit(self, rel_path: str, old: str, new: str) -> tuple[str | None, str]:
        """Replace exactly one occurrence of `old`. Returns (error for the model or None, the file's previous content)."""
        full = self.resolve(rel_path)
        if not full.is_file():
            return f"no such file: {rel_path}", ""
        text = full.read_text()
        if not old:
            return "old must not be empty", text
        n = text.count(old)
        if n == 0:
            return "old text not found: it must match the file exactly, including whitespace. Read the file again.", text
        if n > 1:
            return f"old text matches {n} places: include more surrounding lines so it matches exactly once.", text
        full.write_text(text.replace(old, new, 1))
        return None, text

    def write_back(self, rel_path: str, content: str) -> None:
        """Undo an edit by restoring the file's earlier content."""
        self.resolve(rel_path).write_text(content)

    # ------------------------------------------------------------------ git
    async def diff(self) -> str:
        """The working tree against HEAD, with paths relative to the app directory (the same paths data-loc reports)."""
        _, out = await sh("git", "diff", "--no-color", "--relative", cwd=self.app)
        return out

    async def reset(self) -> None:
        await sh("git", "checkout", "--", ".", cwd=self.path)           # every attempt starts from HEAD

    async def run(self, cmd: list[str], timeout: float = 240) -> tuple[bool, str]:
        code, out = await sh(*cmd, cwd=self.app, timeout=timeout)
        return code == 0, out
