import json

import pytest

from fixel.meta import client


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "CACHE", tmp_path / "cache")


async def test_record_mode_stores_then_serves_from_cache(monkeypatch):
    monkeypatch.setenv("FIXEL_MODE", "record")
    calls, events = [], []

    async def fn():
        calls.append(1)
        return {"json": "{}", "usage": {"in": 3}}

    async def emit(ev):
        events.append(ev)

    a = await client.call("spark.triage", {"img": "abc"}, fn, emit)
    b = await client.call("spark.triage", {"img": "abc"}, fn, emit)
    assert a == b and len(calls) == 1
    assert [e["source"] for e in events if e["type"] == "model.call"] == ["live", "cached"]
    assert events[0]["type"] == "model.start"                          # the UI pulses a pill during the call


async def test_replay_never_calls_and_raises_on_miss(monkeypatch):
    monkeypatch.setenv("FIXEL_MODE", "replay")

    async def fn():
        raise AssertionError("replay must not call the model")

    with pytest.raises(client.CacheMiss):
        await client.call("sam.box", {"img": "x"}, fn)


async def test_replay_serves_recorded_answer(monkeypatch):
    monkeypatch.setenv("FIXEL_MODE", "record")

    async def fn():
        return {"raw": "ok"}

    await client.call("sam.box", {"img": "x"}, fn)
    monkeypatch.setenv("FIXEL_MODE", "replay")
    assert (await client.call("sam.box", {"img": "x"}, fn)) == {"raw": "ok"}


async def test_live_mode_bypasses_cache(monkeypatch):
    monkeypatch.setenv("FIXEL_MODE", "live")
    n = []

    async def fn():
        n.append(1)
        return {"n": len(n)}

    await client.call("k", {}, fn)
    assert (await client.call("k", {}, fn)) == {"n": 2}


def test_key_is_order_independent_and_distinguishes_payloads():
    assert client.key_of("k", {"a": 1, "b": 2}) == client.key_of("k", {"b": 2, "a": 1})
    assert client.key_of("k", {"a": 1}) != client.key_of("k", {"a": 2})
    assert client.key_of("k", {"a": 1}) != client.key_of("j", {"a": 1})


def test_bad_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("FIXEL_MODE", "bogus")
    with pytest.raises(ValueError):
        client.mode()


async def test_retry_does_not_resend_a_400():
    import httpx
    from openai import APIStatusError

    n = []

    async def fn():
        n.append(1)
        req = httpx.Request("POST", "http://x")
        raise APIStatusError("bad", response=httpx.Response(400, request=req), body=None)

    with pytest.raises(APIStatusError):
        await client.retry(fn)
    assert len(n) == 1
