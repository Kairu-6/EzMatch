"""Self-check for the AutoCount/SQL invoice mapping (money/parser path).
Run: ./venv/Scripts/python.exe test_accounting_map.py"""
from accounting_client import map_invoice, get_recent_invoices, _MOCK_INVOICES

SME = "11111111-1111-1111-1111-111111111111"
REQUIRED = ("invoice_number", "counterparty_name", "invoice_currency", "invoice_amount", "invoice_date")

# Mapping normalises a fixture-shaped doc to an invoice row.
doc = {"DocNo": "AC-9", "DebtorName": "Buyer Sdn Bhd", "CurrencyCode": "USD",
       "Total": "12500.00", "DocDate": "2026-06-20", "DueDate": "2026-07-20"}
row = map_invoice(doc, SME, "autocount")
assert row["invoice_number"] == "AC-9"
assert row["counterparty_name"] == "Buyer Sdn Bhd"
assert row["invoice_currency"] == "USD"
assert row["invoice_amount"] == 12500.00        # coerced from string
assert row["invoice_date"] == "2026-06-20"
assert row["due_date"] == "2026-07-20"
assert row["source"] == "autocount" and row["source_ref"] == "AC-9"
assert row["status"] == "pending" and row["direction"] == "Sent"
assert row["sme_id"] == SME

# Currency defaults to MYR when absent; amount is made positive.
d2 = map_invoice({"DocNo": "X", "DebtorName": "Y", "Total": -300, "DocDate": "2026-01-01"}, SME, "sql")
assert d2["invoice_currency"] == "MYR", d2["invoice_currency"]
assert d2["invoice_amount"] == 300.0, d2["invoice_amount"]
assert d2["source"] == "sql"

# Idempotency: same doc maps to the same upsert key every time.
assert map_invoice(doc, SME, "autocount")["source_ref"] == row["source_ref"]

# Every mock fixture must satisfy the recon contract (else it's silently dropped).
n = 0
for provider in ("autocount", "sql"):
    for fixture in get_recent_invoices({"environment": "mock", "provider": provider}):
        r = map_invoice(fixture, SME, provider)
        assert all(r.get(k) for k in REQUIRED), (provider, r)
        assert r["invoice_amount"] > 0, r          # invoice_amount CHECK (> 0)
        assert r["source"] == provider
        n += 1

# Both providers are mock-only: any non-mock environment raises (no hallucinated API).
for provider in ("autocount", "sql"):
    try:
        get_recent_invoices({"environment": "demo", "provider": provider})
        assert False, f"{provider} live path should raise NotImplementedError"
    except NotImplementedError:
        pass

total = sum(len(v) for v in _MOCK_INVOICES.values())
print(f"OK — mapping + defaults + idempotency + {n}/{total} mock fixtures pass.")
