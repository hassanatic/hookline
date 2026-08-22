"""FastAPI receiver: authenticate, deduplicate, acknowledge fast.

The receive path does no business work. It verifies the signature, stores the
event exactly once, and acknowledges - processing happens via the dispatcher,
so a slow handler can never make the sender time out and redeliver.
"""
from __future__ import annotations

import json
import os

from fastapi import FastAPI, Header, HTTPException, Request, Response

from .security import SignatureError, verify
from .store import Store


def create_app(store: Store | None = None, secret: bytes | None = None) -> FastAPI:
    app = FastAPI(title="hookline")
    app.state.store = store or Store(os.environ.get("HOOKLINE_DB", "hookline.db"))
    app.state.secret = secret or os.environ.get("HOOKLINE_SECRET", "").encode()

    @app.post("/webhooks/{source}")
    async def receive(source: str, request: Request, response: Response,
                      x_hookline_timestamp: int = Header(...),
                      x_hookline_signature: str = Header(...)) -> dict:
        body = await request.body()
        try:
            verify(app.state.secret, x_hookline_timestamp, body, x_hookline_signature)
        except SignatureError as e:
            raise HTTPException(status_code=401, detail=str(e))
        try:
            payload = json.loads(body)
            event_id = payload["id"]
        except (json.JSONDecodeError, KeyError, TypeError):
            raise HTTPException(status_code=422, detail="body must be JSON with an 'id'")
        fresh = app.state.store.insert_once(event_id, source, payload)
        response.status_code = 202 if fresh else 200
        return {"event_id": event_id, "duplicate": not fresh}

    @app.get("/events/{event_id}")
    def event_status(event_id: str) -> dict:
        ev = app.state.store.get(event_id)
        if ev is None:
            raise HTTPException(status_code=404, detail="unknown event")
        return {"event_id": ev.event_id, "source": ev.source, "status": ev.status,
                "attempts": app.state.store.attempt_count(ev.event_id)}

    @app.get("/dead-letters")
    def dead() -> list[dict]:
        return [{"event_id": e.event_id, "source": e.source} for e in app.state.store.dead_letters()]

    return app
