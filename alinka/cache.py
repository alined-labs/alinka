"""The response cache every model call goes through.

Key: sha256(model + prompt_hash + input_hash). One JSON file per key under
`cache/responses/`, holding the request summary, the response, tokens, cost, latency
and stop reason. Modes:
- replay: read only; a miss raises `CacheMiss`, which the caller turns into an
  `extraction_error`, so the invoice escalates. Tests and the hub always replay.
- record: a hit is returned; a miss calls the model and writes the file.
- live: like record, for uploads at deploy time.
Jobs choose the mode with `--mode`; the default comes from settings.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from alinka.types import ModelCall

Mode = Literal["record", "replay", "live"]
Role = Literal["reader", "checker", "jev"]
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "cache" / "responses"


class CacheMiss(LookupError):
    """Replay mode found no recording for this request."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cache_key(model: str, prompt_hash: str, input_hash: str) -> str:
    return sha256_text(model + prompt_hash + input_hash)


@dataclass(frozen=True)
class Fresh:
    """What a real model call returns to the cache."""

    response: Any  # JSON-serialisable
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    stop_reason: str | None = None


@dataclass(frozen=True)
class Cached:
    key: str
    model: str
    prompt_hash: str
    response: Any
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int  # of the original call
    stop_reason: str | None
    cached: bool  # True when this came from a recording
    request: dict[str, Any] = field(default_factory=dict)

    def model_call(self, role: Role) -> ModelCall:
        return ModelCall(
            role=role,
            model=self.model,
            prompt_hash=self.prompt_hash,
            cache_key=self.key,
            cached=self.cached,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_usd=self.cost_usd,
            latency_ms=self.latency_ms,
            stop_reason=self.stop_reason,
        )


class ResponseCache:
    def __init__(self, mode: Mode, directory: Path = DEFAULT_DIR) -> None:
        if mode not in ("record", "replay", "live"):
            raise ValueError(f"unknown cache mode {mode!r}")
        self.mode: Mode = mode
        self.directory = directory
        self._memory: dict[str, Cached] = {}
        self._lock = threading.Lock()

    def path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> Cached | None:
        hit = self._memory.get(key)
        if hit is not None:
            return hit
        try:
            raw = json.loads(self.path(key).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        hit = Cached(
            key=key,
            model=raw["model"],
            prompt_hash=raw["prompt_hash"],
            response=raw["response"],
            input_tokens=raw.get("input_tokens", 0),
            output_tokens=raw.get("output_tokens", 0),
            cost_usd=raw.get("cost_usd", 0.0),
            latency_ms=raw.get("latency_ms", 0),
            stop_reason=raw.get("stop_reason"),
            cached=True,
            request=raw.get("request", {}),
        )
        with self._lock:
            self._memory[key] = hit
        return hit

    def call(
        self,
        *,
        model: str,
        prompt_hash: str,
        input_hash: str,
        request: dict[str, Any],
        fn: Callable[[], Fresh],
    ) -> Cached:
        """Return the recording for this request, or (record and live only) make the call."""
        key = cache_key(model, prompt_hash, input_hash)
        hit = self.get(key)
        if hit is not None:
            return hit
        if self.mode == "replay":
            raise CacheMiss(f"no recording for {model} key {key[:12]}")
        start = time.perf_counter()
        fresh = fn()
        latency_ms = round((time.perf_counter() - start) * 1000)
        result = Cached(
            key=key,
            model=model,
            prompt_hash=prompt_hash,
            response=fresh.response,
            input_tokens=fresh.input_tokens,
            output_tokens=fresh.output_tokens,
            cost_usd=fresh.cost_usd,
            latency_ms=latency_ms,
            stop_reason=fresh.stop_reason,
            cached=False,
            request=request,
        )
        self._write(result, input_hash)
        with self._lock:
            self._memory[key] = replace(result, cached=True)
        return result

    def _write(self, result: Cached, input_hash: str) -> None:
        body = {
            "key": result.key,
            "model": result.model,
            "prompt_hash": result.prompt_hash,
            "input_hash": input_hash,
            "request": result.request,
            "response": result.response,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
            "latency_ms": result.latency_ms,
            "stop_reason": result.stop_reason,
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, self.path(result.key))


_caches: dict[tuple[str, Path], ResponseCache] = {}


def get_cache(mode: Mode | None = None, directory: Path = DEFAULT_DIR) -> ResponseCache:
    """One cache per mode and directory; the mode defaults to settings.cache_mode."""
    if mode is None:
        from alinka.settings import get_settings

        mode = get_settings().cache_mode
    key = (mode, directory)
    if key not in _caches:
        _caches[key] = ResponseCache(mode, directory)
    return _caches[key]
