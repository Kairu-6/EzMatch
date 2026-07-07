"""
agent/tools.py
==============
The agent's action surface. Each tool wraps an existing, tested backend helper
so the agent reuses the same data access and the same committer the legacy
pipeline uses — nothing new touches the database directly.

Design rules that make this safe for finance:
  - The model passes only IDs + a confidence + a rationale. All money/currency is
    looked up server-side from authoritative objects (no hallucinated amounts).
  - The model's ONLY write tool is `propose_match`; proposing is not committing.
    Every proposal is judged by the deterministic `gate`, which sets match_status.
  - Tool returns are compact (ids + verdicts) to keep working memory small.

Every tool has signature: fn(db, job_id, sme_id, ctx, mem, mode, **args) -> dict
"""
from datetime import date

import orchestrator
from forex_api import get_rate
from data_contracts import MorpheusMatchProposal, MatchStatus
from agent import gate, verifier, anomaly


# ── observe (read-only) ───────────────────────────────────────────
def list_invoices(db, job_id, sme_id, ctx, mem, mode, status_filter=None, **_):
    invoices = orchestrator._fetch_invoices(db, sme_id)
    ctx["inv_map"] = {inv.invoice_id: inv for inv in invoices}
    mem.persist("tool_result", f"Listed {len(invoices)} pending invoice(s).", phase="plan")
    return {"count": len(invoices), "invoices": [
        {"invoice_id": i.invoice_id, "invoice_number": i.invoice_number,
         "counterparty": i.counterparty_name, "amount": i.invoice_amount,
         "currency": i.invoice_currency, "date": str(i.invoice_date),
         "due_date": str(i.due_date) if i.due_date else None}
        for i in invoices]}


def list_transactions(db, job_id, sme_id, ctx, mem, mode, lookback_days=None, **_):
    txns = (orchestrator._fetch_transactions(db, sme_id, int(lookback_days))
            if lookback_days is not None
            else orchestrator._fetch_transactions(db, sme_id))
    ctx["txn_map"] = {t.transaction_id: t for t in txns}
    mem.persist("tool_result", f"Listed {len(txns)} unmatched transaction(s).", phase="plan")
    return {"count": len(txns), "transactions": [
        {"transaction_id": t.transaction_id, "date": str(t.transaction_date),
         "description": t.description_normalised, "reference": t.reference_number,
         "credit": t.credit_amount, "debit": t.debit_amount,
         "currency": t.currency_code} for t in txns]}


def list_proofs(db, job_id, sme_id, ctx, mem, mode, **_):
    proofs = orchestrator._fetch_proofs(db, sme_id)
    ctx["proof_map"] = {p.proof_id: p for p in proofs}
    mem.persist("tool_result", f"Listed {len(proofs)} payment proof(s).", phase="plan")
    return {"count": len(proofs), "proofs": [
        {"proof_id": p.proof_id, "amount": p.parsed_amount, "currency": p.parsed_currency,
         "date": p.parsed_date, "reference": p.parsed_reference} for p in proofs]}


def get_fx_rate(db, job_id, sme_id, ctx, mem, mode,
                from_currency=None, to_currency=None, on_date=None, **_):
    if not (from_currency and to_currency and on_date):
        return {"error": "from_currency, to_currency and on_date are required"}
    fc, tc = from_currency.upper(), to_currency.upper()
    if fc == tc:
        return {"from": fc, "to": tc, "date": on_date, "rate": 1.0, "rate_id": None}
    try:
        d = date.fromisoformat(on_date)
    except ValueError:
        return {"error": f"on_date '{on_date}' must be ISO YYYY-MM-DD"}
    rate_id, rate = get_rate(db, fc, tc, d, job_id)
    ctx.setdefault("rates", {})[(fc, tc, on_date)] = (rate_id, rate)
    return {"from": fc, "to": tc, "date": on_date, "rate": rate, "rate_id": rate_id}


# ── verify (read-only self-critique) ──────────────────────────────
def verify_matches(db, job_id, sme_id, ctx, mem, mode, **_):
    """Re-examine this run's matches without mutating anything. Surfaces risky
    auto-commits and possible missed matches so the agent can self-critique."""
    result = verifier.run_verification(db, job_id, sme_id, ctx, mem, apply=False)
    findings = [
        {"invoice_number": f["invoice_number"], "code": f["code"],
         "severity": f["severity"], "detail": f["detail"],
         **({"transaction_id": f["transaction_id"]} if f.get("transaction_id") else {})}
        for f in result["findings"]]
    risks = sum(1 for f in result["findings"] if f["severity"] == "risk")
    return {"checked": result["checked"], "risks": risks,
            "warnings": result["warnings"], "missed": result["missed"],
            "findings": findings}


def scan_anomalies(db, job_id, sme_id, ctx, mem, mode, **_):
    """Scan the workspace for fraud/anomaly signals (duplicate billing, payments
    from the wrong party, changed bank details, amount outliers) without mutating
    anything. Surfaces signals so the agent can flag them in its wrap-up."""
    result = anomaly.scan_anomalies(db, job_id, sme_id, ctx, mem, apply=False)
    return {"flagged": result["flagged"], "high": result["high"],
            "findings": [{"code": f["code"], "severity": f["severity"],
                          "detail": f["detail"]} for f in result["findings"]]}


# ── act (gated + logged) ──────────────────────────────────────────
def propose_match(db, job_id, sme_id, ctx, mem, mode,
                  invoice_id=None, transaction_id=None, confidence=None,
                  rationale=None, proof_id=None, **_):
    inv = (ctx.get("inv_map") or {}).get(invoice_id)
    if inv is None:
        return {"error": "unknown_invoice_id",
                "hint": "call list_invoices and use an exact invoice_id from it"}
    txn = (ctx.get("txn_map") or {}).get(transaction_id)
    if txn is None:
        return {"error": "unknown_transaction_id",
                "hint": "call list_transactions and use an exact transaction_id from it"}

    matched_ids = ctx.setdefault("matched_ids", set())
    if invoice_id in matched_ids:
        return {"error": "already_matched", "invoice_id": invoice_id}

    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        return {"error": "confidence must be a number between 0 and 1"}

    # Ignore a proof_id the agent invented; keep it only if it's real.
    if proof_id and proof_id not in (ctx.get("proof_map") or {}):
        proof_id = None

    # Resolve FX server-side (self-healing if the agent skipped get_fx_rate).
    fc, tc = inv.invoice_currency.upper(), txn.currency_code.upper()
    if fc == tc:
        rate_id, rate = None, 1.0
    else:
        key = (fc, tc, str(inv.invoice_date))
        cached = ctx.get("rates", {}).get(key)
        if cached:
            rate_id, rate = cached
        else:
            rate_id, rate = get_rate(db, fc, tc, inv.invoice_date, job_id)
            ctx.setdefault("rates", {})[key] = (rate_id, rate)

    converted    = round(inv.invoice_amount * rate, 4)
    txn_amount   = txn.credit_amount or 0.0
    variance     = round(txn_amount - converted, 4)
    variance_pct = round((variance / converted) * 100, 4) if converted else 0.0

    verdict, reasons = gate.decide(confidence, variance_pct, converted,
                                   ctx.get("auto_count", 0))
    meta = {"invoice_id": invoice_id, "transaction_id": transaction_id,
            "invoice_number": inv.invoice_number, "confidence": confidence,
            "variance_pct": variance_pct, "verdict": verdict.value,
            "gate_reasons": reasons, "rationale": rationale}

    if verdict == gate.Verdict.REJECT:
        mem.persist("match_rejected",
                    f"Rejected {inv.invoice_number} → {transaction_id[:8]}: "
                    f"{'; '.join(reasons)}", meta, phase="act")
        return {"gate": verdict.value, "gate_reasons": reasons,
                "variance_pct": variance_pct, "written": False}

    if mode == "dry_run":
        mem.persist("match_proposed",
                    f"[dry-run] would {verdict.value} {inv.invoice_number} "
                    f"→ {transaction_id[:8]}", meta, phase="act")
        return {"gate": verdict.value, "gate_reasons": reasons,
                "variance_pct": variance_pct, "written": False, "dry_run": True}

    force_status = (MatchStatus.AUTO if verdict == gate.Verdict.AUTO_COMMIT
                    else MatchStatus.PENDING_REVIEW)
    proposal = MorpheusMatchProposal(invoice_id=invoice_id, transaction_id=transaction_id,
                                     proof_id=proof_id, confidence=confidence)
    orchestrator._write_match(db, job_id, proposal, inv, txn, rate_id, rate,
                              force_status=force_status)
    matched_ids.add(invoice_id)

    if verdict == gate.Verdict.AUTO_COMMIT:
        ctx["auto_count"] = ctx.get("auto_count", 0) + 1
        event, verb = "match_committed", "Committed"
    else:
        event, verb = "match_escalated", "Escalated to review"
    mem.persist(event,
                f"{verb}: {inv.invoice_number} → txn {transaction_id[:8]} "
                f"(conf {confidence:.2f}, var {variance_pct:+.1f}%)", meta, phase="act")

    return {"gate": verdict.value, "gate_reasons": reasons,
            "match_status": force_status.value, "variance_pct": variance_pct,
            "converted_amount": converted, "written": True}


def _finish_placeholder(*_args, **_kwargs):
    # Never executed — the runner intercepts "finish" before dispatch.
    return {"finished": True}


# ── catalog ───────────────────────────────────────────────────────
TOOLS = [
    {"name": "list_invoices", "fn": list_invoices,
     "description": "List this workspace's unmatched/pending invoices (id, counterparty, amount, currency, date).",
     "parameters": {"type": "object",
                    "properties": {"status_filter": {"type": "string",
                                   "description": "optional; ignored for now (always pending+unmatched)"}},
                    "required": []}},
    {"name": "list_transactions", "fn": list_transactions,
     "description": "List unmatched bank transactions (id, date, normalised description, credit/debit, currency).",
     "parameters": {"type": "object",
                    "properties": {"lookback_days": {"type": "integer",
                                   "description": "optional window in days; defaults to the configured lookback"}},
                    "required": []}},
    {"name": "list_proofs", "fn": list_proofs,
     "description": "List parsed payment proofs (id, amount, currency, date, reference) that corroborate matches.",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_fx_rate", "fn": get_fx_rate,
     "description": "Get the historical FX rate for a currency pair on a date (cache-first). Use the INVOICE date.",
     "parameters": {"type": "object",
                    "properties": {"from_currency": {"type": "string", "description": "ISO code, e.g. USD"},
                                   "to_currency": {"type": "string", "description": "ISO code, e.g. MYR"},
                                   "on_date": {"type": "string", "description": "ISO date YYYY-MM-DD (the invoice date)"}},
                    "required": ["from_currency", "to_currency", "on_date"]}},
    {"name": "propose_match", "fn": propose_match,
     "description": ("Propose that an invoice was paid by a bank transaction. A deterministic gate "
                     "(not you) decides whether it auto-commits, routes to a human, or is rejected. "
                     "Give a calibrated confidence 0-1 and a one-line rationale."),
     "parameters": {"type": "object",
                    "properties": {"invoice_id": {"type": "string"},
                                   "transaction_id": {"type": "string"},
                                   "confidence": {"type": "number", "description": "0.0–1.0"},
                                   "rationale": {"type": "string", "description": "why these two match"},
                                   "proof_id": {"type": "string", "description": "optional corroborating proof id"}},
                    "required": ["invoice_id", "transaction_id", "confidence", "rationale"]}},
    {"name": "verify_matches", "fn": verify_matches,
     "description": ("Re-check the matches you've made so far this run. Returns risky "
                     "auto-commits (no proof / weak counterparty link / reused transaction) "
                     "and possible missed matches (an unmatched invoice with a candidate "
                     "transaction). Call this in your VERIFY phase before finishing; re-propose "
                     "a 'missed' candidate if it truly matches. A deterministic verifier will "
                     "independently downgrade unsupported auto-commits regardless."),
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "scan_anomalies", "fn": scan_anomalies,
     "description": ("Scan the workspace for fraud/anomaly signals: duplicate (double-billed) "
                     "invoices, payment proofs naming a different paying party than the invoice "
                     "counterparty, counterparties whose bank details changed, and invoice amounts "
                     "far outside a counterparty's norm. Call this in your ADVISE phase and mention "
                     "anything it returns. A deterministic detector escalates high-severity signals "
                     "to human review regardless."),
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "finish", "fn": _finish_placeholder,
     "description": "Call when every invoice has been matched or deemed unmatchable. Ends the run.",
     "parameters": {"type": "object",
                    "properties": {"summary": {"type": "string"},
                                   "matched_count": {"type": "integer"},
                                   "unmatched_count": {"type": "integer"}},
                    "required": ["summary"]}},
]

REGISTRY = {t["name"]: t["fn"] for t in TOOLS}


def openai_tools_param() -> list[dict]:
    return [{"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": t["parameters"]}} for t in TOOLS]


def react_tool_descriptions() -> str:
    lines = []
    for t in TOOLS:
        props = t["parameters"].get("properties", {})
        req = set(t["parameters"].get("required", []))
        sig = ", ".join((f"{k}*" if k in req else k) for k in props) or "—"
        lines.append(f"- {t['name']}({sig}): {t['description']}")
    return "\n".join(lines)
