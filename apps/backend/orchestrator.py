import os
import re
import uuid
import logging
import httpx
import json
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client

from data_contracts import (
    InvoiceForMatching,
    TransactionForMatching,
    ProofForMatching,
    OrchestratorJobInput,
    ForexCacheQuery,
    MorpheusMatchProposal,
    ReconciliationMatchInsert,
    LogEntry,
    MatchStatus,
    JobStatus,
)
from forex_api import get_rates_batch, get_rate

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Constants — read from .env, no client created here

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_API_KEY")
MORPHEUS_URL  = os.getenv("MORPHEUS_URL", "https://api.mor.org/api/v1")
MORPHEUS_API_KEY      = os.getenv("MORPHEUS_API_KEY")
# ✅ FIX 1: Set default to the working model from your test script
MORPHEUS_MODEL        = os.getenv("MORPHEUS_MODEL", "qwen3-5-9b")
CONFIDENCE_THRESHOLD  = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))
# How far back to look for unmatched transactions. The old hardcoded 30 days
# silently excluded all data once the demo aged; env-driven, generous default.
LOOKBACK_DAYS         = int(os.getenv("RECON_LOOKBACK_DAYS", "365"))

# Logging helper

def _log(db: Client, job_id: str, event_type: str, message: str, metadata: dict = None):
    try:
        entry = LogEntry(job_id=job_id, event_type=event_type, message=message, metadata=metadata)
        db.table("reconciliation_log").insert(entry.model_dump()).execute()
    except Exception as exc:
        logger.error("Log write failed: %s", exc)
    logger.info("[%s] %s — %s", event_type, job_id, message)

# Step 1: Start job

def _start_job(db: Client, sme_id: str) -> str:
    job_id = str(uuid.uuid4())
    db.table("reconciliation_job").insert({
        "job_id":        job_id,
        "sme_id":        sme_id,
        "status":        JobStatus.PROCESSING,
        "model_version": MORPHEUS_MODEL,
        "started_at":    datetime.utcnow().isoformat(),
    }).execute()
    _log(db, job_id, "job_started", f"Reconciliation job started for SME {sme_id}")
    return job_id

# Step 2: Fetch documents

def _fetch_invoices(db: Client, sme_id: str) -> list[InvoiceForMatching]:
    rows = (
        db.table("invoice")
        .select("invoice_id, invoice_number, counterparty_name, invoice_currency, invoice_amount, invoice_date, due_date")
        .eq("sme_id", sme_id)
        .in_("status", ["pending", "unmatched"])
        .execute()
        .data
    )
    # Skip rows with incomplete data (e.g. a failed/half-parsed upload) so they
    # neither crash schema validation nor reach the matcher as garbage.
    invoices = []
    for r in rows:
        try:
            invoices.append(InvoiceForMatching(**r))
        except Exception:
            logger.warning("Skipping invoice %s — incomplete or failed parse.", r.get("invoice_id"))
    return invoices


def _fetch_transactions(db: Client, sme_id: str, days: int = LOOKBACK_DAYS) -> list[TransactionForMatching]:
    cutoff = (datetime.utcnow().date() - timedelta(days=days)).isoformat()
    rows = (
        db.table("bank_transaction")
        .select(
            "transaction_id, transaction_date, description, description_normalised, "
            "reference_number, debit_amount, credit_amount, currency_code, "
            "bank_statement!inner(account_id, bank_account!inner(sme_id))"
        )
        .eq("bank_statement.bank_account.sme_id", sme_id)
        .eq("is_matched", False)
        .gte("transaction_date", cutoff)
        .execute()
        .data
    )
    return [
        TransactionForMatching(
            transaction_id=r["transaction_id"],
            transaction_date=r["transaction_date"],
            description=r["description"],
            description_normalised=r["description_normalised"],
            reference_number=r.get("reference_number"),
            debit_amount=r["debit_amount"],
            credit_amount=r["credit_amount"],
            currency_code=r["currency_code"],
        )
        for r in rows
    ]


def _fetch_proofs(db: Client, sme_id: str) -> list[ProofForMatching]:
    rows = (
        db.table("payment_proof")
        .select("proof_id, parsed_amount, parsed_currency, parsed_date, parsed_reference, parsed_data")
        .eq("sme_id", sme_id)
        .eq("parse_status", "completed")
        .execute()
        .data
    )
    return [ProofForMatching(**r) for r in rows]

# Step 3.5: Deterministic reference pre-match (DuitNow/FPX recon key)

def _norm_ref(s: str | None) -> str | None:
    """Normalise a reference for exact comparison: drop spaces/dashes, uppercase."""
    if not s:
        return None
    cleaned = re.sub(r"[\s\-]", "", str(s)).upper()
    return cleaned or None


def _reference_pairs(
    invoices: list[InvoiceForMatching],
    transactions: list[TransactionForMatching],
    proofs: list[ProofForMatching],
) -> list[tuple[InvoiceForMatching, TransactionForMatching, ProofForMatching | None]]:
    """Pure: find (invoice, transaction, proof?) triples that share an exact
    DuitNow/FPX reference. A transaction matches an invoice when its
    reference_number equals the invoice number OR an amount-corroborating proof's
    reference. One transaction → one invoice. No DB, no side effects."""
    txn_by_ref: dict[str, TransactionForMatching] = {}
    for t in transactions:
        r = _norm_ref(t.reference_number)
        if r and r not in txn_by_ref:  # first wins; ref should be unique per txn
            txn_by_ref[r] = t

    pairs = []
    claimed_txn: set[str] = set()
    for inv in invoices:
        proof = next(
            (p for p in proofs if p.parsed_amount is not None
             and abs(p.parsed_amount - inv.invoice_amount) < 0.01),
            None,
        )
        candidates = {_norm_ref(inv.invoice_number)}
        if proof:
            candidates.add(_norm_ref(proof.parsed_reference))
        candidates.discard(None)

        for ref in candidates:
            txn = txn_by_ref.get(ref)
            if txn and txn.transaction_id not in claimed_txn:
                pairs.append((inv, txn, proof))
                claimed_txn.add(txn.transaction_id)
                break
    return pairs


def _reference_prematch(db: Client, job_id: str, sme_id: str) -> tuple[int, set[str]]:
    """Commit exact-reference matches through the same gate + writer the LLM path
    uses, BEFORE any model runs. Returns (matches_written, matched_invoice_ids).
    Because _write_match flips invoice/transaction state, matched rows drop out of
    every later _fetch_*, so the LLM only works the unreferenced remainder."""
    from agent.gate import decide, Verdict

    invoices     = _fetch_invoices(db, sme_id)
    transactions = _fetch_transactions(db, sme_id)
    proofs       = _fetch_proofs(db, sme_id)
    pairs        = _reference_pairs(invoices, transactions, proofs)

    written, matched_ids, auto_count = 0, set(), 0
    for inv, txn, proof in pairs:
        fc, tc = inv.invoice_currency.upper(), txn.currency_code.upper()
        if fc == tc:
            rate_id, rate = None, 1.0
        else:
            try:
                rate_id, rate = get_rate(db, fc, tc, inv.invoice_date, job_id)
            except Exception as exc:
                logger.warning("Reference pre-match: rate lookup %s->%s failed for "
                               "invoice %s — %s", fc, tc, inv.invoice_id, exc)
                continue

        converted    = round(inv.invoice_amount * rate, 4)
        txn_amount   = txn.credit_amount or 0.0
        variance_pct = round(((txn_amount - converted) / converted) * 100, 4) if converted else 0.0

        verdict, reasons = decide(0.99, variance_pct, converted, auto_count)
        if verdict == Verdict.REJECT:
            _log(db, job_id, "reference_match_rejected",
                 f"Exact reference match {inv.invoice_number} → txn {txn.transaction_id[:8]} "
                 f"rejected: {'; '.join(reasons)}",
                 metadata={"invoice_id": inv.invoice_id, "variance_pct": variance_pct})
            continue

        force_status = (MatchStatus.AUTO if verdict == Verdict.AUTO_COMMIT
                        else MatchStatus.PENDING_REVIEW)
        proposal = MorpheusMatchProposal(
            invoice_id=inv.invoice_id, transaction_id=txn.transaction_id,
            proof_id=proof.proof_id if proof else None, confidence=0.99,
        )
        _write_match(db, job_id, proposal, inv, txn, rate_id, rate, force_status=force_status)
        matched_ids.add(inv.invoice_id)
        written += 1
        if verdict == Verdict.AUTO_COMMIT:
            auto_count += 1
        _log(db, job_id, "reference_matched",
             f"Exact FPX/DuitNow reference match: {inv.invoice_number} → txn "
             f"{txn.transaction_id[:8]} (ref {txn.reference_number}, {force_status})",
             metadata={"invoice_id": inv.invoice_id, "transaction_id": txn.transaction_id,
                       "invoice_number": inv.invoice_number, "reference": txn.reference_number,
                       "match_status": force_status.value, "variance_pct": variance_pct})

    if written:
        _log(db, job_id, "reference_prematch_done",
             f"Reference pre-pass matched {written} invoice(s) on exact DuitNow/FPX key.")
    return written, matched_ids

# Step 4: Build Morpheus prompt

def _build_morpheus_prompt(job_input: OrchestratorJobInput, rates: dict) -> str:
    invoice_blocks = []
    for inv in job_input.invoices:
        rate_info = rates.get(inv.invoice_id, {})
        rate      = rate_info.get("rate", 0)
        converted = round(inv.invoice_amount * rate, 2) if rate else None

        proof = next(
            (p for p in job_input.proofs if p.parsed_amount and
             abs((p.parsed_amount or 0) - inv.invoice_amount) < 0.01),
            None
        )

        block = (
            f"INVOICE {inv.invoice_id}:\n"
            f"  number:        {inv.invoice_number}\n"
            f"  counterparty:  {inv.counterparty_name}\n"
            f"  amount:        {inv.invoice_amount} {inv.invoice_currency}\n"
            f"  date:          {inv.invoice_date}\n"
            f"  fx_rate:       1 {inv.invoice_currency} = {rate} MYR (on {inv.invoice_date})\n"
            f"  converted:     {converted} MYR\n"
        )
        if proof:
            block += (
                f"  proof_id:      {proof.proof_id}\n"
                f"  proof_amount:  {proof.parsed_amount} {proof.parsed_currency}\n"
                f"  proof_ref:     {proof.parsed_reference}\n"
            )
        invoice_blocks.append(block)

    txn_blocks = []
    for txn in job_input.transactions:
        amount_display = (
            f"+{txn.credit_amount} {txn.currency_code} (credit)"
            if txn.credit_amount
            else f"-{txn.debit_amount} {txn.currency_code} (debit)"
        )
        ref_line = f"  reference:     {txn.reference_number}\n" if txn.reference_number else ""
        txn_blocks.append(
            f"TRANSACTION {txn.transaction_id}:\n"
            f"  date:           {txn.transaction_date}\n"
            f"  description:    {txn.description_normalised}\n"
            f"{ref_line}"
            f"  amount:         {amount_display}\n"
        )

    return f"""You are a financial reconciliation engine for a cross-border payment system.

Your task: match each INVOICE to the BANK TRANSACTION that most likely represents its payment.

Rules:
- If a transaction's reference exactly matches an invoice number (or its proof reference), that is a decisive DuitNow/FPX reference match — prefer it over name/amount similarity and assign high confidence.
- Base your matching on semantic similarity of counterparty names and descriptions.
- Use the pre-calculated converted amounts (in MYR) to verify the amounts align within a reasonable tolerance.
- A negative variance (transaction < converted) is normal — it means bank fees were deducted.
- Assign a confidence score between 0.0 and 1.0.
- One invoice maps to at most one transaction. One transaction maps to at most one invoice.
- If no transaction is a plausible match for an invoice, do not force a match.
- Include proof_id in your proposal if a payment proof was provided for that invoice.

INVOICES TO MATCH:
{''.join(invoice_blocks)}

BANK TRANSACTIONS (last {LOOKBACK_DAYS} days, unmatched only):
{''.join(txn_blocks)}

Respond with ONLY a valid JSON array. No explanation, no markdown, no preamble.
Each element must have exactly these keys:
  invoice_id     — full UUID of the matched invoice
  transaction_id — full SHA-256 of the matched transaction
  proof_id       — full UUID if a proof exists, otherwise null
  confidence     — float between 0.0 and 1.0

Example:
[
  {{"invoice_id": "...", "transaction_id": "...", "proof_id": null, "confidence": 0.91}}
]
"""

def _call_morpheus(prompt: str) -> list[MorpheusMatchProposal]:
    logger.debug("Morpheus prompt:\n%s", prompt)

    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {MORPHEUS_API_KEY}",
    }
    payload = {
        "model":    MORPHEUS_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream":   False,
    }

    target_url = MORPHEUS_URL
    if not target_url.endswith("/chat/completions"):
        target_url = f"{target_url.rstrip('/')}/chat/completions"

    response = httpx.post(target_url, json=payload, headers=headers, timeout=180.0)
    response.raise_for_status()

    raw_text = response.json()["choices"][0]["message"]["content"].strip()
    logger.debug("Morpheus raw response:\n%s", raw_text)

    # Strip markdown code fences if present.
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()
        if raw_text.lower().startswith("json"):
            raw_text = raw_text[4:].strip()

    try:
        parsed_json = json.loads(raw_text)
        return [MorpheusMatchProposal(**p) for p in parsed_json]
    except json.JSONDecodeError as e:
        logger.error("Morpheus did not return valid JSON: %s", e)
        raise

# Step 5: Write matches

def _write_match(
    db: Client,
    job_id: str,
    proposal: MorpheusMatchProposal,
    invoice: InvoiceForMatching,
    transaction: TransactionForMatching,
    rate_id: str,
    rate: float,
    force_status: MatchStatus = None,
) -> ReconciliationMatchInsert:
    match = ReconciliationMatchInsert.build(
        job_id=job_id,
        proposal=proposal,
        invoice=invoice,
        transaction=transaction,
        rate_id=rate_id,
        rate=rate,
        threshold=CONFIDENCE_THRESHOLD,
        force_status=force_status,
    )
    db.table("reconciliation_match").insert(match.model_dump()).execute()
    db.table("bank_transaction").update({"is_matched": True}).eq("transaction_id", transaction.transaction_id).execute()

    new_status = "matched" if match.match_status == MatchStatus.AUTO else "partial"
    db.table("invoice").update({"status": new_status}).eq("invoice_id", invoice.invoice_id).execute()

    _log(db, job_id, "match_written",
         f"Invoice {invoice.invoice_number} → txn {transaction.transaction_id[:8]} "
         f"(confidence: {proposal.confidence}, status: {match.match_status})",
         metadata={
             "invoice_id":     invoice.invoice_id,
             "transaction_id": transaction.transaction_id,
             "variance_pct":   match.variance_pct,
             "match_status":   match.match_status,
         })
    return match

# Step 6 & 7: Complete job + Predictor

def _complete_job(db: Client, job_id: str, matched: int, unmatched: int):
    db.table("reconciliation_job").update({
        "status":          JobStatus.COMPLETED,
        "completed_at":    datetime.utcnow().isoformat(),
        "matched_count":   matched,
        "unmatched_count": unmatched,
    }).eq("job_id", job_id).execute()
    _log(db, job_id, "job_completed", f"Job finished — {matched} matched, {unmatched} unmatched.")


def _write_recommendation(db: Client, sme_id: str, job_id: str, unmatched_invoices: list[InvoiceForMatching]):
    if not unmatched_invoices:
        return
    currencies = list({inv.invoice_currency for inv in unmatched_invoices})
    content = (
        f"{len(unmatched_invoices)} invoice(s) could not be matched this run. "
        f"Outstanding currencies: {', '.join(currencies)}. "
        f"Consider checking for pending bank statement uploads or delayed SWIFT transfers."
    )
    db.table("recommendation").insert({
        "recommendation_id": str(uuid.uuid4()),
        "sme_id":            sme_id,
        "job_id":            job_id,
        "rec_type":          "general",
        "content":           content,
        "estimated_saving":  None,
        "is_read":           False,
        "generated_at":      datetime.utcnow().isoformat(),
    }).execute()

# Main entry point

def run_reconciliation(sme_id: str) -> dict:
    # Client created here — after load_dotenv() has already run
    db = create_client(SUPABASE_URL, SUPABASE_KEY)

    job_id = _start_job(db, sme_id)

    try:
        # Deterministic exact-reference matches first — these drop out of the
        # fetches below, so Morpheus only handles the unreferenced remainder.
        prematched, _ = _reference_prematch(db, job_id, sme_id)

        invoices     = _fetch_invoices(db, sme_id)
        transactions = _fetch_transactions(db, sme_id)
        proofs       = _fetch_proofs(db, sme_id)

        _log(db, job_id, "documents_fetched",
             f"Fetched {len(invoices)} invoices, {len(transactions)} transactions, {len(proofs)} proofs.")

        if not invoices:
            reason = "all_matched_by_reference" if prematched else "no_pending_invoices"
            _log(db, job_id, "job_skipped",
                 f"No invoices left for the matcher ({prematched} pre-matched by reference).")
            _complete_job(db, job_id, matched=prematched, unmatched=0)
            return {"status": "completed" if prematched else "skipped",
                    "reason": reason, "matched_count": prematched}

        if not transactions:
            _log(db, job_id, "job_skipped", f"No unmatched transactions in the last {LOOKBACK_DAYS} days.")
            _complete_job(db, job_id, matched=prematched, unmatched=len(invoices))
            return {"status": "skipped", "reason": "no_transactions"}

        # Step 3 — FX rates
        queries      = []
        seen_pairs   = set()
        account_currency = transactions[0].currency_code if transactions else "MYR"

        for inv in invoices:
            if inv.invoice_currency == account_currency:
                continue
            pair = (inv.invoice_currency, account_currency, str(inv.invoice_date))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                queries.append(ForexCacheQuery(
                    from_currency=inv.invoice_currency,
                    to_currency=account_currency,
                    on_date=inv.invoice_date,
                ))

        batch_results = get_rates_batch(db, queries, job_id) if queries else {}

        rates: dict[str, dict] = {}
        for inv in invoices:
            if inv.invoice_currency == account_currency:
                rates[inv.invoice_id] = {"rate_id": None, "rate": 1.0}
            else:
                key = (inv.invoice_currency.upper(), account_currency.upper(), str(inv.invoice_date))
                if key in batch_results:
                    rate_id, rate = batch_results[key]
                    rates[inv.invoice_id] = {"rate_id": rate_id, "rate": rate}
                else:
                    logger.warning("Rate missing for invoice %s — skipping.", inv.invoice_id)

        _log(db, job_id, "rates_fetched", f"FX rates resolved for {len(rates)} invoice(s).")

        # Step 4 — Morpheus
        job_input = OrchestratorJobInput(
            job_id=job_id, sme_id=sme_id,
            invoices=invoices, transactions=transactions, proofs=proofs,
        )
        prompt    = _build_morpheus_prompt(job_input, rates)
        _log(db, job_id, "morpheus_called", "Sending prompt to Morpheus DeAI node.")

        proposals = _call_morpheus(prompt)
        _log(db, job_id, "morpheus_responded",
             f"Morpheus returned {len(proposals)} proposal(s).",
             metadata={"proposals": [p.model_dump() for p in proposals]})

        # Step 5 — Write matches
        inv_map             = {inv.invoice_id:     inv for inv in invoices}
        txn_map             = {txn.transaction_id: txn for txn in transactions}
        matched_invoice_ids = set()
        matched_count       = 0

        for proposal in proposals:
            inv = inv_map.get(proposal.invoice_id)
            txn = txn_map.get(proposal.transaction_id)

            if not inv or not txn:
                _log(db, job_id, "proposal_skipped",
                     "Proposal references unknown invoice or transaction.",
                     metadata=proposal.model_dump())
                continue

            if proposal.invoice_id in matched_invoice_ids:
                _log(db, job_id, "proposal_skipped",
                     f"Invoice {proposal.invoice_id[:8]} already matched — duplicate ignored.")
                continue

            rate_info = rates.get(proposal.invoice_id, {"rate_id": None, "rate": 1.0})
            _write_match(db, job_id, proposal, inv, txn, rate_info["rate_id"], rate_info["rate"])
            matched_invoice_ids.add(proposal.invoice_id)
            matched_count += 1

        unmatched = [inv for inv in invoices if inv.invoice_id not in matched_invoice_ids]
        for inv in unmatched:
            db.table("invoice").update({"status": "unmatched"}).eq("invoice_id", inv.invoice_id).execute()
            _log(db, job_id, "invoice_unmatched",
                 f"Invoice {inv.invoice_number} ({inv.invoice_amount} {inv.invoice_currency}) — no match found.")

        total_matched = matched_count + prematched
        _complete_job(db, job_id, matched=total_matched, unmatched=len(unmatched))
        _write_recommendation(db, sme_id, job_id, unmatched)

        return {
            "status":          "completed",
            "job_id":          job_id,
            "matched_count":   total_matched,
            "unmatched_count": len(unmatched),
        }

    except Exception as exc:
        logger.exception("Reconciliation job failed.")
        db.table("reconciliation_job").update({
            "status":       JobStatus.FAILED,
            "completed_at": datetime.utcnow().isoformat(),
        }).eq("job_id", job_id).execute()
        _log(db, job_id, "job_failed", str(exc))
        raise