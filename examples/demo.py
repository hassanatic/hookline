"""End-to-end walkthrough: sign, deliver, duplicate, process, dead-letter.

Runs fully in-process (no server needed):
    ./.venv/bin/python examples/demo.py
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from hookline.app import create_app
from hookline.dispatcher import drain
from hookline.security import sign
from hookline.store import Store

SECRET = b"demo-secret"
store = Store(":memory:")
client = TestClient(create_app(store=store, secret=SECRET))


def deliver(payload: dict) -> None:
    raw = json.dumps(payload).encode()
    ts = int(time.time())
    r = client.post("/webhooks/demo", content=raw, headers={
        "X-Hookline-Timestamp": str(ts),
        "X-Hookline-Signature": sign(SECRET, ts, raw),
        "Content-Type": "application/json"})
    print(f"  -> {r.status_code} {r.json()}")


print("fresh delivery:")
deliver({"id": "evt_1", "kind": "payment.settled"})
print("the sender retries (at-least-once), we deduplicate:")
deliver({"id": "evt_1", "kind": "payment.settled"})
print("a second event that will keep failing:")
deliver({"id": "evt_2", "kind": "always.breaks"})


def handler(event):
    if event.payload["kind"] == "always.breaks":
        raise RuntimeError("downstream is down")


print("drain:", drain(store, handler, max_attempts=3, sleep=lambda s: None))
print("dead letters:", client.get("/dead-letters").json())
print("evt_1 status:", client.get("/events/evt_1").json())
