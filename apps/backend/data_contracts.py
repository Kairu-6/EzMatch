"""
data_contracts.py
=================
Pydantic input/output schemas for every component that reads from
or writes to the Global Treasury Agent database.

Components covered:
  1. statementparser.py      → bank_transaction
  2. Chutes image/PDF parser → payment_proof
  3. Frankfurter forex API   → exchange_rate
  4. Orchestrator            → reconciliation_job, reconciliation_match,
                               reconciliation_log, recommendation
                             → response sent back to frontend
"""

from __future__ import annotations
from typing import Optional
from datetime import date, datetime
from typing import Any
from pydantic import BaseModel, field_validator
from enum import Enum


# ══════════════════════════════════════════════════════════════════
# SHARED ENUMS  (mirror CHECK constraints in the SQL schema)
# ══════════════════════════════════════════════════════════════════

class ParseStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"

class InvoiceStatus(str, Enum):
    PENDING    = "pending"
    MATCHED    = "matched"
    PARTIAL    = "partial"
    UNMATCHED  = "unmatched"
    DISPUTED   = "disputed"

class MatchStatus(str, Enum):
    AUTO           = "auto"
    MANUAL         = "manual"
    REJECTED       = "rejected"
    PENDING_REVIEW = "pending_review"

class JobStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETED  = "completed"
    FAILED     = "failed"
    CANCELLED  = "cancelled"

class RecType(str, Enum):
    FEE_OPTIMIZATION = "fee_optimization"
    TIMING           = "timing"
    BANK_SELECTION   = "bank_selection"
    FX_EXPOSURE      = "fx_exposure"
    GENERAL          = "general"


# ══════════════════════════════════════════════════════════════════
# 1.  STATEMENTPARSER.PY  →  bank_transaction
# ══════════════════════════════════════════════════════════════════
# Your partner's parser outputs a signed `amount` float and uses
# the key `date` instead of `transaction_date`. The backend must
# transform this before upserting into Supabase.
#
# DB table:  bank_transaction
# Trigger:   SME uploads CSV / Excel via frontend
# Writer:    statementparser.py  (via service_role key)
# ──────────────────────────────────────────────────────────────────

class TransactionSchema(BaseModel):
    transaction_id:         str
    transaction_date:       str
    description:            str
    description_normalised: str
    reference_number:       str | None = None
    debit_amount:           float | None
    credit_amount:          float | None
    currency_code:          str
    running_balance:        float | None
    is_matched:             bool = False

    @field_validator("currency_code")
    @classmethod
    def currency_must_be_iso(cls, v: str) -> str:
        if not v or not v.isalpha() or len(v) != 3:
            raise ValueError(f"Currency '{v}' is not a valid 3-letter ISO 4217 code.")
        return v.upper()

    @field_validator("transaction_date")
    @classmethod
    def date_must_be_iso(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Date '{v}' is not in ISO 8601 format (YYYY-MM-DD).")
        return v


# Supabase upsert (run this after building BankTransactionInsert):
#
#   supabase.table("bank_transaction") \
#       .upsert(row.model_dump(), on_conflict="transaction_id") \
#       .execute()


# ══════════════════════════════════════════════════════════════════
# 2.  CHUTES IMAGE / PDF PARSER  →  payment_proof
# ══════════════════════════════════════════════════════════════════
# The frontend creates the payment_proof row on upload
# (parse_status = pending). Chutes then receives the file, extracts
# structured fields, and calls back to update that same row.
#
# DB table:  payment_proof
# Trigger:   SME uploads image / PDF via frontend
# Writer:
#   INSERT  → frontend           (on upload, status = pending)
#   UPDATE  → Chutes parser      (after extraction, fills parsed_* fields)
# ──────────────────────────────────────────────────────────────────

class ChutesParserInput(BaseModel):
    """
    What the backend sends TO the Chutes parser.
    """
    proof_id:  str   # UUID — so the parser knows which row to update
    file_path: str   # path / presigned URL to the uploaded file
    file_type: str   # "pdf" | "png" | "jpg" | "jpeg" | "webp"


class ParsedProofData(BaseModel):
    """
    Raw extraction detail stored in payment_proof.parsed_data (JSONB).
    All fields are optional — not every document type contains all of them.
    """
    sender_name:       str | None = None  # who sent the payment
    receiver_name:     str | None = None  # who received it
    bank_name:         str | None = None  # issuing bank
    swift_code:        str | None = None  # SWIFT/BIC if present
    iban:              str | None = None
    account_number:    str | None = None
    raw_text:          str | None = None  # full OCR dump for debugging
    confidence_scores: dict[str, float] | None = None  # per-field model confidence


class ChutesParserOutput(BaseModel):
    proof_id:         str
    status:           ParseStatus         
    parsed_amount:    float | None = None          # <-- Added = None
    parsed_currency:  str | None = None            # <-- Added = None
    parsed_date:      str | None = None            # <-- Added = None
    parsed_reference: str | None = None            # <-- Added = None
    parsed_data:      ParsedProofData | None = None # <-- Added = None
    message:          str | None = None   

    @field_validator("parsed_currency")
    @classmethod
    def currency_uppercase(cls, v: str | None) -> str | None:
        return v.upper() if v else None


# Example update that the backend runs after receiving ChutesParserOutput:
#
#   supabase.table("payment_proof") \
#       .update({
#           "parse_status":     output.status,
#           "parsed_amount":    output.parsed_amount,
#           "parsed_currency":  output.parsed_currency,
#           "parsed_date":      output.parsed_date,
#           "parsed_reference": output.parsed_reference,
#           "parsed_data":      output.parsed_data.model_dump() if output.parsed_data else None,
#       }) \
#       .eq("proof_id", output.proof_id) \
#       .execute()


# ══════════════════════════════════════════════════════════════════
# 3.  FRANKFURTER API  →  exchange_rate
# ══════════════════════════════════════════════════════════════════
# Always check the exchange_rate table first (cache-first).
# Only call Frankfurter if no row exists for that pair + date.
# Rows are immutable once inserted — never update them.
#
# DB table:  exchange_rate
# Trigger:   Orchestrator, at start of reconciliation job
# Writer:    Orchestrator  (via service_role key)
# ──────────────────────────────────────────────────────────────────

class ForexCacheQuery(BaseModel):
    """
    Cache check: query exchange_rate before calling the API.

    SQL equivalent:
      SELECT rate_id, rate
      FROM exchange_rate
      WHERE from_currency = :from_currency
        AND to_currency   = :to_currency
        AND effective_at::date = :on_date
      LIMIT 1;
    """
    from_currency: str   # e.g. "USD"
    to_currency:   str   # e.g. "MYR"
    on_date:       date  # the bank transaction date — NOT today


class FrankfurterRequest(BaseModel):
    """
    Parameters for GET https://api.frankfurter.dev/v2/rates
    Only called when ForexCacheQuery returns no result.
    """
    date:          date        # effective_at — the transaction date
    base:          str         # from_currency
    quotes:        str         # to_currency (comma-separated for multiple)

    def to_url(self) -> str:
        return (
            f"https://api.frankfurter.dev/v2/rates"
            f"?date={self.date}&base={self.base}&quotes={self.quotes}"
        )


class FrankfurterResponse(BaseModel):
    """
    Frankfurter API response shape.
    Example: {"base":"USD","date":"2025-05-14","rates":{"MYR":4.725}}
    """
    base:  str
    date:  str             # YYYY-MM-DD returned by the API
    quote: str          # was "rates: dict" — API returns single target as "quote"
    rate:  float


class ExchangeRateInsert(BaseModel):
    """
    Row inserted into exchange_rate after a successful API call.

    DB columns mapped:
      from_currency  ← from_currency
      to_currency    ← to_currency
      rate           ← rate
      effective_at   ← effective_at  (the transaction date, not now)
      api_source     ← "frankfurter"
      fetched_at     ← datetime.utcnow()
    """
    from_currency: str
    to_currency:   str
    rate:          float
    effective_at:  datetime   # set to transaction date at midnight UTC
    api_source:    str = "frankfurter"
    fetched_at:    datetime = None

    def model_post_init(self, __context: Any) -> None:
        if self.fetched_at is None:
            self.fetched_at = datetime.utcnow()

    @classmethod
    def from_api_response(
        cls,
        response: FrankfurterResponse,
        transaction_date: date,
    ) -> "ExchangeRateInsert":
        return cls(
            from_currency = response.base,
            to_currency   = response.quote,   # was response.rates[to_currency]
            rate          = response.rate,    # was response.rates[to_currency]
            effective_at  = datetime.combine(transaction_date, datetime.min.time()),
        )


# Full cache-first fetch pattern used by the Orchestrator:
#
#   def get_or_fetch_rate(
#       from_currency: str,
#       to_currency:   str,
#       txn_date:      date,
#   ) -> tuple[str, float]:           # returns (rate_id, rate)
#
#       # 1. check cache
#       result = supabase.table("exchange_rate") \
#           .select("rate_id, rate") \
#           .eq("from_currency", from_currency) \
#           .eq("to_currency",   to_currency) \
#           .eq("effective_at",  datetime.combine(txn_date, datetime.min.time()).isoformat()) \
#           .limit(1).execute()
#
#       if result.data:
#           return result.data[0]["rate_id"], result.data[0]["rate"]
#
#       # 2. call Frankfurter
#       req = FrankfurterRequest(date=txn_date, base=from_currency, quotes=to_currency)
#       api_resp = httpx.get(req.to_url()).json()
#       parsed = FrankfurterResponse(**api_resp)
#
#       # 3. insert and return
#       row = ExchangeRateInsert.from_api_response(parsed, to_currency, txn_date)
#       inserted = supabase.table("exchange_rate").insert(row.model_dump()).execute()
#       return inserted.data[0]["rate_id"], row.rate


# ══════════════════════════════════════════════════════════════════
# 4.  ORCHESTRATOR INPUT  (reads from DB to run the job)
# ══════════════════════════════════════════════════════════════════
# These are the objects the Orchestrator assembles from Supabase
# before passing to Morpheus for semantic matching.
# ──────────────────────────────────────────────────────────────────

class InvoiceForMatching(BaseModel):
    """Subset of invoice columns Morpheus needs."""
    invoice_id:        str
    invoice_number:    str
    counterparty_name: str
    invoice_currency:  str
    invoice_amount:    float
    invoice_date:      date
    due_date:          date | None = None


class TransactionForMatching(BaseModel):
    """Subset of bank_transaction columns Morpheus needs."""
    transaction_id:         str    # SHA-256
    transaction_date:       date
    description:            str    # raw — for display
    description_normalised: str    # cleaned — what Morpheus actually reads
    debit_amount:           float | None
    credit_amount:          float | None
    currency_code:          str


class ProofForMatching(BaseModel):
    """Subset of payment_proof columns Morpheus uses as corroboration."""
    proof_id:         str
    parsed_amount:    float | None
    parsed_currency:  str | None
    parsed_date:      str | None
    parsed_reference: str | None
    parsed_data:      dict | None


class OrchestratorJobInput(BaseModel):
    """
    Everything the Orchestrator assembles and passes to Morpheus.
    Built by querying Supabase before starting reconciliation_job.
    """
    job_id:       str
    sme_id:       str
    invoices:     list[InvoiceForMatching]
    transactions: list[TransactionForMatching]
    proofs:       list[ProofForMatching]


# ══════════════════════════════════════════════════════════════════
# 5.  MORPHEUS OUTPUT  →  reconciliation_match  +  invoice update
# ══════════════════════════════════════════════════════════════════
# Morpheus returns a list of proposed matches.
# The Orchestrator validates and writes each one to the DB.
# ──────────────────────────────────────────────────────────────────

class MorpheusMatchProposal(BaseModel):
    """
    One match proposed by Morpheus.
    The Orchestrator fetches rate_id via get_or_fetch_rate() before
    writing the final ReconciliationMatchInsert.
    """
    invoice_id:     str
    transaction_id: str
    proof_id:       str | None    # None if no proof was uploaded for this invoice
    confidence:     float         # 0.0 – 1.0


class ReconciliationMatchInsert(BaseModel):
    """
    Final row written to reconciliation_match.
    All amount fields are snapshots — frozen at match time.

    DB columns mapped:
      job_id             ← job_id
      invoice_id         ← invoice_id
      transaction_id     ← transaction_id  (TEXT, SHA-256)
      proof_id           ← proof_id        (nullable)
      rate_id            ← rate_id         (from exchange_rate cache)
      match_confidence   ← confidence
      invoice_amount     ← snapshot of invoice.invoice_amount
      invoice_currency   ← snapshot of invoice.invoice_currency
      transaction_amount ← credit_amount from bank_transaction
      tx_currency        ← currency_code  from bank_transaction
      converted_amount   ← invoice_amount × rate
      variance_amount    ← transaction_amount − converted_amount
      variance_pct       ← (variance_amount / converted_amount) × 100
      match_status       ← "auto" if confidence ≥ threshold, else "pending_review"
    """
    job_id:             str
    invoice_id:         str
    transaction_id:     str
    proof_id:           str | None
    rate_id:          str | None = None
    match_confidence:   float
    invoice_amount:     float
    invoice_currency:   str
    transaction_amount: float
    tx_currency:        str
    converted_amount:   float
    variance_amount:    float
    variance_pct:       float
    match_status:       MatchStatus

    @classmethod
    def build(
        cls,
        job_id:      str,
        proposal:    MorpheusMatchProposal,
        invoice:     InvoiceForMatching,
        transaction: TransactionForMatching,
        rate:        float,
        rate_id: Optional[str] = None,
        threshold:   float = 0.75,
    ) -> "ReconciliationMatchInsert":
        txn_amount    = transaction.credit_amount or 0.0
        converted     = round(invoice.invoice_amount * rate, 4)
        variance      = round(txn_amount - converted, 4)
        variance_pct  = round((variance / converted) * 100, 4) if converted else 0.0

        return cls(
            job_id             = job_id,
            invoice_id         = invoice.invoice_id,
            transaction_id     = transaction.transaction_id,
            proof_id           = proposal.proof_id,
            rate_id            = rate_id,
            match_confidence   = proposal.confidence,
            invoice_amount     = invoice.invoice_amount,
            invoice_currency   = invoice.invoice_currency,
            transaction_amount = txn_amount,
            tx_currency        = transaction.currency_code,
            converted_amount   = converted,
            variance_amount    = variance,
            variance_pct       = variance_pct,
            match_status       = MatchStatus.AUTO if proposal.confidence >= threshold
                                 else MatchStatus.PENDING_REVIEW,
        )


# ══════════════════════════════════════════════════════════════════
# 6.  RECONCILIATION LOG  →  reconciliation_log
# ══════════════════════════════════════════════════════════════════

class LogEntry(BaseModel):
    """
    One append-only event written to reconciliation_log during a job.
    metadata holds any structured context useful for debugging.
    """
    job_id:     str
    event_type: str        # e.g. "job_started", "rate_fetched", "match_written", "job_failed"
    message:    str
    metadata:   dict | None = None


# ══════════════════════════════════════════════════════════════════
# 7.  ORCHESTRATOR RESPONSE  →  frontend
# ══════════════════════════════════════════════════════════════════
# After the job completes, the Orchestrator sends this payload
# to the frontend via the Node.js API layer.
# The frontend uses it to render the reconciliation dashboard.
# ──────────────────────────────────────────────────────────────────

class MatchedInvoiceSummary(BaseModel):
    """One confirmed match — shown as a row in the results table."""
    match_id:          str
    match_status:      MatchStatus
    match_confidence:  float

    # invoice side
    invoice_number:    str
    counterparty_name: str
    invoice_amount:    float
    invoice_currency:  str
    invoice_date:      date

    # transaction side
    transaction_date:  date
    description:       str
    transaction_amount: float
    tx_currency:        str

    # fx + reconciliation
    rate:              float
    rate_date:         date
    converted_amount:  float
    variance_amount:   float
    variance_pct:      float

    # proof (optional)
    proof_id:          str | None
    parsed_reference:  str | None


class UnmatchedInvoiceSummary(BaseModel):
    """Invoice that could not be matched — shown in the review queue."""
    invoice_id:        str
    invoice_number:    str
    counterparty_name: str
    invoice_amount:    float
    invoice_currency:  str
    invoice_date:      date
    reason:            str   # "no_matching_transaction" | "low_confidence" | "proof_parse_failed"


class RecommendationSummary(BaseModel):
    """One AI insight shown in the recommendations panel."""
    recommendation_id: str
    rec_type:          RecType
    content:           str
    estimated_saving:  float | None


class JobSummary(BaseModel):
    """Top-level stats shown in the dashboard header."""
    total_invoices:   int
    matched_count:    int
    unmatched_count:  int
    pending_review:   int    # matches with match_status = pending_review
    started_at:       datetime
    completed_at:     datetime
    duration_seconds: float


class OrchestratorFrontendResponse(BaseModel):
    """
    Full payload returned to the frontend after a reconciliation job.
    The Node.js API layer forwards this directly or reshapes it for the UI.

    Shape mirrors the DB reads:
      job          ← reconciliation_job
      matches      ← reconciliation_match JOIN invoice, bank_transaction, exchange_rate
      unmatched    ← invoices WHERE status != 'matched'
      recs         ← recommendation WHERE job_id = job_id
    """
    job_id:    str
    sme_id:    str
    status:    JobStatus
    summary:   JobSummary
    matches:   list[MatchedInvoiceSummary]
    unmatched: list[UnmatchedInvoiceSummary]
    recs:      list[RecommendationSummary]