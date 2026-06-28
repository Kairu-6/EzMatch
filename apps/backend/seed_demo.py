"""
seed_demo.py — full multi-tenant idempotent reseed
===================================================
Rewrites the database into a clean, demoable, MULTI-TENANT state: four SMEs, each
with three bank accounts, a completed historical reconciliation job, a pre-seeded
"current" set ready to reconcile, and payment proofs — covering every Phase-A/B
code path and edge case (see seed_data.py).

It is **idempotent**: every id is derived deterministically (uuid5), so re-running
replaces in place. It is also **destructive by design** — it wipes ALL tenant data
and prunes stray Supabase Auth users, leaving exactly the four demo logins.

The "other half" of the documents (≈ half the invoices/proofs/statements) is NOT
seeded here — those ship as uploadable files under test_files/ (run seed_files.py).

Run (backend venv):
  cd apps/backend && PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe seed_demo.py

Demo logins (all share the password in seed_data.DEMO_PASSWORD):
  finance@wzbgroup.my · ops@nusantara-logistics.my ·
  finance@selangortextiles.my · accounts@pearldelta.sg
"""
import os

from dotenv import load_dotenv
from supabase import create_client

import seed_data

load_dotenv()
db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_API_KEY"])

# Tables wiped on every run, in FK-safe (child → parent) order, with the PK used
# to match "all rows" (PostgREST requires a filter on delete).
_WIPE = [
    ("reconciliation_match", "match_id", "uuid"),
    ("reconciliation_log", "log_id", "uuid"),
    ("recommendation", "recommendation_id", "uuid"),
    ("reconciliation_job", "job_id", "uuid"),
    ("payment_proof", "proof_id", "uuid"),
    ("bank_transaction", "transaction_id", "text"),
    ("bank_statement", "statement_id", "uuid"),
    ("invoice", "invoice_id", "uuid"),
    ("bank_account", "account_id", "uuid"),
    ("sme", "sme_id", "uuid"),
]
_UUID_SENTINEL = "00000000-0000-0000-0000-000000000000"


def wipe_all() -> None:
    for table, pk, kind in _WIPE:
        sentinel = _UUID_SENTINEL if kind == "uuid" else "__seed_none__"
        db.table(table).delete().neq(pk, sentinel).execute()
    print("Wiped all tenant data.")


def _list_users() -> list:
    res = db.auth.admin.list_users()
    return res if isinstance(res, list) else getattr(res, "users", []) or []


def prune_and_provision_users(target_emails: set[str]) -> dict[str, str]:
    """Delete auth users not in the demo set; ensure each demo email exists with the
    documented password and a confirmed email. Returns email → user_id."""
    existing = {(u.email or "").lower(): u.id for u in _list_users()}

    # Prune strays (anything not a demo login).
    for u in _list_users():
        if (u.email or "").lower() not in target_emails:
            try:
                db.auth.admin.delete_user(u.id)
                print(f"  pruned stray auth user: {u.email}")
            except Exception as exc:
                print(f"  WARN could not delete {u.email}: {exc}")

    ids: dict[str, str] = {}
    for email in sorted(target_emails):
        uid = existing.get(email)
        if uid:
            try:
                db.auth.admin.update_user_by_id(
                    uid, {"password": seed_data.DEMO_PASSWORD, "email_confirm": True})
            except Exception as exc:
                print(f"  WARN could not update {email}: {exc}")
        else:
            created = db.auth.admin.create_user({
                "email": email, "password": seed_data.DEMO_PASSWORD, "email_confirm": True})
            uid = created.user.id
            print(f"  created auth user: {email}")
        ids[email] = uid
    return ids


def _strip(row: dict) -> dict:
    """Drop internal helper keys (anything starting with '_') and nested children."""
    return {k: v for k, v in row.items() if not k.startswith("_") and k != "transactions"}


def main() -> None:
    data = seed_data.build()
    datasets = data["datasets"]
    target_emails = {ds["sme"]["email"].lower() for ds in datasets}

    print("== Reseeding (idempotent, destructive) ==")
    wipe_all()

    # FX cache (upsert — exchange_rate is global, never wiped).
    for r in data["fx"]:
        db.table("exchange_rate").upsert(
            r, on_conflict="from_currency,to_currency,effective_at,api_source").execute()
    print(f"Upserted {len(data['fx'])} FX rates.")

    # Provision auth users AFTER smes are inserted so the handle_new_user trigger
    # claims our unclaimed rows — but we insert smes with user_id NULL first.
    sme_rows = []
    for ds in datasets:
        s = ds["sme"]
        sme_rows.append({
            "sme_id": s["sme_id"], "company_name": s["company_name"],
            "registration_no": s["registration_no"], "email": s["email"],
            "phone": s["phone"], "country_code": s["country_code"], "user_id": None,
        })
    db.table("sme").insert(sme_rows).execute()

    user_ids = prune_and_provision_users(target_emails)

    # Re-assert linkage + clean any trigger-created stray sme rows.
    target_ids = {ds["sme"]["sme_id"] for ds in datasets}
    for ds in datasets:
        s = ds["sme"]
        db.table("sme").update({"user_id": user_ids[s["email"].lower()]}) \
          .eq("sme_id", s["sme_id"]).execute()
    strays = [r["sme_id"] for r in db.table("sme").select("sme_id").execute().data
              if r["sme_id"] not in target_ids]
    if strays:
        db.table("sme").delete().in_("sme_id", strays).execute()
        print(f"  removed {len(strays)} trigger-created stray sme row(s).")

    totals = {"accounts": 0, "statements": 0, "transactions": 0,
              "invoices": 0, "proofs": 0, "matches": 0}

    for ds in datasets:
        s = ds["sme"]
        db.table("bank_account").insert(ds["accounts"]).execute()
        totals["accounts"] += len(ds["accounts"])

        # ── historical job (B.1 manual exemplars + B.3 baselines) ──
        h = ds["history"]
        db.table("bank_statement").insert(h["statement"]).execute()
        db.table("invoice").insert([_strip(i) for i in h["invoices"]]).execute()
        if h["transactions"]:
            for t in h["transactions"]:
                t["statement_id"] = h["statement"]["statement_id"]
            db.table("bank_transaction").insert(h["transactions"]).execute()
        db.table("reconciliation_job").insert(h["job"]).execute()
        db.table("reconciliation_match").insert(h["matches"]).execute()
        totals["statements"] += 1
        totals["transactions"] += len(h["transactions"])
        totals["invoices"] += len(h["invoices"])
        totals["matches"] += len(h["matches"])

        # ── current pre-seeded set (live reconcile/verify/anomaly demo) ──
        if ds["db"]["invoices"]:
            db.table("invoice").insert([_strip(i) for i in ds["db"]["invoices"]]).execute()
            totals["invoices"] += len(ds["db"]["invoices"])
        for st in ds["db"]["statements"]:
            db.table("bank_statement").insert(_strip(st)).execute()
            if st["transactions"]:
                for t in st["transactions"]:
                    t["statement_id"] = st["statement_id"]
                db.table("bank_transaction").insert(st["transactions"]).execute()
                totals["transactions"] += len(st["transactions"])
            totals["statements"] += 1
        if ds["db"]["proofs"]:
            db.table("payment_proof").insert([_strip(p) for p in ds["db"]["proofs"]]).execute()
            totals["proofs"] += len(ds["db"]["proofs"])

        print(f"  seeded {s['company_name']}")

    print("\n== Done ==")
    print(f"  4 SMEs · {totals['accounts']} accounts · {totals['statements']} statements · "
          f"{totals['transactions']} transactions")
    print(f"  {totals['invoices']} invoices · {totals['proofs']} proofs · "
          f"{totals['matches']} historical matches")
    print(f"  Logins (password '{seed_data.DEMO_PASSWORD}'): " +
          ", ".join(sorted(target_emails)))
    print("  Next: run seed_files.py to (re)generate the uploadable test_files set.")


if __name__ == "__main__":
    main()
