"""The user's repo is never touched; edits, diffs and cleanup behave (guide 7.2)."""
import subprocess
import sys
import urllib.request

import pytest

from fixel.config import Target
from fixel.fix.worktree import Workspace, WorkspaceError


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, capture_output=True,
                          text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    """A git repo whose app lives in client/ (like the real submodule targets), with a fake node_modules."""
    r = tmp_path / "repo"
    app = r / "client"
    (app / "src").mkdir(parents=True)
    (app / "index.html").write_text("<style>\n.promo { width: 480px; }\n</style>\n<p class=\"promo\">Hello</p>\n")
    (app / "src" / "Card.jsx").write_text('export const Card = () => (\n  <div className="flex">\n    <p>Pay now</p>\n  </div>\n)\n')
    (app / "node_modules" / "dep").mkdir(parents=True)
    (app / "node_modules" / "dep" / "index.js").write_text("module.exports = 1\n")
    (r / ".gitignore").write_text("node_modules\n")
    git(r, "init", "-q")
    git(r, "add", ".")
    git(r, "commit", "-qm", "base")
    return r


def target(repo):
    return Target(name="demo", path=str(repo / "client"), dev_cmd=f"{sys.executable} -m http.server {{port}} --bind 127.0.0.1")


async def test_open_creates_an_isolated_worktree_and_leaves_the_repo_alone(repo, tmp_path):
    async with await Workspace.open(target(repo), "collision|src/Card.jsx:2:3", root=tmp_path / "wt") as ws:
        assert ws.path.is_relative_to(tmp_path / "wt") and (ws.app / "index.html").is_file()
        assert (ws.app / "node_modules").is_symlink() and (ws.app / "node_modules" / "dep" / "index.js").is_file()
        assert urllib.request.urlopen(ws.url).read().startswith(b"<style>")
        assert ws.edit("index.html", "width: 480px", "width: 100%; max-width: 480px")[0] is None
        assert "max-width" in (ws.app / "index.html").read_text()
        assert "480px" in (repo / "client" / "index.html").read_text() and "max-width" not in (repo / "client" / "index.html").read_text()
        assert git(repo, "status", "--porcelain") == ""                      # no .fixel/, no stray files in the user's repo
    assert not ws.path.exists()
    assert str(ws.path) not in git(repo, "worktree", "list")                  # worktree removed and pruned


async def test_dev_server_serves_the_edit(repo, tmp_path):
    async with await Workspace.open(target(repo), "k", root=tmp_path / "wt") as ws:
        ws.edit("index.html", "Hello", "Hello world")
        assert b"Hello world" in urllib.request.urlopen(ws.url).read()


async def test_diff_has_app_relative_paths_and_reset_restores_head(repo, tmp_path):
    async with await Workspace.open(target(repo), "k", root=tmp_path / "wt", serve=False) as ws:
        assert await ws.diff() == ""
        assert ws.edit("src/Card.jsx", 'className="flex"', 'className="flex min-w-0"')[0] is None
        d = await ws.diff()
        assert "--- a/src/Card.jsx" in d and "+++ b/src/Card.jsx" in d and "client/" not in d     # the paths data-loc reports
        assert '+  <div className="flex min-w-0">' in d
        await ws.reset()
        assert await ws.diff() == ""


async def test_edit_errors_guide_the_model_and_nothing_is_written(repo, tmp_path):
    async with await Workspace.open(target(repo), "k", root=tmp_path / "wt", serve=False) as ws:
        err, _ = ws.edit("src/Card.jsx", "does not exist", "x")
        assert "not found" in err
        err, _ = ws.edit("index.html", "o", "0")                               # 'o' occurs many times
        assert "matches" in err and "exactly once" in err
        assert "must not be empty" in ws.edit("index.html", "", "x")[0]
        assert "no such file" in ws.edit("src/Nope.jsx", "a", "b")[0]
        assert await ws.diff() == ""


async def test_edit_returns_previous_content_so_it_can_be_undone(repo, tmp_path):
    async with await Workspace.open(target(repo), "k", root=tmp_path / "wt", serve=False) as ws:
        err, before = ws.edit("index.html", "480px", "100%")
        assert err is None and "480px" in before
        ws.write_back("index.html", before)
        assert await ws.diff() == ""


@pytest.mark.parametrize("bad", ["../repo/client/index.html", "/etc/passwd", "node_modules/dep/index.js", "src/../../x", ".git/config"])
async def test_paths_cannot_escape_or_touch_node_modules(repo, tmp_path, bad):
    async with await Workspace.open(target(repo), "k", root=tmp_path / "wt", serve=False) as ws:
        with pytest.raises(WorkspaceError):
            ws.edit(bad, "a", "b")
        with pytest.raises(WorkspaceError):
            ws.read(bad)
    assert (repo / "client" / "node_modules" / "dep" / "index.js").read_text() == "module.exports = 1\n"


async def test_read_and_search(repo, tmp_path):
    async with await Workspace.open(target(repo), "k", root=tmp_path / "wt", serve=False) as ws:
        assert ws.read("src/Card.jsx", 2, 3) == '2:   <div className="flex">\n3:     <p>Pay now</p>'
        assert ws.search(r"Pay now", "*.jsx") == ["src/Card.jsx:3: <p>Pay now</p>"]
        assert ws.search(r"module\.exports") == []                              # node_modules is never searched


async def test_reopening_the_same_key_replaces_a_stale_worktree(repo, tmp_path):
    a = await Workspace.open(target(repo), "same", root=tmp_path / "wt", serve=False)
    b = await Workspace.open(target(repo), "same", root=tmp_path / "wt", serve=False)   # as after a crash
    assert a.path == b.path and (b.app / "index.html").is_file()
    await b.close()


async def test_run_reports_success_and_failure(repo, tmp_path):
    async with await Workspace.open(target(repo), "k", root=tmp_path / "wt", serve=False) as ws:
        ok, _ = await ws.run([sys.executable, "-c", "print('built')"])
        bad, out = await ws.run([sys.executable, "-c", "import sys; print('boom'); sys.exit(2)"])
        assert ok and not bad and "boom" in out


async def test_not_a_git_repo_is_a_clear_error(tmp_path):
    (tmp_path / "plain").mkdir()
    with pytest.raises(WorkspaceError, match="not inside a git repository"):
        await Workspace.open(Target(name="x", path=str(tmp_path / "plain")), "k", root=tmp_path / "wt", serve=False)
