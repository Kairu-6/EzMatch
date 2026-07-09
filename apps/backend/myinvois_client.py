"""LHDN MyInvois e-Invoice pull client.

Pulls VALIDATED e-Invoices from MyInvois so they land in the `invoice` table and
flow through reconciliation like OCR'd invoices. See the migration `add_myinvois`
and CLAUDE.md's MyInvois section.

Auth model: taxpayer (per-tenant client_id/secret). Intermediary path is left in
behind creds["model"] == "intermediary" (adds an `onbehalfof: <tin>` header) but is
not exercised yet.

Environments: "mock" returns static fixtures (demoable with no real creds);
"preprod"/"production" hit the real API. The UBL->invoice mapping (`map_document`)
is identical in both paths — mock fixtures ARE raw-UBL JSON.
"""
import time

import httpx

# ponytail: token host vs document-API host differ across LHDN docs; if a real call
# 404s/401s, this is the one line to fix. preprod/prod bases per the SDK guide.
_BASES = {
    "preprod": "https://preprod.myinvois.hasil.gov.my",
    "production": "https://myinvois.hasil.gov.my",
}
_SCOPE = "InvoicingAPI"

# ── OAuth2 token cache ────────────────────────────────────────────────────────
# ponytail: in-proc dict, fine for a single uvicorn worker. Move to a shared store
# if you ever run multiple workers.
_token_cache: dict[str, tuple[str, float]] = {}  # client_id -> (token, expires_at)


def get_token(creds: dict) -> str:
    client_id = creds["client_id"]
    cached = _token_cache.get(client_id)
    if cached and cached[1] > time.time() + 30:  # 30s safety margin
        return cached[0]

    base = _BASES[creds["environment"]]
    headers = {}
    if creds.get("model") == "intermediary" and creds.get("tin"):
        headers["onbehalfof"] = creds["tin"]

    resp = httpx.post(
        f"{base}/connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": creds["client_secret"],
            "scope": _SCOPE,
        },
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    token = body["access_token"]
    _token_cache[client_id] = (token, time.time() + int(body.get("expires_in", 3600)))
    return token


def _auth_headers(creds: dict) -> dict:
    headers = {"Authorization": f"Bearer {get_token(creds)}"}
    if creds.get("model") == "intermediary" and creds.get("tin"):
        headers["onbehalfof"] = creds["tin"]
    return headers


# ── Pull ──────────────────────────────────────────────────────────────────────
def get_recent_documents(creds: dict, direction: str) -> list[dict]:
    """List Valid documents (last 31 days) for a direction ('Sent' | 'Received').
    Returns lightweight metadata dicts; each has a 'uuid'."""
    if creds["environment"] == "mock":
        return [{"uuid": d["uuid"]} for d in _MOCK_DOCS if d["direction"] == direction]

    base = _BASES[creds["environment"]]
    resp = httpx.get(
        f"{base}/api/v1.0/documents/recent",
        params={"InvoiceDirection": direction, "status": "Valid", "pageSize": 100},
        headers=_auth_headers(creds),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", [])


def get_document_raw(creds: dict, uuid: str) -> dict:
    """Fetch the raw UBL 2.1 JSON for a document (carries DocumentCurrencyCode +
    totals, which the recent/details endpoints omit — MYR only)."""
    if creds["environment"] == "mock":
        return next(d["ubl"] for d in _MOCK_DOCS if d["uuid"] == uuid)

    base = _BASES[creds["environment"]]
    resp = httpx.get(
        f"{base}/api/v1.0/documents/{uuid}/raw",
        headers=_auth_headers(creds),
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    # ponytail: real /raw wraps the UBL in an envelope; the doc lives under
    # "document" (sometimes as a JSON string). Confirm the exact key against the SDK.
    doc = body.get("document", body)
    if isinstance(doc, str):
        import json
        doc = json.loads(doc)
    return doc


# ── UBL 2.1 JSON navigation ─────────────────────────────────────────────────────
def _ubl(node, *path):
    """Walk MyInvois UBL JSON, which nests every field as [{"_": value, ...}].
    Returns the leaf scalar or None."""
    cur = node
    for key in path:
        if not isinstance(cur, (list, dict)):
            return None
        if isinstance(cur, list):
            cur = cur[0] if cur else None
        if cur is None:
            return None
        cur = cur.get(key) if isinstance(cur, dict) else None
    if isinstance(cur, list):
        cur = cur[0] if cur else None
    return cur.get("_") if isinstance(cur, dict) else cur


def _party_name(inv, party_key: str):
    party = _ubl_node(inv, party_key, "Party")
    return _ubl(party, "PartyLegalEntity", "RegistrationName")


def _ubl_node(node, *path):
    """Like _ubl but returns the sub-node (dict/list), not the leaf scalar."""
    cur = node
    for key in path:
        if isinstance(cur, list):
            cur = cur[0] if cur else None
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def map_document(ubl: dict, direction: str, sme_id: str, uuid: str) -> dict:
    """UBL 2.1 JSON -> an `invoice` row. Fills the exact non-null columns
    orchestrator._fetch_invoices requires, else the row is silently dropped."""
    inv = ubl.get("Invoice", ubl)  # tolerate a bare Invoice body
    # Sent = we issued it -> counterparty is the customer/buyer.
    # Received = a vendor issued it -> counterparty is the supplier.
    counterparty = (
        _party_name(inv, "AccountingCustomerParty")
        if direction == "Sent"
        else _party_name(inv, "AccountingSupplierParty")
    )
    amount = _ubl(inv, "LegalMonetaryTotal", "PayableAmount")
    return {
        "sme_id": sme_id,
        "myinvois_uuid": uuid,
        "direction": direction,
        "source": "myinvois",
        "status": "pending",
        "invoice_number": _ubl(inv, "ID"),
        "counterparty_name": counterparty,
        "invoice_currency": _ubl(inv, "DocumentCurrencyCode"),
        "invoice_amount": float(amount) if amount is not None else None,
        "invoice_date": _ubl(inv, "IssueDate"),
        "due_date": _ubl(inv, "PaymentMeans", "PaymentDueDate"),
    }


# ── Mock fixtures (raw-UBL JSON, so map_document is exercised identically) ───────
def _mk_ubl(inv_id, currency, amount, issue, due, supplier, customer):
    return {"Invoice": [{
        "ID": [{"_": inv_id}],
        "IssueDate": [{"_": issue}],
        "DocumentCurrencyCode": [{"_": currency}],
        "AccountingSupplierParty": [{"Party": [{
            "PartyLegalEntity": [{"RegistrationName": [{"_": supplier}]}]}]}],
        "AccountingCustomerParty": [{"Party": [{
            "PartyLegalEntity": [{"RegistrationName": [{"_": customer}]}]}]}],
        "LegalMonetaryTotal": [{"PayableAmount": [{"_": amount, "currencyID": currency}]}],
        "PaymentMeans": [{"PaymentDueDate": [{"_": due}]}],
    }]}


# Deterministic uuids so re-sync is idempotent. "us"/"them" = the demo tenant is
# supplier (Sent) or customer (Received). Currencies exist in the `currency` table.
_MOCK_DOCS = [
    {"uuid": "mock-einv-0001", "direction": "Sent",
     "ubl": _mk_ubl("EINV-2026-001", "USD", 12500.00, "2026-06-20", "2026-07-20",
                    "ezMatch Demo Sdn Bhd", "Contoso Trading LLC")},
    {"uuid": "mock-einv-0002", "direction": "Sent",
     "ubl": _mk_ubl("EINV-2026-002", "MYR", 8400.00, "2026-06-22", "2026-07-22",
                    "ezMatch Demo Sdn Bhd", "Seri Mutiara Enterprise")},
    {"uuid": "mock-einv-0003", "direction": "Sent",
     "ubl": _mk_ubl("EINV-2026-003", "EUR", 6750.50, "2026-06-25", "2026-07-25",
                    "ezMatch Demo Sdn Bhd", "Nordwind GmbH")},
    {"uuid": "mock-einv-0004", "direction": "Received",
     "ubl": _mk_ubl("BILL-9931", "MYR", 3200.00, "2026-06-18", "2026-07-18",
                    "Klang Valley Logistics Sdn Bhd", "ezMatch Demo Sdn Bhd")},
    {"uuid": "mock-einv-0005", "direction": "Received",
     "ubl": _mk_ubl("BILL-9942", "SGD", 1980.00, "2026-06-27", "2026-07-27",
                    "Lion City Supplies Pte Ltd", "ezMatch Demo Sdn Bhd")},
    {"uuid": "mock-einv-0006", "direction": "Sent",
     "ubl": _mk_ubl("EINV-2026-006", "MYR", 7250.00, "2026-06-21", "2026-07-21",
                    "ezMatch Demo Sdn Bhd", "Puchong Plastics Sdn Bhd")},
    {"uuid": "mock-einv-0007", "direction": "Sent",
     "ubl": _mk_ubl("EINV-2026-007", "USD", 4100.00, "2026-06-23", "2026-07-23",
                    "ezMatch Demo Sdn Bhd", "Cascadia Imports Inc")},
    {"uuid": "mock-einv-0008", "direction": "Received",
     "ubl": _mk_ubl("BILL-9953", "MYR", 2600.00, "2026-06-24", "2026-07-24",
                    "Klang Freight Movers Sdn Bhd", "ezMatch Demo Sdn Bhd")},
]
