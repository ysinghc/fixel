"""One door for every model call: disk cache, retries, live/cached labelling.

Modes (FIXEL_MODE): live = always call; record = use cache, call and store on a miss (default);
replay = cache only, a miss raises CacheMiss and spends nothing. See guide section 6.1.
"""
import asyncio
import hashlib
import json
import os
import random
from pathlib import Path

from openai import APIConnectionError, APIStatusError, AsyncOpenAI

CACHE = Path(".fixel/cache")

_client: AsyncOpenAI | None = None


def mode() -> str:
    """Read per call so tests and the UI's replay toggle can change it at runtime."""
    m = os.environ.get("FIXEL_MODE", "record")
    if m not in ("live", "record", "replay"):
        raise ValueError(f"FIXEL_MODE must be live, record or replay, got {m!r}")
    return m


def api_key() -> str:
    """MODEL_API_KEY, or META_MODEL_API (the name some environments store the Meta key under)."""
    for name in ("MODEL_API_KEY", "META_MODEL_API"):
        if os.environ.get(name):
            return os.environ[name]
    raise KeyError("set MODEL_API_KEY (or META_MODEL_API) to call a model live")


def get_client() -> AsyncOpenAI:
    """Created lazily so replay and offline runs need no API key. A local Glimmer server only changes the base URL."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=os.environ.get("MODEL_BASE_URL", "https://api.meta.ai/v1"), api_key=api_key())
    return _client


class CacheMiss(Exception): ...
class EmptyOutput(Exception): ...                       # Spark returned nothing: retryable


def key_of(kind: str, payload: dict) -> str:
    blob = json.dumps({"kind": kind, **payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


async def call(kind: str, payload: dict, fn, emit=None) -> dict:
    """payload holds image SHAs, never image bytes, so keys stay small and stable."""
    m = mode()
    path = CACHE / kind / f"{key_of(kind, payload)}.json"
    if m != "live" and path.exists():
        out, src = json.loads(path.read_text()), "cached"
    elif m == "replay":
        raise CacheMiss(path.name)                       # replay never spends credits
    else:
        if emit:                                         # lets the UI pulse a model pill while the call is in flight
            await emit({"type": "model.start", "kind": kind, "model": payload.get("model")})
        out, src = await retry(fn), "live"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out))
    if emit:
        await emit({"type": "model.call", "kind": kind, "model": payload.get("model"), "source": src, "usage": out.get("usage")})
    return out


async def retry(fn, attempts: int = 4):
    for i in range(attempts):
        try:
            return await fn()
        except APIStatusError as e:
            if e.status_code < 500 and e.status_code not in (408, 409, 429):
                raise                                    # a 400 is permanent: fix the request, never resend it
        except (APIConnectionError, EmptyOutput):
            pass
        await asyncio.sleep(min(8.0, 0.5 * 2 ** i) + random.random() * 0.3)
    return await fn()
