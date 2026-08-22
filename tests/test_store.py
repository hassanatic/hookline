from hookline.store import Store


def make_store(tmp_path):
    return Store(str(tmp_path / "t.db"))


def test_first_insert_wins(tmp_path):
    s = make_store(tmp_path)
    assert s.insert_once("evt_1", "stripe", {"n": 1}) is True
    assert s.insert_once("evt_1", "stripe", {"n": 2}) is False
    assert s.get("evt_1").payload == {"n": 1}


def test_status_lifecycle(tmp_path):
    s = make_store(tmp_path)
    s.insert_once("evt_2", "github", {})
    assert s.get("evt_2").status == "received"
    s.set_status("evt_2", "processing")
    s.set_status("evt_2", "done")
    assert s.get("evt_2").status == "done"


def test_attempts_and_dead_letter(tmp_path):
    s = make_store(tmp_path)
    s.insert_once("evt_3", "github", {"x": 1})
    s.record_attempt("evt_3", ok=False, error="boom")
    s.record_attempt("evt_3", ok=False, error="boom again")
    assert s.attempt_count("evt_3") == 2
    s.set_status("evt_3", "dead")
    dead = s.dead_letters()
    assert [e.event_id for e in dead] == ["evt_3"]


def test_missing_event_is_none(tmp_path):
    s = make_store(tmp_path)
    assert s.get("nope") is None
