"""Finverse bank-feed client — pulls a tenant's bank transactions into the same
`bank_transaction` seam that CSV/XLSX uploads use.

Unlike MyInvois/AutoCount, Finverse is NOT a "save per-tenant creds + sync" connector.
The app has ONE set of GLOBAL developer creds (env), and the per-tenant artifact is a
CONSENT (`login_identity`) obtained via a three-legged browser redirect (Finverse Link).
So the flow is: create_link_session -> user authorizes their bank in Finverse's hosted
UI -> callback with a code -> exchange_code -> store the login_identity token -> later
get_transactions pulls with that token.

Endpoints/fields verified from the official SDK (github.com/finversetech/sdk-typescript,
api.ts path literals + test/responses/*.ts). Their docs site is an SPA.

Environments (FINVERSE_ENV): "mock" returns static fixtures AND a link_url that points
straight back at our own callback with a mock code (so the whole consent->pull->recon
path is exercised offline, no Finverse account needed); "sandbox"/"prod" hit the real API
— identical code path, only the host + a registered redirect_uri + real creds differ.

# ponytail: in-proc token cache, plaintext token at rest — same prototype ceilings already
# accepted for myinvois_client / myinvois_credential. Move to a shared store + pgcrypto to scale.
"""
import logging
import os
import time

import httpx

from data_contracts import TransactionSchema
from statement_parser import _normalise_description, _extract_reference

logger = logging.getLogger(__name__)

# Finverse uses ONE API host for BOTH test and live — there is no api.sandbox host
# (it doesn't resolve). "sandbox" vs "prod" is decided by which CREDENTIALS you use
# (and test institutions in Link), not by the host. Verified: api.prod resolves +
# authenticates, api.sandbox.finverse.net fails DNS.
_API_HOST = "https://api.prod.finverse.net"


def _env() -> str:
    return os.environ.get("FINVERSE_ENV", "mock")


def _host() -> str:
    if _env() == "mock":
        raise RuntimeError("_host() called in mock mode — mock branches must not hit the network.")
    return _API_HOST


def _redirect_uri() -> str:
    return os.environ.get("FINVERSE_REDIRECT_URI", "http://127.0.0.1:8000/api/bankfeed/callback")


def _frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:3000")


# ── Customer token (client_credentials) ─────────────────────────────────────────
_token_cache: dict[str, tuple[str, float]] = {}  # env -> (token, expires_at)


def _customer_token() -> str:
    env = _env()
    cached = _token_cache.get(env)
    if cached and cached[1] > time.time() + 60:  # 60s safety margin (SDK guidance)
        return cached[0]
    resp = httpx.post(
        f"{_host()}/auth/customer/token",
        json={
            "client_id": os.environ["FINVERSE_CLIENT_ID"],
            "client_secret": os.environ["FINVERSE_CLIENT_SECRET"],
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    token = body["access_token"]
    _token_cache[env] = (token, time.time() + int(body.get("expires_in", 3600)))
    return token


# ── 1. Start a Link session -> hosted link_url ───────────────────────────────────
def create_link_session(state: str) -> str:
    """Return the URL the user's browser should visit to authorize their bank.

    Mock: point straight back at our own callback with a mock code, so the callback +
    persistence + sync all run offline exactly as in the real flow (skips Finverse's UI)."""
    if _env() == "mock":
        return f"{_redirect_uri()}?code=mock-code&state={state}"

    resp = httpx.post(
        f"{_host()}/link/token",
        headers={"Authorization": f"Bearer {_customer_token()}"},
        json={
            "client_id": os.environ["FINVERSE_CLIENT_ID"],
            "grant_type": "client_credentials",
            "response_type": "code",
            # ponytail: query redirect (callback = GET ?code&state). Switch to "form_post"
            # only if the dashboard app is configured for it (then callback must accept a POST form).
            "response_mode": "query",
            "ui_mode": "redirect",
            "redirect_uri": _redirect_uri(),  # must be pre-registered in dashboard.finverse.com
            "state": state,
            "user_id": state[:64],  # opaque to Finverse; we route via `state`, not this
            "countries": ["MYS"],   # ISO-3; confirm MY institution coverage on the app
            "language": "en",       # enum has no Malay
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["link_url"]


# ── 2. Exchange the callback code for a login_identity + its accounts ─────────────
def _pick(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def exchange_code(code: str) -> dict:
    """code -> {finverse_login_id, access_token, refresh_token, token_expires_at, accounts:[…]}."""
    if _env() == "mock":
        return _MOCK_IDENTITY

    customer = _customer_token()
    tok = httpx.post(
        f"{_host()}/auth/token",
        headers={
            "Authorization": f"Bearer {customer}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": os.environ["FINVERSE_CLIENT_ID"],
            "redirect_uri": _redirect_uri(),
        },
        timeout=30,
    )
    tok.raise_for_status()
    tb = tok.json()
    li_token = tb["access_token"]

    # Poll retrieval status until terminal (data ready), then read the accounts.
    accounts: list[dict] = []
    for _ in range(20):
        li = httpx.get(
            f"{_host()}/login_identity",
            headers={"Authorization": f"Bearer {li_token}"},
            timeout=30,
        )
        li.raise_for_status()
        body = li.json().get("login_identity", li.json())
        status = body.get("status")
        accounts = body.get("accounts", []) or accounts
        if status in ("DATA_RETRIEVAL_COMPLETE", "DATA_RETRIEVAL_PARTIALLY_SUCCESSFUL", "ERROR"):
            break
        time.sleep(3)

    return {
        "finverse_login_id": tb.get("login_identity_id"),
        "access_token": li_token,
        "refresh_token": tb.get("refresh_token"),
        "token_expires_at": time.time() + int(tb.get("expires_in", 3600)),
        # ponytail: account field names not code-confirmed (data-track research failed on an
        # API overload); _pick tolerates the likely variants. Verify against a live payload.
        "accounts": [
            {
                "finverse_account_id": _pick(a, "account_id", "id"),
                "institution": _pick(a, "institution_name", "institution", "institution_id") or "Bank",
                "currency": _pick(a, "currency", "currency_code") or "MYR",
                "mask": _pick(a, "account_number", "mask", "masked_number") or "",
            }
            for a in accounts
        ],
    }


# ── 3. Pull transactions -> the parser's parsed_result blob ──────────────────────
def map_transaction(doc: dict) -> dict | None:
    """Finverse transaction -> a TransactionSchema-shaped row, or None to drop it.

    Seeds `transaction_id` from Finverse's STABLE id (not a content hash) so re-syncs
    dedup exactly; upload_parsed_statement then account-scopes it."""
    if doc.get("is_pending"):
        return None
    amount = doc.get("amount") or {}
    val = amount.get("value")
    if val is None:
        return None
    desc = doc.get("description") or ""
    row = {
        "transaction_id": doc.get("transaction_id"),
        "transaction_date": doc.get("posted_date"),
        "description": desc,
        "description_normalised": _normalise_description(desc),
        "reference_number": _extract_reference(desc),
        "debit_amount": round(abs(val), 2) if val < 0 else None,
        "credit_amount": round(val, 2) if val >= 0 else None,
        "currency_code": amount.get("currency") or "",
        "running_balance": None,
        "is_matched": False,
    }
    try:
        # Validate/normalise exactly like parse_bank_statement does; drop junk rows.
        return TransactionSchema(**row).model_dump()
    except Exception as exc:
        logger.warning("Dropping unmappable Finverse txn %s: %s", doc.get("transaction_id"), exc)
        return None


def _to_parsed_result(rows: list[dict]) -> dict:
    dates = sorted(r["transaction_date"] for r in rows) if rows else []
    return {
        "status": "success",
        "data": rows,
        "meta": {
            "currency": rows[0]["currency_code"] if rows else None,
            "date_range": {"from": dates[0] if dates else None, "to": dates[-1] if dates else None},
        },
    }


def get_transactions(link: dict) -> dict:
    """Pull all transactions for a stored consent -> parser blob for upload_parsed_statement."""
    if _env() == "mock":
        rows = [r for r in (map_transaction(t) for t in _MOCK_TXNS) if r]
        return _to_parsed_result(rows)

    token = link["access_token"]
    raw: list[dict] = []
    offset, limit = 0, 1000
    while True:
        resp = httpx.get(
            f"{_host()}/transactions",
            headers={"Authorization": f"Bearer {token}"},
            params={"offset": offset, "limit": limit},
            timeout=60,
        )
        resp.raise_for_status()
        body = resp.json()
        batch = body.get("transactions", []) or []
        raw.extend(batch)
        offset += len(batch)
        if not batch or offset >= int(body.get("total_transactions", offset)):
            break
    rows = [r for r in (map_transaction(t) for t in raw) if r]
    return _to_parsed_result(rows)


# ── Mock fixtures ────────────────────────────────────────────────────────────────
# Amounts/refs mirror accounting_client's mock invoices (Penang Foods, Crescent, Selat),
# so a mock accounting-sync + a mock bank-feed-sync reconcile against EACH OTHER in the
# demo — feed transactions carry the invoice ref as a DuitNow recipient reference.
_MOCK_IDENTITY = {
    "finverse_login_id": "mock-login-0001",
    "access_token": "mock-login-identity-token",
    "refresh_token": "mock-refresh-token",
    "token_expires_at": time.time() + 3600,
    "accounts": [
        {"finverse_account_id": "mock-acct-0001", "institution": "TestBank (Finverse Mock)",
         "currency": "MYR", "mask": "4321"},
    ],
}

_MOCK_TXNS = [
    {"transaction_id": "mock-fv-txn-0001", "posted_date": "2026-06-12", "is_pending": False,
     "amount": {"currency": "MYR", "value": 6656.00, "raw": "6656.00"},
     "description": "DUITNOW CR PENANG FOODS SDN BHD REF AC-INV-0001"},
    {"transaction_id": "mock-fv-txn-0002", "posted_date": "2026-06-10", "is_pending": False,
     "amount": {"currency": "MYR", "value": 7600.00, "raw": "7600.00"},
     "description": "DUITNOW CR CRESCENT TRADING SDN BHD REF AC-INV-0002"},
    {"transaction_id": "mock-fv-txn-0003", "posted_date": "2026-06-11", "is_pending": False,
     "amount": {"currency": "MYR", "value": 5400.00, "raw": "5400.00"},
     "description": "IBG CR SELAT SHIPPING SDN BHD REF AC-INV-0003"},
    {"transaction_id": "mock-fv-txn-0004", "posted_date": "2026-06-13", "is_pending": False,
     "amount": {"currency": "MYR", "value": -1280.50, "raw": "-1280.50"},
     "description": "DUITNOW DR OFFICE SUPPLIES TRADING"},  # noise / stays unmatched
    {"transaction_id": "mock-fv-txn-0005", "posted_date": "2026-06-14", "is_pending": True,
     "amount": {"currency": "MYR", "value": 999.00, "raw": "999.00"},
     "description": "PENDING AUTHORIZATION HOLD"},  # dropped: is_pending
]


def _demo():
    """Self-check: mock get_transactions yields exactly the keys the ingestion seam consumes,
    the pending row is dropped, and signs map correctly."""
    os.environ["FINVERSE_ENV"] = "mock"
    parsed = get_transactions(_MOCK_IDENTITY)
    assert parsed["status"] == "success"
    rows = parsed["data"]
    assert len(rows) == 4, f"expected 4 (1 pending dropped), got {len(rows)}"
    seam_keys = {"transaction_id", "transaction_date", "description", "description_normalised",
                 "reference_number", "debit_amount", "credit_amount", "currency_code",
                 "running_balance", "is_matched"}
    for r in rows:
        assert set(r.keys()) == seam_keys, f"row keys drifted from seam: {set(r.keys()) ^ seam_keys}"
    credit = next(r for r in rows if r["transaction_id"] == "mock-fv-txn-0001")
    assert credit["credit_amount"] == 6656.00 and credit["debit_amount"] is None
    assert credit["reference_number"] == "AC-INV-0001", credit["reference_number"]
    debit = next(r for r in rows if r["transaction_id"] == "mock-fv-txn-0004")
    assert debit["debit_amount"] == 1280.50 and debit["credit_amount"] is None
    # 06-14 belonged to the dropped pending row, so the real max is 06-13.
    assert parsed["meta"]["date_range"] == {"from": "2026-06-10", "to": "2026-06-13"}
    assert create_link_session("SIGNED").startswith(_redirect_uri())
    print("bank_feed_client self-check passed.")


if __name__ == "__main__":
    _demo()
