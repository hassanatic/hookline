"""Deliver stored events to a handler with bounded retries.

The store guarantees an event is persisted exactly once; this module
guarantees it is HANDLED to a terminal state: 'done' on success, 'dead'
after max_attempts failures. Dead letters stay queryable instead of
disappearing into a log line.
"""
from __future__ import annotations

import time
from typing import Callable

from .store import Event, Store

Handler = Callable[[Event], None]


def backoff_s(attempt: int, base: float = 0.5, cap: float = 30.0) -> float:
    """Exponential backoff: 0.5, 1, 2, 4... capped."""
    return min(cap, base * (2 ** (attempt - 1)))


def process(store: Store, event_id: str, handler: Handler,
            *, max_attempts: int = 3, sleep: Callable[[float], None] = time.sleep) -> str:
    """Drive one event to a terminal state. Returns the final status.

    `sleep` is injectable so tests exercise the retry path without waiting.
    """
    event = store.get(event_id)
    if event is None:
        raise KeyError(f"unknown event {event_id!r}")
    if event.status in ("done", "dead"):
        return event.status

    store.set_status(event_id, "processing")
    while True:
        attempt = store.attempt_count(event_id) + 1
        try:
            handler(store.get(event_id))
            store.record_attempt(event_id, ok=True)
            store.set_status(event_id, "done")
            return "done"
        except Exception as exc:
            store.record_attempt(event_id, ok=False, error=repr(exc))
            if attempt >= max_attempts:
                store.set_status(event_id, "dead")
                return "dead"
            sleep(backoff_s(attempt))


def drain(store: Store, handler: Handler, *, max_attempts: int = 3,
          sleep: Callable[[float], None] = time.sleep) -> dict:
    """Process every event still in 'received', oldest first."""
    rows = store._db.execute(
        "SELECT event_id FROM events WHERE status='received' ORDER BY received_at").fetchall()
    out = {"done": 0, "dead": 0}
    for (eid,) in rows:
        out[process(store, eid, handler, max_attempts=max_attempts, sleep=sleep)] += 1
    return out
