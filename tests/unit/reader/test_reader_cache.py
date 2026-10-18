"""The response cache: keys, the three modes, and replay speed."""

from __future__ import annotations

import json
import time

import pytest

from alinka.cache import CacheMiss, Fresh, ResponseCache, cache_key, sha256_text


def _call(cache: ResponseCache, calls: list[int], text: str = "hola"):
    def fn() -> Fresh:
        calls.append(1)
        return Fresh(response={"echo": text}, input_tokens=10, output_tokens=3, cost_usd=0.001,
                     stop_reason="end_turn")  # fmt: skip

    return cache.call(
        model="m-1",
        prompt_hash=sha256_text("prompt"),
        input_hash=sha256_text(text),
        request={"summary": "test"},
        fn=fn,
    )


def test_key_is_sha256_of_model_prompt_and_input():
    assert cache_key("m", "p", "i") == sha256_text("mpi")
    assert cache_key("m", "p", "i") != cache_key("m2", "p", "i")


def test_replay_miss_raises(tmp_path):
    calls: list[int] = []
    with pytest.raises(CacheMiss):
        _call(ResponseCache("replay", tmp_path), calls)
    assert calls == [] and list(tmp_path.iterdir()) == []


def test_record_writes_once_and_replay_reads_it(tmp_path):
    calls: list[int] = []
    first = _call(ResponseCache("record", tmp_path), calls)
    again = _call(ResponseCache("record", tmp_path), calls)
    assert calls == [1] and not first.cached and again.cached
    (path,) = tmp_path.glob("*.json")
    body = json.loads(path.read_text())
    assert path.stem == first.key == body["key"]
    assert body["request"] == {"summary": "test"} and body["response"] == {"echo": "hola"}
    assert body["stop_reason"] == "end_turn" and body["input_tokens"] == 10

    replay = ResponseCache("replay", tmp_path)
    hit = _call(replay, calls)
    assert calls == [1] and hit.cached and hit.response == {"echo": "hola"}
    call = hit.model_call("reader")
    assert call.cached and call.cache_key == first.key and call.cost_usd == 0.001


def test_live_calls_on_miss(tmp_path):
    calls: list[int] = []
    _call(ResponseCache("live", tmp_path), calls, "a")
    _call(ResponseCache("live", tmp_path), calls, "b")
    assert len(calls) == 2


def test_hits_return_in_under_5_ms(tmp_path):
    calls: list[int] = []
    _call(ResponseCache("record", tmp_path), calls)
    replay = ResponseCache("replay", tmp_path)
    start = time.perf_counter()
    _call(replay, calls)  # cold: reads the file
    cold = time.perf_counter() - start
    start = time.perf_counter()
    for _ in range(100):
        _call(replay, calls)
    warm = (time.perf_counter() - start) / 100
    assert cold < 0.005 and warm < 0.005


def test_unknown_mode_is_refused(tmp_path):
    with pytest.raises(ValueError):
        ResponseCache("bogus", tmp_path)  # type: ignore[arg-type]
