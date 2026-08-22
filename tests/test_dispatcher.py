import pytest

from hookline.dispatcher import backoff_s, drain, process
from hookline.store import Store


def make(tmp_path):
    return Store(str(tmp_path / "d.db"))


def test_success_first_try(tmp_path):
    s = make(tmp_path)
    s.insert_once("e1", "src", {"v": 1})
    seen = []
    assert process(s, "e1", lambda ev: seen.append(ev.payload)) == "done"
    assert seen == [{"v": 1}]
    assert s.attempt_count("e1") == 1


def test_retry_then_success(tmp_path):
    s = make(tmp_path)
    s.insert_once("e2", "src", {})
    calls = {"n": 0}
    naps = []

    def flaky(ev):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")

    assert process(s, "e2", flaky, max_attempts=5, sleep=naps.append) == "done"
    assert calls["n"] == 3
    assert naps == [0.5, 1.0]  # exponential, no real sleeping in tests


def test_exhausted_goes_dead(tmp_path):
    s = make(tmp_path)
    s.insert_once("e3", "src", {})

    def always_fail(ev):
        raise RuntimeError("permanent")

    assert process(s, "e3", always_fail, max_attempts=3, sleep=lambda _: None) == "dead"
    assert s.attempt_count("e3") == 3
    assert [e.event_id for e in s.dead_letters()] == ["e3"]


def test_terminal_states_are_not_reprocessed(tmp_path):
    s = make(tmp_path)
    s.insert_once("e4", "src", {})
    process(s, "e4", lambda ev: None)
    assert process(s, "e4", lambda ev: 1 / 0) == "done"  # handler never runs again
    assert s.attempt_count("e4") == 1


def test_drain_processes_all_received(tmp_path):
    s = make(tmp_path)
    for i in range(3):
        s.insert_once(f"b{i}", "src", {})
    out = drain(s, lambda ev: None)
    assert out == {"done": 3, "dead": 0}


def test_backoff_caps():
    assert backoff_s(1) == 0.5
    assert backoff_s(10, cap=30.0) == 30.0
