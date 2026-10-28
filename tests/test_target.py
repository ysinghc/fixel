import sys
import urllib.request

import pytest

from fixel.config import Target
from fixel.target import TargetServer, find_vite_config, wait_http


async def test_target_server_starts_serves_and_stops(tmp_path):
    (tmp_path / "index.html").write_text("hello")
    t = Target(path=str(tmp_path), dev_cmd=f"{sys.executable} -m http.server {{port}} --bind 127.0.0.1")
    async with TargetServer(t, timeout=20) as url:
        assert urllib.request.urlopen(url).read() == b"hello"
    with pytest.raises(OSError):
        urllib.request.urlopen(url, timeout=2)               # process group was stopped on exit


async def test_wait_http_times_out_when_nothing_listens():
    with pytest.raises(TimeoutError):
        await wait_http("http://127.0.0.1:9", timeout=1)


def test_find_vite_config(tmp_path):
    assert find_vite_config(tmp_path) is None
    (tmp_path / "vite.config.js").write_text("export default {}")
    assert find_vite_config(tmp_path).name == "vite.config.js"


async def test_failed_start_reports_log_tail_quickly(tmp_path):
    t = Target(name="broken", path=str(tmp_path), dev_cmd="echo 'boom: cannot find module vite'; exit 1")
    with pytest.raises(RuntimeError, match="boom: cannot find module vite"):
        await TargetServer(t, timeout=20).__aenter__()
