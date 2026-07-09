"""AutoCount / SQL Account sales-invoice pull client.

HONEST STATUS: both providers are MOCK-ONLY. AutoCount's and SQL Account's real API
documentation is gated behind a paid SME subscription (SQL Account's API is also
on-premise), so we could not obtain the real endpoints, methods, auth, or field
schemas. Rather than guess/hallucinate an API surface, the live path is left
unimplemented — it raises NotImplementedError. Mock mode returns a small set of
sample invoices so the connector demonstrates the end-to-end reconciliation flow
(map -> invoice table -> recon) exactly as a real source would.

To integrate for real later: obtain an SME subscription + the official API docs for
the provider, then implement get_recent_invoices() for that provider and adjust
map_invoice() to the real field names. Everything downstream (dedup, upsert on
(sme_id, source, source_ref), recon) already works.
"""


# ── Pull ──────────────────────────────────────────────────────────────────────
def get_recent_invoices(creds: dict) -> list[dict]:
    """List sales invoices for the tenant's configured provider. Mock-only for now."""
    provider = creds.get("provider", "autocount")

    if creds.get("environment") == "mock":
        return _MOCK_INVOICES.get(provider, [])

    # No hallucinated API path: the real integration is not implemented because the
    # provider's API documentation requires a paid SME subscription we don't have.
    raise NotImplementedError(
        f"Live {provider} integration is not available — its API documentation requires "
        f"a paid SME subscription (SQL Account is also on-premise). Use environment='mock'."
    )


# ── Map (mock fixtures -> invoice row) ──────────────────────────────────────────
def _pick(doc: dict, *keys):
    """First present, non-empty value among candidate keys."""
    for k in keys:
        v = doc.get(k)
        if v not in (None, ""):
            return v
    return None


def map_invoice(doc: dict, sme_id: str, provider: str) -> dict:
    """Mock fixture dict -> an `invoice` row. Fills the exact non-null columns
    orchestrator._fetch_invoices requires, else the row is silently dropped."""
    doc_no = _pick(doc, "DocNo", "InvoiceNo", "DocumentNo")
    amount = _pick(doc, "Total", "NetTotal", "Amount")
    return {
        "sme_id": sme_id,
        "source": provider,            # "autocount" | "sql"
        "source_ref": doc_no,
        "direction": "Sent",           # AR/sales listing = receivables
        "status": "pending",
        "invoice_number": doc_no,
        "counterparty_name": _pick(doc, "DebtorName", "CustomerName", "CompanyName"),
        "invoice_currency": _pick(doc, "CurrencyCode", "Currency") or "MYR",
        "invoice_amount": abs(float(amount)) if amount is not None else None,
        "invoice_date": _pick(doc, "DocDate", "InvoiceDate"),
        "due_date": _pick(doc, "DueDate"),
    }


# ── Mock fixtures ────────────────────────────────────────────────────────────────
# Sample invoices only — NOT a claim about the real API's schema. Amounts/counterparties
# are aligned to WZB Group's unmatched credit transactions so a mock sync -> reconcile
# produces real matches in the demo. Deterministic DocNos so re-sync is idempotent.
def _inv(doc_no, debtor, currency, total, doc_date, due):
    return {"DocNo": doc_no, "DebtorName": debtor, "CurrencyCode": currency,
            "Total": total, "DocDate": doc_date, "DueDate": due}


_MOCK_INVOICES = {
    "autocount": [
        _inv("AC-INV-0001", "Penang Foods Sdn Bhd",       "MYR", 6656.00, "2026-06-12", "2026-07-12"),
        _inv("AC-INV-0002", "Crescent Trading Sdn Bhd",   "MYR", 7600.00, "2026-06-10", "2026-07-10"),
        _inv("AC-INV-0003", "Selat Shipping Sdn Bhd",     "MYR", 5400.00, "2026-06-11", "2026-07-11"),
        _inv("AC-INV-0004", "Contoso Trading LLC",        "USD", 2329.77, "2026-06-14", "2026-07-14"),
        _inv("AC-INV-0005", "Rembau Rubber Sdn Bhd",      "MYR", 9120.00, "2026-06-15", "2026-07-15"),
        _inv("AC-INV-0006", "Kuantan Ceramics",           "MYR", 4380.00, "2026-06-16", "2026-07-16"),
        _inv("AC-INV-0007", "Bentong Ginger Traders",     "MYR", 3175.00, "2026-06-17", "2026-07-17"),
        _inv("AC-INV-0008", "Muar Furniture Bhd",         "MYR", 8890.00, "2026-06-18", "2026-07-18"),
    ],
    "sql": [
        _inv("SQL-INV-0001", "Nordwind GmbH",             "EUR", 2603.03, "2026-06-14", "2026-07-14"),
        _inv("SQL-INV-0002", "Selangor Foods Sdn Bhd",    "MYR", 5289.40, "2026-06-13", "2026-07-13"),
        _inv("SQL-INV-0003", "Alor Setar Textiles",       "MYR", 6210.00, "2026-06-14", "2026-07-14"),
        _inv("SQL-INV-0004", "Sungai Petani Steel",       "MYR", 4750.00, "2026-06-19", "2026-07-19"),
        _inv("SQL-INV-0005", "Taiping Tea Company",       "MYR", 3990.00, "2026-06-20", "2026-07-20"),
    ],
}
