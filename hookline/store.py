"""SQLite persistence: idempotency, event log, delivery attempts, dead letters.

Webhooks are delivered at-least-once by every serious sender, so the receiver
owns deduplication. The event id is the idempotency key: the first insert wins
and every later duplicate is acknowledged without reprocessing.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    received_at REAL NOT NULL,
    payload     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'received'
        CHECK (status IN ('received', 'processing', 'done', 'dead'))
);
CREATE TABLE IF NOT EXISTS attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id   TEXT NOT NULL REFERENCES events(event_id),
    started_at REAL NOT NULL,
    ok         INTEGER NOT NULL,
    error      TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
"""


@dataclass(frozen=True)
class Event:
    event_id: str
    source: str
    payload: dict
    status: str


class Store:
    def __init__(self, path: str = "hookline.db") -> None:
        # check_same_thread=False: the web layer serves from worker threads while
        # tests and the dispatcher hold the same connection. SQLite serialises
        # writes itself, and this store issues short, committed statements only.
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def insert_once(self, event_id: str, source: str, payload: dict) -> bool:
        """True if this is the first delivery; False for a duplicate."""
        try:
            self._db.execute(
                "INSERT INTO events (event_id, source, received_at, payload) VALUES (?,?,?,?)",
                (event_id, source, time.time(), json.dumps(payload)),
            )
            self._db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get(self, event_id: str) -> Event | None:
        row = self._db.execute(
            "SELECT event_id, source, payload, status FROM events WHERE event_id=?",
            (event_id,)).fetchone()
        if not row:
            return None
        return Event(row[0], row[1], json.loads(row[2]), row[3])

    def set_status(self, event_id: str, status: str) -> None:
        self._db.execute("UPDATE events SET status=? WHERE event_id=?", (status, event_id))
        self._db.commit()

    def record_attempt(self, event_id: str, ok: bool, error: str | None = None) -> None:
        self._db.execute(
            "INSERT INTO attempts (event_id, started_at, ok, error) VALUES (?,?,?,?)",
            (event_id, time.time(), int(ok), error))
        self._db.commit()

    def attempt_count(self, event_id: str) -> int:
        return self._db.execute(
            "SELECT COUNT(*) FROM attempts WHERE event_id=?", (event_id,)).fetchone()[0]

    def dead_letters(self) -> list[Event]:
        rows = self._db.execute(
            "SELECT event_id, source, payload, status FROM events WHERE status='dead'").fetchall()
        return [Event(r[0], r[1], json.loads(r[2]), r[3]) for r in rows]

    def close(self) -> None:
        self._db.close()
