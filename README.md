# hookline

The receiving half of webhooks, done properly. Verifies HMAC signatures with
a bound timestamp (so captured deliveries can't be replayed or re-stamped),
deduplicates at-least-once deliveries by event id, and persists every event
with its attempt history and a dead-letter state in SQLite.

Work in progress: dispatch with retry/backoff and a FastAPI receiver are next.

## Development

```bash
python3 -m venv .venv && ./.venv/bin/pip install fastapi httpx uvicorn pytest
./.venv/bin/python -m pytest
```
