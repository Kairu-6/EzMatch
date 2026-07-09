"""Signed OAuth `state` for the Finverse Link redirect.

The bank-feed callback (`GET /api/bankfeed/callback`) is hit by Finverse's browser
redirect, so it carries NO Bearer JWT — we can't resolve the tenant the usual way
(auth.get_current_sme_id). Instead we mint a short-lived HMAC-signed token holding
the sme_id when we start the Link session, and verify it on the callback. This both
routes the callback to the right tenant AND acts as CSRF protection (an attacker
can't forge a valid state without the secret).

# ponytail: 10-min expiry is the replay ceiling. Stateless (no DB) is deliberate —
# a single-use nonce table is the upgrade only if replay-within-the-window becomes
# a real threat, which it isn't for this prototype.
"""
import hashlib
import hmac
import os
import time

_TTL = 600   # seconds a signed state stays valid
_SIGLEN = 32  # hex chars of HMAC kept = 128-bit truncation (Finverse caps `state` at 100 chars)


def _secret() -> bytes:
    s = os.environ.get("BANKFEED_STATE_SECRET", "")
    if not s:
        raise RuntimeError("BANKFEED_STATE_SECRET is not set — required for bank-feed linking.")
    return s.encode()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:_SIGLEN]


def sign_state(sme_id: str) -> str:
    """Return a compact, tamper-evident token carrying sme_id + issue time.
    Format `sme_id.epoch.sig` (~80 chars; sme_id is a uuid with no dots)."""
    payload = f"{sme_id}.{int(time.time())}"
    return f"{payload}.{_sign(payload)}"


def verify_state(state: str) -> str:
    """Return the sme_id from a valid, unexpired state, else raise ValueError."""
    try:
        sme_id, issued, sig = state.rsplit(".", 2)
        issued_at = int(issued)
    except (ValueError, AttributeError):
        raise ValueError("Malformed state.")
    if not hmac.compare_digest(sig, _sign(f"{sme_id}.{issued}")):  # constant-time
        raise ValueError("Bad state signature.")
    if time.time() - issued_at > _TTL:
        raise ValueError("State expired.")
    return sme_id


def _demo():
    """Self-check for the security path: roundtrip, tamper reject, expiry reject."""
    os.environ["BANKFEED_STATE_SECRET"] = "test-secret-not-real"
    sme = "111e4567-e89b-12d3-a456-426614174000"

    tok = sign_state(sme)
    assert verify_state(tok) == sme, "roundtrip failed"
    assert len(tok) <= 100, f"state too long for Finverse ({len(tok)} chars)"

    sme_id, issued, sig = tok.rsplit(".", 2)

    # Tampered signature is rejected.
    try:
        verify_state(f"{sme_id}.{issued}.{'0' * len(sig)}")
        assert False, "tampered signature accepted"
    except ValueError:
        pass

    # Tampered payload (different sme_id, old sig) is rejected.
    try:
        verify_state(f"999.{issued}.{sig}")
        assert False, "tampered payload accepted"
    except ValueError:
        pass

    # Expired state is rejected.
    old_payload = f"{sme}.{int(time.time()) - _TTL - 1}"
    try:
        verify_state(f"{old_payload}.{_sign(old_payload)}")
        assert False, "expired state accepted"
    except ValueError:
        pass

    # Garbage is rejected, not crashed.
    for junk in ("", "no-dot", "a.b.c", "!!!.###"):
        try:
            verify_state(junk)
            assert False, f"garbage accepted: {junk!r}"
        except ValueError:
            pass

    print("bankfeed_state self-check passed.")


if __name__ == "__main__":
    _demo()
