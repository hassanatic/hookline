# hookline

The receiving half of webhooks, done properly. Verifies HMAC signatures with
a bound timestamp (so captured deliveries can't be replayed or re-stamped),
deduplicates at-least-once deliveries by event id, and persists every event
with its attempt history and a dead-letter state in SQLite.

Everything below is built and tested:

- **Receiver** (FastAPI): verify signature -> deduplicate -> acknowledge fast
  (202 fresh, 200 duplicate, 401 bad-signature-or-stale, 422 malformed). No
  business work on the receive path, so a slow handler can never make the
  sender time out and redeliver.
- **Dispatcher**: drives every stored event to a terminal state - retries with
  exponential backoff, then a queryable dead-letter list instead of a lost log
  line.

Run the whole journey in one command:

```bash
./.venv/bin/python examples/demo.py
```

## Development

```bash
python3 -m venv .venv && ./.venv/bin/pip install fastapi httpx uvicorn pytest
./.venv/bin/python -m pytest
```
