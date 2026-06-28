"""
agent/anomaly.py
================
Phase B.3 — the anomaly / fraud-signal detector. Where the gate governs a single
proposal and the verifier re-checks the run's matches, this layer looks at the
financial picture for fraud/risk patterns no per-match rule can see:

  - duplicate_invoice    — the same bill issued twice (double-billing),
  - beneficiary_mismatch — a payment proof names a different paying party than the
                           invoice's counterparty (impersonation / BEC),
  - bank_detail_change   — a counterparty's banking identity differs from the
                           account it used on a previous proof,
  - amount_outlier       — an invoice amount far outside that counterparty's norm.

Deterministic and self-fetching (it does not depend on the run's `ctx` being
populated). On the automatic post-loop pass (`apply=True`) a HIGH-severity fraud
signal that implicates a match this run auto-committed gets escalated to
`pending_review` (reusing the verifier's governed downgrade). On the tool path
(`apply=False`) it only reports.

Findings are persisted as `anomaly_detected` events: they render as warnings in the
dashboard ActivityDrawer (levelFor maps "anomaly" → warning) and feed the dashboard
Anomalies panel.
"""
import logging
import os
import statistics
from collections import defaultdict
from datetime import date

from agent import verifier

logger = logging.getLogger(__name__)

ANOMALY_DUP_DAYS            = int(os.getenv("ANOMALY_DUP_DAYS", "30"))
ANOMALY_OUTLIER_MIN_HISTORY = int(os.getenv("ANOMALY_OUTLIER_MIN_HISTORY", "4"))
ANOMALY_OUTLIER_IQR_K       = float(os.getenv("ANOMALY_OUTLIER_IQR_K", "1.5"))
ANOMALY_ENABLE_ESCALATE     = os.getenv("ANOMALY_ENABLE_ESCALATE", "true").lower() == "true"

SEV_HIGH = "high"
SEV_MEDIUM = "medium"


def _parse_date(v):
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


def scan_anomalies(db, job_id, sme_id, ctx, mem, *, apply: bool) -> dict:
    """Run the four deterministic checks, persist findings, and (when apply=True)
    escalate high-severity fraud signals on this run's auto-commits. Defensive —
    the runner also wraps this, but a single failing check must not sink the rest."""
    invoices = _fetch_invoices(db, sme_id)
    proofs = _fetch_proofs(db, sme_id)
    history = _counterparty_history(db, sme_id)
    job_auto = _job_auto_matches(db, job_id)   # counterparty/invoice -> match_id (auto only)

    findings: list[dict] = []
    for check in (_check_duplicate_invoices, _check_beneficiary_mismatch,
                  _check_bank_detail_change, _check_amount_outlier):
        try:
            findings.extend(check(invoices, proofs, history))
        except Exception as exc:  # one bad check shouldn't kill the scan
            logger.warning("anomaly check %s failed: %s", check.__name__, exc)

    # Only the governed pass (apply=True) escalates and writes to the durable
    # trace; the advisory tool path (apply=False) just returns findings so nothing
    # is double-logged.
    escalated = 0
    for f in findings:
        if not apply:
            continue
        if (ANOMALY_ENABLE_ESCALATE and f["severity"] == SEV_HIGH
                and f.get("invoice_id") and f["invoice_id"] in job_auto):
            match_id = job_auto[f["invoice_id"]]
            if verifier._downgrade(db, {"match_id": match_id, "invoice_id": f["invoice_id"]}):
                f["action"] = "escalated"
                escalated += 1
        mem.persist("anomaly_detected", f["detail"], f, phase="verify")

    high = sum(1 for f in findings if f["severity"] == SEV_HIGH)
    summary = {"flagged": len(findings), "high": high, "escalated": escalated}
    if apply:
        mem.persist("anomaly_scan_done",
                    f"Anomaly scan: {len(findings)} signal(s), {high} high-severity, "
                    f"{escalated} escalated to review.", summary, phase="verify")
    return {"findings": findings, **summary}


# ── data fetch (self-contained) ───────────────────────────────────
def _fetch_invoices(db, sme_id) -> list[dict]:
    return (db.table("invoice")
              .select("invoice_id, invoice_number, counterparty_name, "
                      "invoice_currency, invoice_amount, invoice_date")
              .eq("sme_id", sme_id).execute().data) or []


def _fetch_proofs(db, sme_id) -> list[dict]:
    # Direct query: _fetch_proofs in orchestrator omits invoice_id + uploaded_at,
    # both of which we need here.
    return (db.table("payment_proof")
              .select("proof_id, invoice_id, parsed_data, parsed_amount, "
                      "parsed_currency, uploaded_at")
              .eq("sme_id", sme_id).eq("parse_status", "completed")
              .order("uploaded_at", desc=False).execute().data) or []


def _counterparty_history(db, sme_id) -> dict[str, list[float]]:
    """Map counterparty_name -> list of past matched converted amounts, for outlier
    baselines. Scoped to the SME via its jobs (reconciliation_match has no sme_id)."""
    jobs = (db.table("reconciliation_job").select("job_id")
              .eq("sme_id", sme_id).execute().data) or []
    job_ids = [j["job_id"] for j in jobs]
    if not job_ids:
        return {}
    rows = (db.table("reconciliation_match")
              .select("converted_amount, invoice(counterparty_name)")
              .in_("job_id", job_ids).execute().data) or []
    hist: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        name = ((r.get("invoice") or {}).get("counterparty_name") or "").strip()
        amt = r.get("converted_amount")
        if name and amt is not None:
            hist[name].append(float(amt))
    return hist


def _job_auto_matches(db, job_id) -> dict[str, str]:
    """invoice_id -> match_id for matches THIS job auto-committed (escalation targets)."""
    rows = (db.table("reconciliation_match")
              .select("match_id, invoice_id, match_status")
              .eq("job_id", job_id).eq("match_status", "auto").execute().data) or []
    return {r["invoice_id"]: r["match_id"] for r in rows if r.get("invoice_id")}


# ── checks ─────────────────────────────────────────────────────────
def _check_duplicate_invoices(invoices, proofs, history) -> list[dict]:
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for inv in invoices:
        key = ((inv.get("counterparty_name") or "").strip().lower(),
               (inv.get("invoice_currency") or "").upper(),
               round(float(inv.get("invoice_amount") or 0), 2))
        buckets[key].append(inv)

    out: list[dict] = []
    for (name, _ccy, amount), group in buckets.items():
        if len(group) < 2 or amount <= 0:
            continue
        # Cluster same-amount invoices that fall within DUP_DAYS of each other, so a
        # far-apart third invoice doesn't mask a genuine close pair.
        dated = sorted(((d, g) for g in group if (d := _parse_date(g.get("invoice_date")))),
                       key=lambda x: x[0])
        cluster: list[dict] = []
        prev_date = None
        for d, g in dated:
            if prev_date is not None and (d - prev_date).days > ANOMALY_DUP_DAYS:
                _emit_dup(out, cluster, amount)
                cluster = []
            cluster.append(g)
            prev_date = d
        _emit_dup(out, cluster, amount)
    return out


def _emit_dup(out: list[dict], cluster: list[dict], amount: float) -> None:
    if len(cluster) < 2:
        return
    numbers = ", ".join(g.get("invoice_number") or "?" for g in cluster)
    out.append({
        "code": "duplicate_invoice", "severity": SEV_MEDIUM,
        "entity": cluster[0].get("counterparty_name"),
        "invoice_id": cluster[0].get("invoice_id"),
        "detail": f"Possible double-billing: {len(cluster)} invoices from "
                  f"'{cluster[0].get('counterparty_name')}' for the same amount "
                  f"({amount:.2f}) within {ANOMALY_DUP_DAYS} days ({numbers})."})


def _check_beneficiary_mismatch(invoices, proofs, history) -> list[dict]:
    inv_by_id = {i["invoice_id"]: i for i in invoices}
    out: list[dict] = []
    for p in proofs:
        inv = inv_by_id.get(p.get("invoice_id"))
        if not inv:
            continue
        pdata = p.get("parsed_data") or {}
        payer = (pdata.get("sender_name") or pdata.get("receiver_name") or "").strip()
        counterparty = (inv.get("counterparty_name") or "").strip()
        if not payer or not counterparty:
            continue
        if not (verifier._tokens(payer) & verifier._tokens(counterparty)):
            out.append({
                "code": "beneficiary_mismatch", "severity": SEV_HIGH,
                "entity": counterparty, "invoice_id": inv["invoice_id"],
                "detail": f"Payment proof for {inv.get('invoice_number')} "
                          f"({counterparty}) names a different paying party: "
                          f"'{payer}'."})
    return out


def _check_bank_detail_change(invoices, proofs, history) -> list[dict]:
    inv_by_id = {i["invoice_id"]: i for i in invoices}

    def identity(pdata: dict) -> str | None:
        for k in ("account_number", "iban", "swift_code"):
            v = (pdata.get(k) or "").strip()
            if v:
                return f"{k}:{v}"
        return None

    # proofs already ordered by uploaded_at ascending
    by_cp: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for p in proofs:
        inv = inv_by_id.get(p.get("invoice_id"))
        if not inv:
            continue
        ident = identity(p.get("parsed_data") or {})
        if ident:
            by_cp[(inv.get("counterparty_name") or "").strip()].append((ident, inv))

    out: list[dict] = []
    for cp, seq in by_cp.items():
        if not cp or len(seq) < 2:
            continue
        prior = {seq[0][0]}
        for ident, inv in seq[1:]:
            if ident not in prior:
                was = ", ".join(sorted(prior))
                out.append({
                    "code": "bank_detail_change", "severity": SEV_HIGH,
                    "entity": cp, "invoice_id": inv.get("invoice_id"),
                    "detail": f"'{cp}' paid from new banking details ({ident}) on "
                              f"{inv.get('invoice_number')} — previously used {was}."})
            prior.add(ident)
    return out


def _check_amount_outlier(invoices, proofs, history) -> list[dict]:
    out: list[dict] = []
    for inv in invoices:
        cp = (inv.get("counterparty_name") or "").strip()
        amounts = history.get(cp)
        if not amounts or len(amounts) < ANOMALY_OUTLIER_MIN_HISTORY:
            continue
        qs = statistics.quantiles(amounts, n=4)  # [Q1, Q2, Q3]
        q1, q3 = qs[0], qs[2]
        iqr = q3 - q1
        lo, hi = q1 - ANOMALY_OUTLIER_IQR_K * iqr, q3 + ANOMALY_OUTLIER_IQR_K * iqr
        amt = float(inv.get("invoice_amount") or 0)
        if iqr > 0 and (amt < lo or amt > hi):
            out.append({
                "code": "amount_outlier", "severity": SEV_MEDIUM,
                "entity": cp, "invoice_id": inv.get("invoice_id"),
                "detail": f"{inv.get('invoice_number')} amount {amt:.0f} is outside "
                          f"'{cp}'s usual range (~{q1:.0f}–{q3:.0f})."})
    return out
