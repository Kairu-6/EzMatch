"""
seed_data.py — single source of truth for the multi-tenant demo dataset
========================================================================
`build()` returns four fully-resolved tenant datasets (deterministic IDs, so the
reseed is idempotent). Both the DB reseeder (`seed_demo.py`) and the upload-file
generator (`seed_files.py`) consume this module, so the pre-seeded rows and the
shippable test files always describe the same world.

Each tenant has:
  • 3 bank accounts (a base-currency primary + 2 foreign), mixed currencies.
  • A completed HISTORICAL reconciliation job (auto + human-`manual` matches) that
    gives Phase-B.1 learned-memory exemplars and Phase-B.3 outlier baselines the
    moment the DB is seeded — no prior run required.
  • A pre-seeded CURRENT set (pending invoices + matching/noise transactions in
    seeded statements + payment proofs) — the live reconcile/verify/anomaly demo.
  • A FILE set (invoices/proofs/statements as uploadable documents) delivered only
    under test_files/ — uploading them exercises the real parse pipeline without
    duplicating anything already in the DB.

Edge cases are spread across the tenants and tagged so they're easy to find:
  clean multi-currency auto-match, FX conversion, over-paid → escalate, unmatched,
  high-value-no-proof (B.2 downgrade), weak counterparty/description link (B.2),
  duplicate invoice (B.3), beneficiary mismatch (B.3), bank-detail change (B.3),
  amount outlier (B.3), failed invoice parse, failed proof parse, and statement
  format coverage (ISO / dd-mm-yyyy / signed-amount CSV + debit/credit XLSX).
"""
import hashlib
import random
import uuid
from datetime import date, datetime, timezone

# Stable namespace → every id is uuid5(NS, business-key): re-running yields the
# exact same UUIDs so inserts upsert in place.
NS = uuid.UUID("5eed5eed-0000-4000-8000-0000000dec0d")

# One documented password for all four demo logins (email pre-confirmed at seed).
DEMO_PASSWORD = "TreasuryFlow#2026"


def uid(*parts) -> str:
    return str(uuid.uuid5(NS, "|".join(str(p) for p in parts)))


def _utc_iso(d: date) -> str:
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc).isoformat()


def txid(account_id: str, date_iso: str, description: str, signed_amount: float,
         occurrence: int = 0) -> str:
    """Replicate statement_parser's account-scoped transaction id so a seeded
    transaction is identical to one produced by uploading the same statement."""
    base = hashlib.sha256(
        f"{date_iso}|{description.upper()}|{round(signed_amount, 2)}|{occurrence}".encode()
    ).hexdigest()
    return hashlib.sha256(f"{account_id}|{base}".encode()).hexdigest()


# ── FX (per-unit, to the noted currency). Upserted, keyed to the invoice date. ──
# rate is "1 FROM = <rate> TO".
RATES = {
    ("USD", "MYR"): 4.72, ("EUR", "MYR"): 5.10, ("SGD", "MYR"): 3.49,
    ("USD", "SGD"): 1.35, ("EUR", "SGD"): 1.46, ("MYR", "SGD"): 0.286,
}


def rate_for(frm: str, to: str) -> float:
    if frm == to:
        return 1.0
    return RATES[(frm, to)]


# ── tenant skeletons ───────────────────────────────────────────────
# WZB keeps its long-documented sme_id + Maybank account id + demo email so the
# existing handoff docs stay valid.
SME_DEFS = [
    {
        "sme_id": "111e4567-e89b-12d3-a456-426614174111",
        "slug": "wzb_group", "company_name": "WZB Group Sdn Bhd",
        "registration_no": "202301012345", "email": "finance@wzbgroup.my",
        "phone": "+60312345678", "country_code": "MY", "base_ccy": "MYR",
        "accounts": [
            ("999e4567-e89b-12d3-a456-426614174999", "Maybank", "512345678901", "MYR", True),
            (None, "CIMB Bank", "700112233445", "USD", False),
            (None, "HSBC", "300998877665", "EUR", False),
        ],
    },
    {
        "sme_id": "22222222-2222-4222-8222-222222222222",
        "slug": "nusantara_logistics", "company_name": "Nusantara Logistics Sdn Bhd",
        "registration_no": "201998811223", "email": "ops@nusantara-logistics.my",
        "phone": "+60341234567", "country_code": "MY", "base_ccy": "MYR",
        "accounts": [
            (None, "Public Bank", "388112200334", "MYR", True),
            (None, "RHB Bank", "211445566778", "USD", False),
            (None, "Maybank", "514998877001", "SGD", False),
        ],
    },
    {
        "sme_id": "33333333-3333-4333-8333-333333333333",
        "slug": "selangor_textiles", "company_name": "Selangor Textiles Bhd",
        "registration_no": "200512334455", "email": "finance@selangortextiles.my",
        "phone": "+60355512340", "country_code": "MY", "base_ccy": "MYR",
        "accounts": [
            (None, "CIMB Bank", "800221144556", "MYR", True),
            (None, "Bank Islam", "140778899221", "USD", False),
            (None, "OCBC", "555330011446", "EUR", False),
        ],
    },
    {
        "sme_id": "44444444-4444-4444-8444-444444444444",
        "slug": "pearl_delta", "company_name": "Pearl Delta Trading Pte Ltd",
        "registration_no": "S2021/77665G", "email": "accounts@pearldelta.sg",
        "phone": "+6562223344", "country_code": "SG", "base_ccy": "SGD",
        "accounts": [
            (None, "DBS Bank", "0011224455", "SGD", True),
            (None, "UOB", "3398877221", "USD", False),
            (None, "Maybank SG", "0455667788", "MYR", False),
        ],
    },
]


def _accounts(sme):
    out = []
    for i, (fixed_id, bank, acct_no, ccy, primary) in enumerate(sme["accounts"]):
        out.append({
            "account_id": fixed_id or uid("acct", sme["sme_id"], i),
            "sme_id": sme["sme_id"], "account_holder": sme["company_name"],
            "account_number": acct_no, "bank_name": bank, "currency_code": ccy,
            "is_active": True, "is_primary": primary,
        })
    return out


# Counterparty pools for deterministic filler.
_NOISE_DESCS = [
    "DUITNOW QR PAYMENT", "FPX ONLINE TRANSFER", "MONTHLY SERVICE CHARGE",
    "SALARY PAYROLL RUN", "SST TAX REMITTANCE", "UTILITIES TNB",
    "OFFICE RENT TENANCY", "INTEREST CREDIT", "CARD SETTLEMENT",
    "INSURANCE PREMIUM", "COURIER CHARGES", "CLOUD SUBSCRIPTION",
]


def _noise_txn(account_id, ccy, rng, d):
    desc = rng.choice(_NOISE_DESCS)
    credit = desc in ("FPX ONLINE TRANSFER", "INTEREST CREDIT", "DUITNOW QR PAYMENT")
    amt = round(rng.uniform(40, 4200), 2)
    if desc == "INTEREST CREDIT":
        amt = round(rng.uniform(5, 90), 2)
    signed = amt if credit else -amt
    return {
        "transaction_id": txid(account_id, d, desc, signed),
        "transaction_date": d, "description": desc,
        "description_normalised": desc.upper(),
        "credit_amount": amt if credit else None,
        "debit_amount": amt if not credit else None,
        "currency_code": ccy, "is_matched": False,
    }


def _match_txn(account_id, base_ccy, d, desc, credit_amt):
    return {
        "transaction_id": txid(account_id, d, desc, credit_amt),
        "transaction_date": d, "description": desc,
        "description_normalised": desc.upper(),
        "credit_amount": credit_amt, "debit_amount": None,
        "currency_code": base_ccy, "is_matched": False,
    }


def _inv(sme_id, num, cp, ccy, amt, idate, due, *, status="pending",
         error=None, tag=None):
    return {
        "invoice_id": uid("inv", sme_id, num), "sme_id": sme_id, "invoice_number": num,
        "counterparty_name": cp, "invoice_currency": ccy, "invoice_amount": amt,
        "invoice_date": idate, "due_date": due, "status": status,
        "error_message": error, "_tag": tag,
    }


def _proof(sme_id, invoice_id, amt, ccy, pdate, ref, *, sender=None, bank=None,
           account_number=None, swift=None, status="completed", error=None, tag=None,
           uploaded=None):
    parsed = None
    if status == "completed":
        parsed = {"sender_name": sender, "receiver_name": None, "bank_name": bank,
                  "swift_code": swift, "iban": None, "account_number": account_number,
                  "raw_text": None}
        parsed = {k: v for k, v in parsed.items() if v is not None}
    return {
        "proof_id": uid("proof", sme_id, ref), "sme_id": sme_id, "invoice_id": invoice_id,
        "file_type": "pdf", "file_path": f"seed://proof-{ref}",
        "parse_status": status, "parsed_amount": amt if status == "completed" else None,
        "parsed_currency": ccy if status == "completed" else None,
        "parsed_date": pdate if status == "completed" else None,
        "parsed_reference": ref if status == "completed" else None,
        "parsed_data": parsed, "error_message": error,
        "uploaded_at": _utc_iso(date.fromisoformat(uploaded or pdate or "2026-05-01")),
        "_tag": tag,
    }


def _build_history(sme, primary, rng):
    """A completed reconciliation job: matched invoices/transactions + match rows.
    Seeds B.1 (manual exemplars) and B.3 (per-counterparty amount baselines)."""
    sme_id = sme["sme_id"]
    base = sme["base_ccy"]
    job_id = uid("histjob", sme_id)
    stmt_id = uid("histstmt", sme_id)
    hist_acct = primary["account_id"]

    # A recurring counterparty with several tight historical amounts → outlier base.
    recurring = {"wzb_group": "Acme Corp", "nusantara_logistics": "Port Klang Freight",
                 "selangor_textiles": "Textile Buyers Co", "pearl_delta": "Marina Imports"}[sme["slug"]]
    base_amt = {"wzb_group": 10000, "nusantara_logistics": 8200,
                "selangor_textiles": 15500, "pearl_delta": 9000}[sme["slug"]]

    invoices, transactions, matches = [], [], []
    # 5 historical matches: 4 for the recurring counterparty (tight band) + 1 other,
    # two of them human-`manual` (learned-memory exemplars).
    specs = []
    for i in range(4):
        amt = base_amt + i * 60                       # tight cluster
        specs.append((recurring, base, float(amt), "manual" if i < 2 else "auto"))
    specs.append(({"wzb_group": "Bremen GmbH", "nusantara_logistics": "Hai Phong Lines",
                   "selangor_textiles": "Dyeworks Ltd", "pearl_delta": "Batam Traders"}[sme["slug"]],
                  base, base_amt * 1.4, "auto"))

    for i, (cp, ccy, amt, mstatus) in enumerate(specs):
        d = f"2026-05-{10 + i:02d}"
        num = f"H{sme['slug'][:3].upper()}-{i+1:03d}"
        inv = _inv(sme_id, num, cp, ccy, amt, d, f"2026-06-{10+i:02d}", status="matched")
        desc = f"INWARD {cp.upper()} SETTLEMENT"
        txn = _match_txn(hist_acct, base, f"2026-05-{12 + i:02d}", desc, round(amt, 2))
        invoices.append(inv)
        txn["is_matched"] = True
        transactions.append(txn)
        matches.append({
            "match_id": uid("histmatch", sme_id, num), "job_id": job_id,
            "invoice_id": inv["invoice_id"], "transaction_id": txn["transaction_id"],
            "proof_id": None, "rate_id": None, "match_confidence": 0.9,
            "invoice_amount": amt, "invoice_currency": ccy,
            "transaction_amount": round(amt, 2), "tx_currency": base,
            "converted_amount": round(amt, 2), "variance_amount": 0.0, "variance_pct": 0.0,
            "match_status": mstatus, "matched_at": _utc_iso(date.fromisoformat(d)),
        })

    statement = {"statement_id": stmt_id, "account_id": hist_acct, "file_type": "csv",
                 "file_path": "seed://history", "period_start": "2026-05-01",
                 "period_end": "2026-05-31", "parse_status": "completed"}
    job = {"job_id": job_id, "sme_id": sme_id, "status": "completed",
           "model_version": "seed-history", "matched_count": len(matches),
           "unmatched_count": 0, "started_at": _utc_iso(date(2026, 5, 31)),
           "completed_at": _utc_iso(date(2026, 5, 31))}
    return {"job": job, "statement": statement, "invoices": invoices,
            "transactions": transactions, "matches": matches,
            "recurring": recurring, "recurring_band": base_amt}


def build():
    """Return the four resolved tenant datasets + the global FX upserts."""
    datasets = []
    fx_rows = {}

    def add_fx(frm, to, d):
        if frm == to:
            return
        key = (frm, to, d)
        fx_rows[key] = {"from_currency": frm, "to_currency": to, "rate": rate_for(frm, to),
                        "effective_at": _utc_iso(date.fromisoformat(d)), "api_source": "seed"}

    for sme in SME_DEFS:
        rng = random.Random(uid("rng", sme["sme_id"]))
        accounts = _accounts(sme)
        primary = accounts[0]
        base = sme["base_ccy"]
        sme_id = sme["sme_id"]
        history = _build_history(sme, primary, rng)

        db_invoices, db_proofs, db_statements = [], [], []
        file_invoices, file_proofs, file_statements = [], [], []

        # ── DB current set: pending invoices + matching credits + noise. ──
        # Curated story per tenant; matching credits go in the primary (base ccy).
        db_match_txns = []        # (date, desc, credit_amt) to place into a statement
        n = 0

        def add_db_invoice_with_match(num, cp, ccy, amt, idate, due, desc,
                                      variance_pct=0.0, proof=None, tag=None):
            nonlocal n
            inv = _inv(sme_id, num, cp, ccy, amt, idate, due, tag=tag)
            db_invoices.append(inv)
            converted = round(amt * rate_for(ccy, base), 2)
            credit = round(converted * (1 + variance_pct / 100), 2)
            day = f"2026-06-{min(28, int(idate[-2:]) + 2):02d}"
            db_match_txns.append((day, desc, credit))
            add_fx(ccy, base, idate)
            if proof:
                db_proofs.append(proof(inv))
            n += 1
            return inv

        # Common clean multi-currency auto-matches (with proofs).
        add_db_invoice_with_match(
            f"{sme['slug'][:3].upper()}-201", "Globex Ltd", "USD", 6200.0,
            "2026-06-08", "2026-07-08", "INWARD TT GLOBEX LTD USD",
            variance_pct=-0.4,
            proof=lambda inv: _proof(sme_id, inv["invoice_id"], 6200.0, "USD",
                                     "2026-06-10", f"SWIFT-{sme['slug'][:3].upper()}-201",
                                     sender="Globex Ltd", bank="Citibank", account_number="GLBX-001"))
        add_db_invoice_with_match(
            f"{sme['slug'][:3].upper()}-202", "Crescent Trading Sdn Bhd", base, 7600.0,
            "2026-06-11", "2026-07-11", "DUITNOW CRESCENT TRADING",
            variance_pct=0.0,
            proof=lambda inv: _proof(sme_id, inv["invoice_id"], 7600.0, base,
                                     "2026-06-12", f"TRX-{sme['slug'][:3].upper()}-202",
                                     sender="Crescent Trading Sdn Bhd", bank="Maybank",
                                     account_number="CRES-77"))
        # Over-paid → escalate (variance beyond auto band, +4%).
        add_db_invoice_with_match(
            f"{sme['slug'][:3].upper()}-203", "Penang Foods", base, 6400.0,
            "2026-06-13", "2026-07-13", "IBG INWARD PENANG FOODS", variance_pct=4.0,
            tag="escalate_overpaid")
        # High-value, NO proof → B.2 verifier downgrade on run.
        add_db_invoice_with_match(
            f"{sme['slug'][:3].upper()}-204", "Continental Mining Bhd", "USD", 14000.0,
            "2026-06-09", "2026-07-09", "INWARD TT CONTINENTAL MINING USD",
            variance_pct=-0.3, tag="b2_high_value_no_proof")
        # Weak link: counterparty shares no words with the bank description → B.2.
        add_db_invoice_with_match(
            f"{sme['slug'][:3].upper()}-205", "Zephyr Holdings", base, 5300.0,
            "2026-06-14", "2026-07-14", "MISC INWARD CREDIT REF 88213",
            variance_pct=-0.2, tag="b2_weak_link")

        # Unmatched invoice (no transaction at all).
        db_invoices.append(_inv(sme_id, f"{sme['slug'][:3].upper()}-206", "Tokyo Trading",
                                "USD", 3200.0, "2026-06-20", "2026-07-20",
                                tag="unmatched_no_txn"))
        add_fx("USD", base, "2026-06-20")

        # Failed-parse invoice (UI red "Failed" pill): error_message, no fields.
        db_invoices.append({
            "invoice_id": uid("inv", sme_id, f"{sme['slug'][:3].upper()}-207"),
            "sme_id": sme_id, "invoice_number": f"{sme['slug'][:3].upper()}-207",
            "counterparty_name": None, "invoice_currency": None, "invoice_amount": None,
            "invoice_date": None, "due_date": None, "status": "pending",
            "error_message": "PDF parse error: No readable text found in PDF (scanned image).",
            "_tag": "failed_parse_invoice",
        })

        # ── Per-tenant special anomaly cases ──
        if sme["slug"] == "wzb_group":
            # B.3 duplicate invoice on the flagship tenant (double-billing).
            for k in (1, 2):
                add_db_invoice_with_match(
                    f"WZB-21{k}", "Selat Shipping Sdn Bhd", base, 5400.0,
                    f"2026-06-1{k}", "2026-07-15", f"DUITNOW SELAT SHIPPING {k}",
                    variance_pct=0.0, tag="duplicate_invoice")

        if sme["slug"] == "nusantara_logistics":
            # B.3 duplicate invoice: same counterparty + amount within 30 days.
            for k in (1, 2):
                add_db_invoice_with_match(
                    f"NUS-21{k}", "Harbour Freight Services", base, 4800.0,
                    f"2026-06-1{k}", "2026-07-15", f"DUITNOW HARBOUR FREIGHT {k}",
                    variance_pct=0.0, tag="duplicate_invoice")
            # B.3 amount outlier: way outside the recurring counterparty's history band.
            add_db_invoice_with_match(
                "NUS-220", history["recurring"], base, history["recurring_band"] * 6,
                "2026-06-16", "2026-07-16", f"INWARD {history['recurring'].upper()} LARGE",
                variance_pct=-0.2, tag="amount_outlier")

        if sme["slug"] == "selangor_textiles":
            # B.3 beneficiary mismatch: proof names a different paying party.
            inv = add_db_invoice_with_match(
                "SEL-230", "Dyeworks Ltd", "EUR", 4100.0, "2026-06-10", "2026-07-10",
                "SEPA INWARD DYEWORKS EUR", variance_pct=-0.5,
                proof=lambda inv: _proof(sme_id, inv["invoice_id"], 4100.0, "EUR",
                                         "2026-06-12", "SEPA-MISMATCH-1",
                                         sender="Unknown Shell Holdings", bank="Unknown Bank",
                                         account_number="ZZZ-999", tag="beneficiary_mismatch"))
            # Failed proof parse.
            file_anchor = db_invoices[0]
            db_proofs.append(_proof(sme_id, file_anchor["invoice_id"], None, None, None,
                                    "FAILED-PROOF-1", status="failed",
                                    error="Image OCR/parse error: unreadable scan.",
                                    tag="failed_parse_proof"))

        if sme["slug"] == "pearl_delta":
            # B.3 bank-detail change: same counterparty, two proofs, different account.
            # Distinct from the history "recurring" counterparty so it doesn't also
            # trip the (currency-naive) amount_outlier check.
            add_db_invoice_with_match(
                "PEA-240", "Sentosa Exports", "USD", 5000.0, "2026-06-06", "2026-07-06",
                "INWARD TT SENTOSA EXPORTS USD A", variance_pct=-0.3,
                proof=lambda inv: _proof(sme_id, inv["invoice_id"], 5000.0, "USD",
                                         "2026-06-07", "SENTOSA-OLD",
                                         sender="Sentosa Exports", bank="OCBC",
                                         account_number="SEN-1111", uploaded="2026-06-07"))
            add_db_invoice_with_match(
                "PEA-241", "Sentosa Exports", "USD", 5200.0, "2026-06-18", "2026-07-18",
                "INWARD TT SENTOSA EXPORTS USD B", variance_pct=-0.3,
                proof=lambda inv: _proof(sme_id, inv["invoice_id"], 5200.0, "USD",
                                         "2026-06-19", "SENTOSA-NEW",
                                         sender="Sentosa Exports", bank="HSBC",
                                         account_number="SEN-9999", uploaded="2026-06-19",
                                         tag="bank_detail_change"))

        # ── Assemble DB statements: matching credits + deterministic noise. ──
        # Primary account: matches + noise (≥10 rows). Secondary accounts: noise only.
        match_rows = [_match_txn(primary["account_id"], base, d, desc, amt)
                      for (d, desc, amt) in db_match_txns]
        noise_rows = [_noise_txn(primary["account_id"], base, rng,
                                 f"2026-06-{rng.randint(1, 27):02d}")
                      for _ in range(max(0, 12 - len(match_rows)))]
        db_statements.append({
            "statement_id": uid("dbstmt", sme_id, primary["account_id"], 0),
            "account_id": primary["account_id"], "file_type": "csv",
            "file_path": "seed://current-primary", "period_start": "2026-06-01",
            "period_end": "2026-06-28", "parse_status": "completed",
            "transactions": match_rows + noise_rows,
        })
        for ai, acct in enumerate(accounts[1:], start=1):
            rows = [_noise_txn(acct["account_id"], acct["currency_code"], rng,
                               f"2026-06-{rng.randint(1, 27):02d}") for _ in range(8)]
            db_statements.append({
                "statement_id": uid("dbstmt", sme_id, acct["account_id"], ai),
                "account_id": acct["account_id"], "file_type": "csv",
                "file_path": f"seed://current-{acct['currency_code'].lower()}",
                "period_start": "2026-06-01", "period_end": "2026-06-28",
                "parse_status": "completed", "transactions": rows,
            })

        # ── FILE set: a parallel, uploadable story (NOT seeded in the DB). ──
        # Two formats of statement + invoices (PDF/PNG) + proofs that reconcile
        # together once uploaded. Amounts converted to the primary base currency.
        file_specs = [
            # num, counterparty, ccy, amount, idate, due, inv_fmt, proof_ref, proof_fmt
            (f"F{sme['slug'][:3].upper()}-301", "Nimbus Technologies", "USD", 3250.0,
             "2026-06-21", "2026-07-21", "pdf", "SWIFT-USD-9920", "pdf"),
            (f"F{sme['slug'][:3].upper()}-302", "Hanseatic GmbH", "EUR", 1840.50,
             "2026-06-22", "2026-07-22", "pdf", "SEPA-7741", "png"),
            (f"F{sme['slug'][:3].upper()}-303", "Lion City Pte", "SGD", 8000.0,
             "2026-06-23", "2026-07-23", "png", "TT-LION-553", "pdf"),
            (f"F{sme['slug'][:3].upper()}-304", "Kuala Supplies", base, 9100.0,
             "2026-06-24", "2026-07-24", "pdf", "DN-KUALA-118", "pdf"),
            (f"F{sme['slug'][:3].upper()}-305", "Bremen GmbH", "EUR", 2600.0,
             "2026-06-25", "2026-07-25", "png", "SEPA-BREMEN-9", "png"),
        ]
        file_stmt_rows = []
        for (num, cp, ccy, amt, idate, due, ifmt, pref, pfmt) in file_specs:
            file_invoices.append({
                "invoice_number": num, "counterparty": cp, "currency": ccy, "amount": amt,
                "invoice_date": idate, "due_date": due, "format": ifmt,
                "expected_credit_base": round(amt * rate_for(ccy, base), 2),
            })
            converted = round(amt * rate_for(ccy, base), 2)
            file_proofs.append({
                "reference": pref, "amount": amt, "currency": ccy, "date": idate,
                "corroborates_invoice": num, "format": pfmt, "sender": cp,
            })
            file_stmt_rows.append({"date": idate, "description": f"INWARD {cp.upper()} {ccy}",
                                   "credit": converted})
            add_fx(ccy, base, idate)

        # Statement files: one ISO/signed CSV, one dd/mm/yyyy CSV, one debit/credit XLSX.
        file_statements = [
            {"filename": "statement_primary_iso.csv", "format": "csv_signed",
             "account_id": primary["account_id"], "currency": base,
             "role": "reconciliation driver for the file invoices (ISO date, signed amount)",
             "rows": file_stmt_rows},
            {"filename": "statement_ddmmyyyy.csv", "format": "csv_ddmmyyyy",
             "account_id": primary["account_id"], "currency": base,
             "role": "format coverage: dd/mm/yyyy dates + noise only",
             "rows": [{"date": "05/06/2026", "description": "OFFICE RENT TENANCY", "credit": -3200.0},
                      {"date": "09/06/2026", "description": "FPX ONLINE TRANSFER", "credit": 1820.0},
                      {"date": "14/06/2026", "description": "MONTHLY SERVICE CHARGE", "credit": -38.0}]},
            {"filename": "statement_debit_credit.xlsx", "format": "xlsx_debit_credit",
             "account_id": accounts[1]["account_id"], "currency": accounts[1]["currency_code"],
             "role": "format coverage: split debit/credit columns (xlsx)",
             "rows": [{"date": "2026-06-07", "description": "INWARD TT REFUND", "debit": 0.0, "credit": 1450.0},
                      {"date": "2026-06-12", "description": "CARD SETTLEMENT", "debit": 990.0, "credit": 0.0},
                      {"date": "2026-06-19", "description": "INTEREST CREDIT", "debit": 0.0, "credit": 22.5}]},
        ]

        datasets.append({
            "sme": {k: sme[k] for k in ("sme_id", "slug", "company_name", "registration_no",
                                        "email", "phone", "country_code", "base_ccy")},
            "accounts": accounts, "history": history,
            "db": {"statements": db_statements, "invoices": db_invoices, "proofs": db_proofs},
            "files": {"statements": file_statements, "invoices": file_invoices,
                      "proofs": file_proofs},
        })

    return {"datasets": datasets, "fx": list(fx_rows.values()), "password": DEMO_PASSWORD}


if __name__ == "__main__":
    data = build()
    for ds in data["datasets"]:
        s = ds["sme"]
        n_txn = sum(len(st["transactions"]) for st in ds["db"]["statements"])
        print(f"{s['company_name']:30} {s['email']:32} "
              f"acct={len(ds['accounts'])} histM={len(ds['history']['matches'])} "
              f"dbInv={len(ds['db']['invoices'])} dbTxn={n_txn} dbProof={len(ds['db']['proofs'])} "
              f"fileInv={len(ds['files']['invoices'])} fileProof={len(ds['files']['proofs'])} "
              f"fileStmt={len(ds['files']['statements'])}")
    print("FX upserts:", len(data["fx"]))
