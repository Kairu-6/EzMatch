"""
agent/verifier.py
=================
Phase B.2 — the verification layer. The per-match `gate` governs each proposal in
isolation; the verifier re-examines the whole run for problems only visible
*across* matches or *after* the fact:

  - an auto-commit of real value with NO corroborating payment proof,
  - a match whose counterparty shares NO words with the bank description,
  - the same transaction claimed by more than one invoice,
  - an obvious match the agent left on the table.

Like the gate, the verifier is deterministic, auditable Python — not the model.
On the automatic post-loop pass (`apply=True`) it can DOWNGRADE a risky
auto-commit to `pending_review` so a human reviews it in /audit; on the tool path
(`apply=False`) it mutates nothing and just returns findings for the agent to
self-critique over.
"""
import logging
import os
import re

from agent import gate

logger = logging.getLogger(__name__)

# Converted-amount above which an auto-commit with no payment proof is treated as
# risky and downgraded for human review.
VERIFY_PROOF_VALUE      = float(os.getenv("VERIFY_PROOF_VALUE", "50000"))
# Master switch for the governed downgrade action.
VERIFY_ENABLE_DOWNGRADE = os.getenv("VERIFY_ENABLE_DOWNGRADE", "true").lower() == "true"

_STOPWORDS = {"the", "sdn", "bhd", "ltd", "llc", "inc", "co", "corp", "company",
              "pte", "plc", "group", "and", "for", "payment", "transfer", "to",
              "from", "ref"}


def _tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens of length >=3, minus generic company words."""
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower())
            if len(t) >= 3 and t not in _STOPWORDS}


def run_verification(db, job_id, sme_id, ctx, mem, *, apply: bool) -> dict:
    """
    Inspect every match this job wrote and (when apply=True) downgrade the risky
    ones. Returns {findings, checked, downgraded, warnings, missed}. Advisory when
    apply=False. The runner calls this in a try/except — it must never raise into
    the loop, but we keep it defensive anyway.
    """
    rows = (db.table("reconciliation_match")
              .select("match_id, invoice_id, transaction_id, proof_id, match_status, "
                      "match_confidence, converted_amount, variance_pct, "
                      "invoice(counterparty_name, invoice_number)")
              .eq("job_id", job_id).execute().data) or []

    txn_map = ctx.get("txn_map") or {}
    inv_map = ctx.get("inv_map") or {}
    matched_ids = ctx.get("matched_ids") or set()

    findings: list[dict] = []
    seen_txn: dict[str, str] = {}   # transaction_id -> first invoice_number seen

    for r in rows:
        inv = r.get("invoice") or {}
        inv_no = inv.get("invoice_number") or "?"
        status = r.get("match_status")
        txn_id = r.get("transaction_id") or ""

        def finding(code, severity, detail, **extra):
            findings.append({"match_id": r.get("match_id"), "invoice_id": r.get("invoice_id"),
                             "invoice_number": inv_no, "match_status": status,
                             "code": code, "severity": severity, "detail": detail, **extra})

        # 1. Unsupported high-value auto-commit.
        if (status == "auto" and not r.get("proof_id")
                and (r.get("converted_amount") or 0) >= VERIFY_PROOF_VALUE):
            finding("no_proof", "risk",
                    f"auto-committed {r.get('converted_amount'):.0f} with no payment proof")

        # 2. Weak semantic link (only judgeable if we still have the txn in memory).
        if status == "auto":
            txn = txn_map.get(txn_id)
            if txn is not None:
                overlap = _tokens(inv.get("counterparty_name")) & _tokens(txn.description_normalised)
                if not overlap:
                    finding("weak_link", "risk",
                            f"counterparty '{inv.get('counterparty_name')}' shares no words with "
                            f"bank description '{txn.description_normalised}'")

        # 3. Transaction reuse.
        if txn_id:
            if txn_id in seen_txn:
                finding("txn_reuse", "risk",
                        f"transaction {txn_id[:8]}… already matched to {seen_txn[txn_id]}",
                        transaction_id=txn_id)
            else:
                seen_txn[txn_id] = inv_no

    # 4. Possible missed matches (advisory): an unmatched invoice with an obvious,
    #    still-unmatched transaction available.
    used_txn_ids = {r.get("transaction_id") for r in rows}
    for inv_id, inv in inv_map.items():
        if inv_id in matched_ids:
            continue
        cand = _find_missed_txn(inv, txn_map, used_txn_ids, ctx)
        if cand:
            findings.append({
                "match_id": None, "invoice_id": inv_id,
                "invoice_number": inv.invoice_number, "match_status": "unmatched",
                "code": "missed", "severity": "warn",
                "detail": f"invoice {inv.invoice_number} has a candidate transaction "
                          f"with amount within the auto band",
                "transaction_id": cand})

    # Act / log. Only the governed pass (apply=True) writes to the durable trace;
    # the advisory tool path (apply=False) just returns findings to the model, so
    # nothing is double-logged.
    downgraded = 0
    for f in findings:
        if not apply:
            continue
        if f["code"] == "missed":
            mem.persist("verify_finding", f["detail"], f, phase="verify")
            continue
        if (VERIFY_ENABLE_DOWNGRADE and f["severity"] == "risk"
                and f["match_status"] == "auto" and f["match_id"]):
            if _downgrade(db, f):
                downgraded += 1
                mem.persist("match_downgraded",
                            f"Downgraded {f['invoice_number']} to review — {f['detail']}",
                            f, phase="verify")
                continue
        mem.persist("verify_finding", f"{f['invoice_number']}: {f['detail']}", f, phase="verify")

    warnings = sum(1 for f in findings if f["severity"] == "warn" and f["code"] != "missed")
    missed = sum(1 for f in findings if f["code"] == "missed")
    summary = {"checked": len(rows), "downgraded": downgraded,
               "warnings": warnings, "missed": missed}
    if apply:
        mem.persist("verification_complete",
                    f"Verified {len(rows)} match(es): {downgraded} downgraded, "
                    f"{missed} possible missed.", summary, phase="verify")

    return {"findings": findings, **summary}


def _find_missed_txn(inv, txn_map, used_txn_ids, ctx) -> str | None:
    """Return a candidate transaction_id whose converted amount lands in the auto
    band, or None. Deterministic & cheap: uses cached FX only (no network call);
    skips currency pairs we can't price without one."""
    inv_ccy = inv.invoice_currency.upper()
    for txn_id, txn in txn_map.items():
        if txn_id in used_txn_ids:
            continue
        txn_ccy = txn.currency_code.upper()
        if inv_ccy == txn_ccy:
            rate = 1.0
        else:
            cached = (ctx.get("rates") or {}).get((inv_ccy, txn_ccy, str(inv.invoice_date)))
            if not cached:
                continue
            rate = cached[1]
        converted = inv.invoice_amount * rate
        if not converted:
            continue
        txn_amount = txn.credit_amount or 0.0
        variance_pct = (txn_amount - converted) / converted * 100
        if -gate.AUTO_MAX_NEG_VARIANCE <= variance_pct <= gate.AUTO_MAX_POS_VARIANCE:
            return txn_id
    return None


def _downgrade(db, f: dict) -> bool:
    """Flip a still-auto match to pending_review (+ invoice to partial). Idempotent:
    the status guard means a second pass is a no-op. Returns True if it acted."""
    try:
        res = (db.table("reconciliation_match")
                 .update({"match_status": "pending_review"})
                 .eq("match_id", f["match_id"]).eq("match_status", "auto")
                 .execute())
        if not res.data:
            return False   # already downgraded by an earlier pass
        if f.get("invoice_id"):
            db.table("invoice").update({"status": "partial"}) \
              .eq("invoice_id", f["invoice_id"]).execute()
        return True
    except Exception as exc:
        logger.warning("verifier downgrade failed for match %s: %s", f.get("match_id"), exc)
        return False
