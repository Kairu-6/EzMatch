import os
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
from forex_api import get_rates_batch

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Constants — read from .env, no client created here

SUPABASE_URL  = os.getenv("SUPABASE_URL")
SUPABASE_KEY  = os.getenv("SUPABASE_API_KEY")
MORPHEUS_URL  = os.getenv("MORPHEUS_URL", "[https://api.mor.org/api/v1/chat/completions](https://api.mor.org/api/v1/chat/completions)")
MORPHEUS_API_KEY      = os.getenv("MORPHEUS_API_KEY")
# ✅ FIX 1: Set default to the working model from your test script
MORPHEUS_MODEL        = os.getenv("MORPHEUS_MODEL", "qwen3-5-9b")
CONFIDENCE_THRESHOLD  = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))

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
    return [InvoiceForMatching(**r) for r in rows]


def _fetch_transactions(db: Client, sme_id: str, days: int = 30) -> list[TransactionForMatching]:
    cutoff = (datetime.utcnow().date() - timedelta(days=days)).isoformat()
    rows = (
        db.table("bank_transaction")
        .select(
            "transaction_id, transaction_date, description, description_normalised, "
            "debit_amount, credit_amount, currency_code, "
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
        txn_blocks.append(
            f"TRANSACTION {txn.transaction_id}:\n"
            f"  date:           {txn.transaction_date}\n"
            f"  description:    {txn.description_normalised}\n"
            f"  amount:         {amount_display}\n"
        )

    return f"""You are a financial reconciliation engine for a cross-border payment system.

Your task: match each INVOICE to the BANK TRANSACTION that most likely represents its payment.

Rules:
- Base your matching on semantic similarity of counterparty names and descriptions.
- Use the pre-calculated converted amounts (in MYR) to verify the amounts align within a reasonable tolerance.
- A negative variance (transaction < converted) is normal — it means bank fees were deducted.
- Assign a confidence score between 0.0 and 1.0.
- One invoice maps to at most one transaction. One transaction maps to at most one invoice.
- If no transaction is a plausible match for an invoice, do not force a match.
- Include proof_id in your proposal if a payment proof was provided for that invoice.

INVOICES TO MATCH:
{''.join(invoice_blocks)}

BANK TRANSACTIONS (last 30 days, unmatched only):
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

# ✅ FIX 2: Super Debug Mode for API Call
def _call_morpheus(prompt: str) -> list[MorpheusMatchProposal]:
    print("\n" + "="*60)
    print("🤖 [DEBUG] SENDING PROMPT TO MORPHEUS:")
    print("="*60)
    print(prompt)
    print("="*60 + "\n")

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
        
    print(f"⏳ Waiting for Morpheus to respond at {target_url}...")
    print(f"🧠 Using Model: {MORPHEUS_MODEL}")
    print("⏱️  Timeout set to 180 seconds. Please wait...")
    
    # HARDCODED TIMEOUT TO 180 SECONDS
    response = httpx.post(target_url, json=payload, headers=headers, timeout=180.0)
    
    print(f"⚡ Status Code: {response.status_code}")
    response.raise_for_status()

    raw_text = response.json()["choices"][0]["message"]["content"].strip()
    
    print("\n" + "="*60)
    print("💬 [DEBUG] RAW RESPONSE FROM MORPHEUS:")
    print("="*60)
    print(raw_text)
    print("="*60 + "\n")

    # ✅ FIX 3: Bulletproof JSON cleaner (strips markdown formatting)
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
        print(f"❌ CRITICAL PARSING ERROR: Morpheus did not return valid JSON. Error: {e}")
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
):
    match = ReconciliationMatchInsert.build(
        job_id=job_id,
        proposal=proposal,
        invoice=invoice,
        transaction=transaction,
        rate_id=rate_id,
        rate=rate,
        threshold=CONFIDENCE_THRESHOLD,
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
        invoices     = _fetch_invoices(db, sme_id)
        transactions = _fetch_transactions(db, sme_id)
        proofs       = _fetch_proofs(db, sme_id)

        _log(db, job_id, "documents_fetched",
             f"Fetched {len(invoices)} invoices, {len(transactions)} transactions, {len(proofs)} proofs.")

        if not invoices:
            _log(db, job_id, "job_skipped", "No pending invoices — nothing to reconcile.")
            _complete_job(db, job_id, matched=0, unmatched=0)
            return {"status": "skipped", "reason": "no_pending_invoices"}

        if not transactions:
            _log(db, job_id, "job_skipped", "No unmatched transactions in the last 30 days.")
            _complete_job(db, job_id, matched=0, unmatched=len(invoices))
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

        _complete_job(db, job_id, matched=matched_count, unmatched=len(unmatched))
        _write_recommendation(db, sme_id, job_id, unmatched)

        return {
            "status":          "completed",
            "job_id":          job_id,
            "matched_count":   matched_count,
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