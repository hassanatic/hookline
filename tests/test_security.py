import pytest

from hookline.security import SignatureError, sign, verify

SECRET = b"test-secret"


def test_roundtrip_valid():
    body = b'{"id": "evt_1"}'
    ts = 1_700_000_000
    sig = sign(SECRET, ts, body)
    verify(SECRET, ts, body, sig, now=ts + 10)


def test_tampered_body_rejected():
    ts = 1_700_000_000
    sig = sign(SECRET, ts, b'{"amount": 10}')
    with pytest.raises(SignatureError, match="mismatch"):
        verify(SECRET, ts, b'{"amount": 9999}', sig, now=ts + 10)


def test_wrong_secret_rejected():
    ts = 1_700_000_000
    body = b"{}"
    sig = sign(b"other-secret", ts, body)
    with pytest.raises(SignatureError, match="mismatch"):
        verify(SECRET, ts, body, sig, now=ts + 10)


def test_replay_outside_window_rejected():
    ts = 1_700_000_000
    body = b"{}"
    sig = sign(SECRET, ts, body)
    with pytest.raises(SignatureError, match="too old"):
        verify(SECRET, ts, body, sig, now=ts + 301)


def test_future_timestamp_rejected():
    ts = 1_700_000_000
    body = b"{}"
    sig = sign(SECRET, ts, body)
    with pytest.raises(SignatureError, match="future"):
        verify(SECRET, ts, body, sig, now=ts - 400)


def test_restamping_old_capture_breaks_signature():
    old_ts = 1_700_000_000
    body = b"{}"
    sig = sign(SECRET, old_ts, body)
    with pytest.raises(SignatureError, match="mismatch"):
        verify(SECRET, old_ts + 9_000, body, sig, now=old_ts + 9_000)
