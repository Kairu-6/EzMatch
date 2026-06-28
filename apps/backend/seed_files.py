"""
seed_files.py — (re)generate the uploadable test_files set + sme_infos manifest
===============================================================================
Companion to seed_demo.py. Writes the "file half" of the demo dataset (the ≈ half
of documents NOT pre-seeded in the DB) as real, parseable upload files, organised
per tenant, plus a `sme_infos` manifest recording who owns what, the demo logins,
which documents are pre-seeded vs file-only, and the expected reconciliation.

Uploading these exercises the real parse pipeline end-to-end without duplicating
anything already in the database:
  • bank statements — CSV (ISO + signed amount), CSV (dd/mm/yyyy), XLSX (debit/credit)
  • invoices        — PDF (PyMuPDF text → Morpheus) and PNG (Tesseract OCR → Morpheus)
  • payment proofs  — PDF and PNG

Run (backend venv):
  cd apps/backend && PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe seed_files.py
"""
import csv
import json
import os
import shutil

import fitz  # PyMuPDF
import pandas as pd

import seed_data

TEST_FILES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "test_files"))


# ── document renderers ─────────────────────────────────────────────
def _render_lines(lines: list[str], path: str, as_png: bool) -> None:
    doc = fitz.open()
    page = doc.new_page()
    y = 64
    for ln in lines:
        page.insert_text((60, y), ln, fontsize=13 if ln and ln[0] != " " else 11)
        y += 22
    if as_png:
        page.get_pixmap(dpi=150).save(path)
    else:
        doc.save(path)
    doc.close()


def _invoice_lines(inv: dict, sme: dict) -> list[str]:
    return [
        sme["company_name"],
        "TAX INVOICE",
        "",
        f"Invoice Number: {inv['invoice_number']}",
        f"Billed To: {inv['counterparty']}",
        f"Invoice Date: {inv['invoice_date']}",
        f"Due Date: {inv['due_date']}",
        "",
        "Description: Professional services rendered",
        f"Total Amount Due: {inv['currency']} {inv['amount']:,.2f}",
        "",
        f"Please remit {inv['currency']} {inv['amount']:,.2f} by {inv['due_date']}.",
    ]


def _proof_lines(p: dict) -> list[str]:
    return [
        "PAYMENT ADVICE / REMITTANCE RECEIPT",
        "",
        f"Reference: {p['reference']}",
        f"Payment Date: {p['date']}",
        f"Amount Paid: {p['currency']} {p['amount']:,.2f}",
        f"Paying Party: {p['sender']}",
        "Remitting Bank: International Settlement Bank",
        "",
        f"This confirms payment of {p['currency']} {p['amount']:,.2f}.",
    ]


def _write_statement(stmt: dict, path: str) -> None:
    fmt = stmt["format"]
    rows = stmt["rows"]
    if fmt == "xlsx_debit_credit":
        df = pd.DataFrame([{"Date": r["date"], "Description": r["description"],
                            "Debit": r.get("debit", 0.0), "Credit": r.get("credit", 0.0)}
                           for r in rows])
        df.to_excel(path, index=False, engine="openpyxl")
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Description", "Amount"])
        for r in rows:
            w.writerow([r["date"], r["description"], f"{r['credit']:.2f}"])


# ── manifest ───────────────────────────────────────────────────────
def _acct_label(accounts: list[dict], account_id: str) -> dict:
    a = next((x for x in accounts if x["account_id"] == account_id), accounts[0])
    return {"account_id": a["account_id"], "bank_name": a["bank_name"],
            "account_number": a["account_number"], "currency_code": a["currency_code"]}


def main() -> None:
    data = seed_data.build()
    password = data["password"]

    if os.path.isdir(TEST_FILES):
        shutil.rmtree(TEST_FILES)
    os.makedirs(TEST_FILES, exist_ok=True)

    manifest = []
    counts = {"statements": 0, "invoices": 0, "proofs": 0}

    for ds in data["datasets"]:
        sme = ds["sme"]
        slug = sme["slug"]
        base = os.path.join(TEST_FILES, slug)
        for sub in ("bank_statements", "invoices", "payment_proofs"):
            os.makedirs(os.path.join(base, sub), exist_ok=True)

        # statements
        stmt_entries = []
        for stmt in ds["files"]["statements"]:
            rel = f"{slug}/bank_statements/{stmt['filename']}"
            _write_statement(stmt, os.path.join(TEST_FILES, rel))
            stmt_entries.append({"file": rel, "format": stmt["format"],
                                 "upload_to_account": _acct_label(ds["accounts"], stmt["account_id"]),
                                 "role": stmt["role"]})
            counts["statements"] += 1

        # invoices
        inv_entries = []
        for inv in ds["files"]["invoices"]:
            ext = inv["format"]
            fname = f"invoice_{inv['invoice_number']}.{ext}"
            rel = f"{slug}/invoices/{fname}"
            _render_lines(_invoice_lines(inv, sme), os.path.join(TEST_FILES, rel),
                          as_png=(ext == "png"))
            inv_entries.append({"file": rel, "invoice_number": inv["invoice_number"],
                                "counterparty": inv["counterparty"], "amount": inv["amount"],
                                "currency": inv["currency"], "invoice_date": inv["invoice_date"],
                                "expected_credit_in_base": inv["expected_credit_base"],
                                "parser": "PyMuPDF+Morpheus" if ext == "pdf" else "Tesseract+Morpheus"})
            counts["invoices"] += 1

        # proofs
        proof_entries = []
        for p in ds["files"]["proofs"]:
            ext = p["format"]
            fname = f"proof_{p['reference']}.{ext}"
            rel = f"{slug}/payment_proofs/{fname}"
            _render_lines(_proof_lines(p), os.path.join(TEST_FILES, rel), as_png=(ext == "png"))
            proof_entries.append({"file": rel, "reference": p["reference"], "amount": p["amount"],
                                  "currency": p["currency"], "corroborates_invoice": p["corroborates_invoice"],
                                  "parser": "PyMuPDF+Morpheus" if ext == "pdf" else "Tesseract+Morpheus"})
            counts["proofs"] += 1

        # pre-seeded summary (what already lives in the DB for this tenant)
        db = ds["db"]
        n_db_txn = sum(len(s["transactions"]) for s in db["statements"])
        edge = sorted({i["_tag"] for i in db["invoices"] if i.get("_tag")} |
                      {p["_tag"] for p in db["proofs"] if p.get("_tag")})

        manifest.append({
            "sme_id": sme["sme_id"],
            "company_name": sme["company_name"],
            "registration_no": sme["registration_no"],
            "country_code": sme["country_code"],
            "base_currency": sme["base_ccy"],
            "login": {"email": sme["email"], "password": password,
                      "note": "email pre-confirmed by the reseed; password shared across all demo tenants"},
            "bank_accounts": [
                {"account_id": a["account_id"], "bank_name": a["bank_name"],
                 "account_number": a["account_number"], "currency_code": a["currency_code"],
                 "is_primary": a["is_primary"]} for a in ds["accounts"]],
            "preseeded_in_db": {
                "note": "Already loaded by seed_demo.py — do NOT upload these; they are the live "
                        "reconcile/verify/anomaly demo plus a historical reconciled job.",
                "historical_matches": len(ds["history"]["matches"]),
                "current_pending_invoices": len([i for i in db["invoices"]]),
                "transactions": n_db_txn,
                "payment_proofs": len(db["proofs"]),
                "edge_cases_present": edge,
            },
            "file_uploads": {
                "note": "NOT in the DB — upload these to exercise the parse pipeline, then run "
                        "reconciliation. Statements go to the noted account.",
                "bank_statements": stmt_entries,
                "invoices": inv_entries,
                "payment_proofs": proof_entries,
            },
            "dependency_chains": {
                "bank": "bank_transaction.statement_id -> bank_statement.account_id -> bank_account.sme_id -> sme",
                "invoice": "invoice.sme_id -> sme",
                "proof": "payment_proof.sme_id -> sme ; payment_proof.invoice_id -> invoice",
                "match": "reconciliation_match.job_id -> reconciliation_job.sme_id -> sme",
            },
        })

    with open(os.path.join(TEST_FILES, "sme_infos"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    with open(os.path.join(TEST_FILES, "README.md"), "w", encoding="utf-8") as f:
        f.write(_readme(data, counts))

    print(f"Wrote test_files for {len(manifest)} tenants -> {TEST_FILES}")
    print(f"  {counts['statements']} statements · {counts['invoices']} invoices · "
          f"{counts['proofs']} proofs + sme_infos + README.md")


def _readme(data, counts) -> str:
    lines = [
        "# test_files — uploadable demo documents",
        "",
        "These are the **file half** of the demo dataset: documents that are NOT pre-seeded",
        "in the database. Upload them through the app to exercise the real parse pipeline,",
        "then run reconciliation. The pre-seeded half (live reconcile/verify/anomaly demo +",
        "a historical reconciled job per tenant) is loaded by `apps/backend/seed_demo.py`.",
        "",
        "Regenerate everything: run `seed_demo.py` (DB) then `seed_files.py` (these files).",
        "",
        "`sme_infos` (JSON) is the authoritative manifest: per-tenant logins, bank accounts,",
        "what is pre-seeded vs file-only, and each upload's expected reconciliation.",
        "",
        f"Demo password (all four logins): `{data['password']}`",
        "",
        "## Tenants",
        "",
    ]
    for ds in data["datasets"]:
        s = ds["sme"]
        lines.append(f"- **{s['company_name']}** (`{s['base_ccy']}`) — {s['email']} — folder `{s['slug']}/`")
    lines += ["", f"Totals: {counts['statements']} statements · {counts['invoices']} invoices · "
              f"{counts['proofs']} proofs across {len(data['datasets'])} tenants.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
