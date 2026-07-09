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
def _render_invoice(inv: dict, sme: dict, path: str, as_png: bool) -> None:
    doc = fitz.open()
    page = doc.new_page()
    
    # Header background (Dark Blue)
    page.draw_rect(fitz.Rect(0, 0, page.rect.width, 80), color=(0.1, 0.2, 0.4), fill=(0.1, 0.2, 0.4))
    page.insert_text((50, 50), "TAX INVOICE", fontname="hebo", fontsize=24, color=(1, 1, 1))
    page.insert_text((page.rect.width - 250, 50), sme["company_name"], fontname="helv", fontsize=14, color=(1, 1, 1))
    
    # Invoice Details
    page.insert_text((50, 120), f"Invoice Number:", fontname="hebo", fontsize=11)
    page.insert_text((150, 120), f"{inv['invoice_number']}", fontname="helv", fontsize=11)
    page.insert_text((50, 140), f"Invoice Date:", fontname="hebo", fontsize=11)
    page.insert_text((150, 140), f"{inv['invoice_date']}", fontname="helv", fontsize=11)
    page.insert_text((50, 160), f"Due Date:", fontname="hebo", fontsize=11)
    page.insert_text((150, 160), f"{inv['due_date']}", fontname="helv", fontsize=11)
    
    # Billed To
    page.insert_text((page.rect.width - 250, 120), "Billed To:", fontname="hebo", fontsize=11)
    page.insert_text((page.rect.width - 250, 140), inv["counterparty"], fontname="helv", fontsize=11)
    
    # Table Header (Light Grey)
    page.draw_rect(fitz.Rect(50, 200, page.rect.width - 50, 220), color=(0.9, 0.9, 0.9), fill=(0.9, 0.9, 0.9))
    page.insert_text((60, 214), "Description", fontname="hebo", fontsize=11)
    page.insert_text((page.rect.width - 150, 214), "Amount", fontname="hebo", fontsize=11)
    
    # Table Row
    page.insert_text((60, 240), "Professional services rendered", fontname="helv", fontsize=11)
    page.insert_text((page.rect.width - 150, 240), f"{inv['currency']} {inv['amount']:,.2f}", fontname="helv", fontsize=11)
    
    # Total Footer
    page.draw_line((50, 260), (page.rect.width - 50, 260), color=(0, 0, 0), width=1.5)
    page.insert_text((page.rect.width - 300, 280), "Total Amount Due:", fontname="hebo", fontsize=12)
    page.insert_text((page.rect.width - 150, 280), f"{inv['currency']} {inv['amount']:,.2f}", fontname="hebo", fontsize=12)
    
    # Payment Instructions
    page.insert_text((50, 340), f"Please remit {inv['currency']} {inv['amount']:,.2f} by {inv['due_date']}.", fontname="helv", fontsize=10, color=(0.3, 0.3, 0.3))

    if as_png:
        page.get_pixmap(dpi=150).save(path)
    else:
        doc.save(path)
    doc.close()


def _render_proof(p: dict, path: str, as_png: bool) -> None:
    doc = fitz.open()
    rail = p.get("rail")
    
    # DuitNow/FPX mobile receipt shape
    is_mobile = rail in ["DuitNow", "FPX"]
    width = 400 if is_mobile else 595
    height = 700 if is_mobile else 842
    
    page = doc.new_page(width=width, height=height)
    
    if is_mobile:
        # Mobile receipt style (centered, distinct colors)
        color = (0.8, 0.1, 0.4) if rail == "DuitNow" else (0.1, 0.3, 0.7)
        page.draw_rect(fitz.Rect(0, 0, width, 100), color=color, fill=color)
        page.insert_text((width/2 - 50, 40), rail, fontname="hebo", fontsize=24, color=(1, 1, 1))
        page.insert_text((width/2 - 70, 70), "Payment Successful", fontname="helv", fontsize=14, color=(1, 1, 1))
        
        # Amount centered
        page.insert_text((width/2 - 70, 160), f"{p['currency']} {p['amount']:,.2f}", fontname="hebo", fontsize=22, color=(0, 0, 0))
        
        y = 220
        def add_row(lbl, val):
            nonlocal y
            page.insert_text((40, y), lbl, fontname="helv", fontsize=11, color=(0.4, 0.4, 0.4))
            page.insert_text((40, y + 20), str(val), fontname="hebo", fontsize=12, color=(0, 0, 0))
            page.draw_line((40, y+35), (width - 40, y+35), color=(0.9, 0.9, 0.9), width=1)
            y += 50
            
        add_row("Reference Number", p['reference'])
        if p.get("recipient_reference"):
            add_row("Recipient Reference", p['recipient_reference'])
        add_row("Date", p['date'])
        add_row("Beneficiary Name", p['sender'])
            
    else:
        # Standard Wire/TT style
        header = f"{rail.upper()} TRANSFER RECEIPT" if rail else "PAYMENT ADVICE"
        # Header background (Green for receipt)
        page.draw_rect(fitz.Rect(0, 0, page.rect.width, 80), color=(0.1, 0.5, 0.2), fill=(0.1, 0.5, 0.2))
        page.insert_text((50, 50), header, fontname="hebo", fontsize=20, color=(1, 1, 1))
        page.insert_text((page.rect.width - 250, 50), "Int'l Settlement Bank", fontname="helv", fontsize=14, color=(1, 1, 1))
        
        y = 120
        def add_row(lbl, val):
            nonlocal y
            page.insert_text((50, y), lbl, fontname="hebo", fontsize=11)
            page.insert_text((200, y), str(val), fontname="helv", fontsize=11)
            page.draw_line((50, y+5), (page.rect.width - 50, y+5), color=(0.9, 0.9, 0.9), width=1)
            y += 25

        if rail:
            add_row("Payment Rail:", rail)
            add_row(f"{rail} Ref No:", p['reference'])
        else:
            add_row("Reference:", p['reference'])
            
        if p.get("recipient_reference"):
            add_row("Recipient Reference:", p['recipient_reference'])
            
        add_row("Payment Date:", p['date'])
        add_row("Amount Paid:", f"{p['currency']} {p['amount']:,.2f}")
        add_row("Paying Party:", p['sender'])
        
        # "Stamp" style confirmation
        y += 20
        page.draw_rect(fitz.Rect(50, y, page.rect.width - 50, y + 40), color=(0.9, 0.95, 0.9), fill=(0.9, 0.95, 0.9))
        page.insert_text((60, y + 25), f"CONFIRMED: Payment of {p['currency']} {p['amount']:,.2f} processed successfully.", fontname="hebo", fontsize=10, color=(0.1, 0.5, 0.2))

    if as_png:
        page.get_pixmap(dpi=150).save(path)
    else:
        doc.save(path)
    doc.close()


def _write_statement(stmt: dict, path: str) -> None:
    fmt = stmt["format"]
    rows = stmt["rows"]
    if fmt == "xlsx_debit_credit":
        df = pd.DataFrame([{"Date": r["date"], "Description": r["description"],
                            "Debit": r.get("debit", 0.0), "Credit": r.get("credit", 0.0)}
                           for r in rows])
        df.to_excel(path, index=False, engine="openpyxl")
        return
    # Emit a Reference column when any row carries a recipient reference (the
    # DuitNow/FPX recon key) so uploading exercises reference extraction + matching.
    has_ref = any(r.get("reference") for r in rows)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if has_ref:
            w.writerow(["Date", "Description", "Reference", "Amount"])
            for r in rows:
                w.writerow([r["date"], r["description"], r.get("reference") or "", f"{r['credit']:.2f}"])
        else:
            w.writerow(["Date", "Description", "Amount"])
            for r in rows:
                w.writerow([r["date"], r["description"], f"{r['credit']:.2f}"])


# ── invalid files (failure-path coverage for the upload validators) ─────────────
def _write_invalid_files(root: str) -> list[dict]:
    """Deliberately broken uploads so the demo can show honest parse-failure states.
    Returns manifest entries documenting the expected rejection for each."""
    d = os.path.join(root, "_invalid")
    os.makedirs(d, exist_ok=True)
    # Not a real PDF (PyMuPDF can't open it) — upload as an invoice/proof.
    with open(os.path.join(d, "corrupt.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 this is not actually a valid pdf body \x00\x01\x02 garbage")
    # Empty statement (no rows).
    open(os.path.join(d, "empty.csv"), "w", encoding="utf-8").close()
    # Headers the statement parser can't map to date/description/amount.
    with open(os.path.join(d, "bad_schema.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["foo", "bar", "baz"])
        w.writerow(["1", "2", "3"])
        w.writerow(["4", "5", "6"])
    # Unsupported file type for any uploader.
    with open(os.path.join(d, "unsupported.txt"), "w", encoding="utf-8") as f:
        f.write("just some plain text, not a statement/invoice/proof")
    return [
        {"file": "_invalid/corrupt.pdf", "upload_as": "invoice or payment_proof",
         "expected": "parse fails → red 'Failed' pill + error_message (no readable text)"},
        {"file": "_invalid/empty.csv", "upload_as": "bank statement",
         "expected": "parse yields zero transactions → rejected / empty statement"},
        {"file": "_invalid/bad_schema.csv", "upload_as": "bank statement",
         "expected": "no mappable date/amount columns → parse error"},
        {"file": "_invalid/unsupported.txt", "upload_as": "any",
         "expected": "unsupported file type → upload rejected"},
    ]


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
            _render_invoice(inv, sme, os.path.join(TEST_FILES, rel),
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
            _render_proof(p, os.path.join(TEST_FILES, rel), as_png=(ext == "png"))
            proof_entries.append({"file": rel, "reference": p["reference"], "amount": p["amount"],
                                  "currency": p["currency"], "corroborates_invoice": p["corroborates_invoice"],
                                  "rail": p.get("rail"), "recipient_reference": p.get("recipient_reference"),
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

    invalid_entries = _write_invalid_files(TEST_FILES)

    with open(os.path.join(TEST_FILES, "sme_infos"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Ground-truth baseline for eval_recon.py — expected correct/false outcome per
    # pre-seeded invoice, keyed on the deterministic seed ids that land in the DB.
    exp = data["expectations"]
    tiers = {}
    for e in exp:
        tiers[e["tier"]] = tiers.get(e["tier"], 0) + 1
    with open(os.path.join(TEST_FILES, "expected_reconciliation.json"), "w", encoding="utf-8") as f:
        json.dump({
            "sme_id": data["datasets"][0]["sme"]["sme_id"],
            "note": "Ground truth for the pre-seeded set. Run reconciliation for this sme, "
                    "then `python eval_recon.py` scores actual matches against expected_* here. "
                    "Accuracy is deliberately < 100% (see the D/E tiers).",
            "time_model": data["time_model"],
            "tier_counts": dict(sorted(tiers.items())),
            "expectations": exp,
        }, f, indent=2, ensure_ascii=False)

    with open(os.path.join(TEST_FILES, "README.md"), "w", encoding="utf-8") as f:
        f.write(_readme(data, counts, invalid_entries))

    print(f"Wrote test_files for {len(manifest)} tenant(s) -> {TEST_FILES}")
    print(f"  {counts['statements']} statements · {counts['invoices']} invoices · "
          f"{counts['proofs']} proofs · {len(invalid_entries)} invalid files")
    print(f"  + sme_infos + expected_reconciliation.json ({len(exp)} scored invoices) + README.md")


def _readme(data, counts, invalid_entries) -> str:
    s = data["datasets"][0]["sme"]
    lines = [
        "# test_files — uploadable demo documents",
        "",
        "These are the **file quarter** of the demo dataset: documents that are NOT pre-seeded",
        "in the database. Upload them through the app to exercise the real parse pipeline,",
        "then run reconciliation. The pre-seeded bulk (live reconcile/verify/anomaly demo +",
        "a historical reconciled job) is loaded by `apps/backend/seed_demo.py`.",
        "",
        "Regenerate everything: run `seed_demo.py` (DB) then `seed_files.py` (these files).",
        "",
        "`sme_infos` (JSON) is the authoritative manifest: login, bank accounts, what is",
        "pre-seeded vs file-only, and each upload's expected reconciliation.",
        "`expected_reconciliation.json` is the ground-truth baseline (per pre-seeded invoice)",
        "that `eval_recon.py` scores a real reconcile run against.",
        "",
        f"Demo login: **{s['email']}** · password `{data['password']}`",
        "",
        f"## Tenant: {s['company_name']} (`{s['base_ccy']}`)",
        "",
        f"Folder `{s['slug']}/` — {counts['statements']} statements · {counts['invoices']} invoices · "
        f"{counts['proofs']} proofs.",
        "",
        "## Invalid files (`_invalid/`) — failure-path coverage",
        "",
        "Upload these to show honest parse-failure/validation states:",
        "",
    ]
    for e in invalid_entries:
        lines.append(f"- `{e['file']}` (upload as {e['upload_as']}) → {e['expected']}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
