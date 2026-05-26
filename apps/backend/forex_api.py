"""
forex_api.py
============
Two public functions:
  - get_rate(supabase, from_currency, to_currency, txn_date, job_id)
  - get_rates_batch(supabase, queries, job_id)

Both return (rate_id, rate). Cache-first — only calls Frankfurter
on a miss. Logs every event to reconciliation_log.
"""

import logging
import time
from datetime import date, datetime, timezone

import httpx
from supabase import Client

from data_contracts import (
    ExchangeRateInsert,
    ForexCacheQuery,
    FrankfurterRequest,
    FrankfurterResponse,
    LogEntry,
)

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────

def _to_utc_iso(d: date) -> str:
    """Convert a date to midnight UTC ISO string for TIMESTAMPTZ comparison."""
    return datetime.combine(d, datetime.min.time()) \
                   .replace(tzinfo=timezone.utc).isoformat()


def _log(supabase: Client, job_id: str, event_type: str, message: str, metadata: dict = None):
    """Write one row to reconciliation_log. Non-fatal if it fails."""
    try:
        entry = LogEntry(job_id=job_id, event_type=event_type,
                         message=message, metadata=metadata)
        supabase.table("reconciliation_log").insert(entry.model_dump()).execute()
    except Exception as exc:
        logger.error("Failed to write log entry: %s", exc)


def _check_cache(supabase: Client, query: ForexCacheQuery) -> tuple[str, float] | None:
    """Return (rate_id, rate) if row exists in exchange_rate, else None."""
    result = (
        supabase.table("exchange_rate")
        .select("rate_id, rate")
        .eq("from_currency", query.from_currency)
        .eq("to_currency",   query.to_currency)
        .eq("effective_at",  _to_utc_iso(query.on_date))
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["rate_id"], float(result.data[0]["rate"])
    return None


def _call_frankfurter(req: FrankfurterRequest) -> list[FrankfurterResponse]:
    for attempt in range(1, 4):
        try:
            resp = httpx.get(req.to_url(), timeout=10)
            resp.raise_for_status()
            return [FrankfurterResponse(**item) for item in resp.json()]  # parse all items
        except Exception as exc:
            logger.warning("Frankfurter attempt %d failed: %s", attempt, exc)
            if attempt < 3:
                time.sleep(attempt * 1.5)
            else:
                raise


def _insert_rate(
    supabase: Client,
    api_response: FrankfurterResponse,
    txn_date: date,
) -> tuple[str, float]:
    """Insert one exchange_rate row. Re-queries if upsert hits a conflict."""
    row = ExchangeRateInsert.from_api_response(api_response, txn_date)

    payload = row.model_dump()
    payload["effective_at"] = _to_utc_iso(txn_date)
    payload.pop("fetched_at", None)   # DB default handles this

    result = (
        supabase.table("exchange_rate")
        .upsert(payload, on_conflict="from_currency,to_currency,effective_at,api_source")
        .execute()
    )

    # if another job inserted the same row first, upsert returns empty
    if not result.data:
        result = (
            supabase.table("exchange_rate")
            .select("rate_id, rate")
            .eq("from_currency", row.from_currency)
            .eq("to_currency",   row.to_currency)
            .eq("effective_at",  _to_utc_iso(txn_date))
            .limit(1)
            .execute()
        )

    return result.data[0]["rate_id"], float(result.data[0]["rate"])


# ── public interface ──────────────────────────────────────────────

def get_rate(
    supabase: Client,
    from_currency: str,
    to_currency: str,
    txn_date: date,
    job_id: str,
) -> tuple[str, float]:
    """
    Return (rate_id, rate) for one currency pair on txn_date.
    Checks the exchange_rate table first; calls Frankfurter only on a miss.

    Called by the Orchestrator once per invoice before building a match.
    """
    query = ForexCacheQuery(
        from_currency=from_currency.upper(),
        to_currency=to_currency.upper(),
        on_date=txn_date,
    )

    cached = _check_cache(supabase, query)
    if cached:
        _log(supabase, job_id, "rate_cache_hit",
             f"{from_currency}→{to_currency} on {txn_date} served from cache.",
             {"rate": cached[1]})
        return cached

    _log(supabase, job_id, "rate_api_call",
         f"Calling Frankfurter for {from_currency}→{to_currency} on {txn_date}.")

    req = FrankfurterRequest(date=txn_date, base=query.from_currency, quotes=query.to_currency)
    api_responses = _call_frankfurter(req)
    rate_id, rate = _insert_rate(supabase, api_responses[0], txn_date)

    _log(supabase, job_id, "rate_inserted",
         f"{from_currency}→{to_currency} on {txn_date} = {rate}.",
         {"rate_id": rate_id, "rate": rate})

    return rate_id, rate


def get_rates_batch(
    supabase: Client,
    queries: list[ForexCacheQuery],
    job_id: str,
) -> dict[tuple[str, str, str], tuple[str, float]]:
    """
    Return a dict of (from_currency, to_currency, date_str) → (rate_id, rate)
    for a list of ForexCacheQuery objects.

    Batches cache misses by (base, date) to minimise Frankfurter calls —
    one API call can return multiple target currencies at once.

    Called by the Orchestrator at job start to prefetch all needed rates.
    """
    results = {}
    misses  = []

    for q in queries:
        key    = (q.from_currency.upper(), q.to_currency.upper(), str(q.on_date))
        cached = _check_cache(supabase, q)
        if cached:
            results[key] = cached
        else:
            misses.append(q)

    _log(supabase, job_id, "rate_batch_start",
         f"{len(queries)} rates requested, {len(misses)} need API calls.",
         {"total": len(queries), "misses": len(misses)})

    # group misses by (base_currency, date) — one Frankfurter call per group
    from collections import defaultdict
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for q in misses:
        groups[(q.from_currency.upper(), str(q.on_date))].append(q.to_currency.upper())

    for (base, date_str), targets in groups.items():
        txn_date = date.fromisoformat(date_str)
        req = FrankfurterRequest(date=txn_date, base=base, quotes=",".join(targets))
        
        try:
            api_responses = _call_frankfurter(req)
        except Exception as e:
            logger.error(f"API Call failed for {base} on {date_str}: {str(e)}")
            continue

        for api_response in api_responses:
            
            # Insert into database
            rate_id, rate = _insert_rate(supabase, api_response, txn_date)
            
            # Map the result back using the object's own built-in base/quote knowledge
            results[(api_response.base, api_response.quote, date_str)] = (rate_id, rate)
            
            # ✅ FIXED: Changed parameter names from status/details to event_type/metadata
            _log(
                supabase=supabase, 
                job_id=job_id, 
                event_type="rate_inserted",
                message=f"{api_response.base}→{api_response.quote} on {date_str} = {rate}.",
                metadata={"rate_id": rate_id, "rate": rate}
            )

    return results