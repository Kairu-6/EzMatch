"""Self-check for the MyInvois UBL->invoice mapping (money/parser path).
Run: ./venv/Scripts/python.exe test_myinvois_map.py"""
from myinvois_client import map_document, get_recent_documents, get_document_raw, _MOCK_DOCS

SME = "11111111-1111-1111-1111-111111111111"

# A doc where supplier != customer, in a non-MYR currency, so we prove currency
# comes from DocumentCurrencyCode (not the MYR-only recent/details totals) and that
# the counterparty flips with direction.
UBL = {"Invoice": [{
    "ID": [{"_": "EINV-42"}],
    "IssueDate": [{"_": "2026-06-20"}],
    "DocumentCurrencyCode": [{"_": "USD"}],
    "AccountingSupplierParty": [{"Party": [{"PartyLegalEntity": [{"RegistrationName": [{"_": "Us Sdn Bhd"}]}]}]}],
    "AccountingCustomerParty": [{"Party": [{"PartyLegalEntity": [{"RegistrationName": [{"_": "Buyer LLC"}]}]}]}],
    "LegalMonetaryTotal": [{"PayableAmount": [{"_": 12500.00, "currencyID": "USD"}]}],
    "PaymentMeans": [{"PaymentDueDate": [{"_": "2026-07-20"}]}],
}]}

sent = map_document(UBL, "Sent", SME, "uuid-1")
assert sent["invoice_currency"] == "USD", sent["invoice_currency"]      # from DocumentCurrencyCode
assert sent["invoice_amount"] == 12500.00, sent["invoice_amount"]        # from PayableAmount
assert sent["invoice_number"] == "EINV-42"
assert sent["invoice_date"] == "2026-06-20"
assert sent["due_date"] == "2026-07-20"
assert sent["counterparty_name"] == "Buyer LLC"                          # Sent -> customer
assert sent["status"] == "pending" and sent["source"] == "myinvois"
assert sent["sme_id"] == SME and sent["myinvois_uuid"] == "uuid-1"

recv = map_document(UBL, "Received", SME, "uuid-1")
assert recv["counterparty_name"] == "Us Sdn Bhd"                         # Received -> supplier

# Idempotency: same doc maps to the same upsert key every time.
assert map_document(UBL, "Sent", SME, "uuid-1")["myinvois_uuid"] == sent["myinvois_uuid"]

# Every mock fixture must satisfy the recon contract (else it's silently dropped).
REQUIRED = ("invoice_number", "counterparty_name", "invoice_currency", "invoice_amount", "invoice_date")
creds = {"environment": "mock"}
for direction in ("Sent", "Received"):
    for meta in get_recent_documents(creds, direction):
        row = map_document(get_document_raw(creds, meta["uuid"]), direction, SME, meta["uuid"])
        assert all(row.get(k) for k in REQUIRED), (direction, meta["uuid"], row)
        assert row["invoice_amount"] > 0, row  # invoice_amount CHECK (> 0)

print(f"OK — mapping + idempotency + {len(_MOCK_DOCS)} mock fixtures pass.")
