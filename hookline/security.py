"""Webhook authenticity: HMAC signatures and replay protection.

The receiving side of a webhook has to answer two questions before touching
the payload: did the configured sender really sign this body, and is it a
fresh delivery rather than a captured one replayed later? Signature checks
use a constant-time compare; freshness is a bounded timestamp window.
"""
from __future__ import annotations

import hashlib
import hmac
import time

DEFAULT_TOLERANCE_S = 300  # 5 minutes, the common provider default


class SignatureError(ValueError):
    pass


def sign(secret: bytes, timestamp: int, body: bytes) -> str:
    """Signature over `<timestamp>.<body>`, hex-encoded.

    Binding the timestamp into the signed message is what makes the replay
    window enforceable: an attacker cannot re-stamp an old capture without
    breaking the signature.
    """
    msg = str(timestamp).encode() + b"." + body
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def verify(secret: bytes, timestamp: int, body: bytes, signature: str,
           *, tolerance_s: int = DEFAULT_TOLERANCE_S, now: float | None = None) -> None:
    """Raise SignatureError unless the signature is valid AND fresh."""
    clock = time.time() if now is None else now
    age = clock - timestamp
    if age > tolerance_s:
        raise SignatureError(f"timestamp too old: {int(age)}s > {tolerance_s}s window")
    if age < -tolerance_s:
        raise SignatureError("timestamp is in the future beyond tolerance")
    expected = sign(secret, timestamp, body)
    if not hmac.compare_digest(expected, signature):
        raise SignatureError("signature mismatch")
