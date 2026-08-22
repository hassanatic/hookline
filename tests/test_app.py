import json
import time

from fastapi.testclient import TestClient

from hookline.app import create_app
from hookline.security import sign
from hookline.store import Store

SECRET = b"app-secret"


def make_client(tmp_path):
    store = Store(str(tmp_path / "a.db"))
    return TestClient(create_app(store=store, secret=SECRET)), store


def post(client, body: dict, ts: int | None = None, sig: str | None = None):
    raw = json.dumps(body).encode()
    ts = int(time.time()) if ts is None else ts
    sig = sign(SECRET, ts, raw) if sig is None else sig
    return client.post("/webhooks/stripe", content=raw,
                       headers={"X-Hookline-Timestamp": str(ts),
                                "X-Hookline-Signature": sig,
                                "Content-Type": "application/json"})


def test_fresh_delivery_202(tmp_path):
    client, _ = make_client(tmp_path)
    r = post(client, {"id": "evt_a", "type": "ping"})
    assert r.status_code == 202
    assert r.json() == {"event_id": "evt_a", "duplicate": False}


def test_duplicate_delivery_200_not_reprocessed(tmp_path):
    client, store = make_client(tmp_path)
    post(client, {"id": "evt_b", "n": 1})
    r = post(client, {"id": "evt_b", "n": 2})
    assert r.status_code == 200
    assert r.json()["duplicate"] is True
    assert store.get("evt_b").payload["n"] == 1


def test_bad_signature_401(tmp_path):
    client, _ = make_client(tmp_path)
    r = post(client, {"id": "evt_c"}, sig="0" * 64)
    assert r.status_code == 401


def test_stale_timestamp_401(tmp_path):
    client, _ = make_client(tmp_path)
    r = post(client, {"id": "evt_d"}, ts=int(time.time()) - 9000)
    assert r.status_code == 401


def test_body_without_id_422(tmp_path):
    client, _ = make_client(tmp_path)
    r = post(client, {"noid": True})
    assert r.status_code == 422


def test_status_and_dead_letter_endpoints(tmp_path):
    client, store = make_client(tmp_path)
    post(client, {"id": "evt_e"})
    assert client.get("/events/evt_e").json()["status"] == "received"
    store.set_status("evt_e", "dead")
    assert client.get("/dead-letters").json() == [{"event_id": "evt_e", "source": "stripe"}]
    assert client.get("/events/missing").status_code == 404
