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
from collections import defaultdict
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


# ── Helpers ───────────────────────────────────────────────────────

def _to_utc_iso(d: date) -> str:
    return datetime.combine(d, datetime.min.time()) \
                   .replace(tzinfo=timezone.utc).isoformat()


def _log(supabase: Client, job_id: str, event_type: str, message: str, metadata: dict = None):
    try:
        entry = LogEntry(job_id=job_id, event_type=event_type,
                         message=message, metadata=metadata)
        supabase.table("reconciliation_log").insert(entry.model_dump()).execute()
    except Exception as exc:
        logger.error("Failed to write log entry: %s", exc)


def _check_cache(supabase: Client, query: ForexCacheQuery) -> tuple[str, float] | None:
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


def _call_frankfurter(req: FrankfurterRequest) -> dict[str, float]:
    """
    Calls Frankfurter and returns a plain dict of {to_currency: rate}.

    Frankfurter response shape (single or multi-quote):
      {"base": "USD", "date": "2025-05-14", "rates": {"MYR": 4.725, "EUR": 0.92}}

    Retries up to 3 times with exponential backoff.
    """
    for attempt in range(1, 4):
        try:
            resp = httpx.get(req.to_url(), timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # "rates" is always a dict — even for a single quote
            return data["rates"]
        except Exception as exc:
            logger.warning("Frankfurter attempt %d failed: %s", attempt, exc)
            if attempt < 3:
                time.sleep(attempt * 1.5)
            else:
                raise


def _insert_rate(
    supabase: Client,
    from_currency: str,
    to_currency: str,
    rate_value: float,
    txn_date: date,
) -> tuple[str, float]:
    """
    Upserts one exchange_rate row. Re-queries if upsert hits a conflict
    (handles race condition where two jobs fetch the same rate simultaneously).
    """
    row = ExchangeRateInsert(
        from_currency=from_currency,
        to_currency=to_currency,
        rate=rate_value,
        effective_at=datetime.combine(txn_date, datetime.min.time()),
    )

    payload = row.model_dump()
    payload["effective_at"] = _to_utc_iso(txn_date)
    payload.pop("fetched_at", None)

    result = (
        supabase.table("exchange_rate")
        .upsert(payload, on_conflict="from_currency,to_currency,effective_at,api_source")
        .execute()
    )

    if not result.data:
        # Another job inserted first — fetch the existing row
        result = (
            supabase.table("exchange_rate")
            .select("rate_id, rate")
            .eq("from_currency", from_currency)
            .eq("to_currency",   to_currency)
            .eq("effective_at",  _to_utc_iso(txn_date))
            .limit(1)
            .execute()
        )

    return result.data[0]["rate_id"], float(result.data[0]["rate"])


# ── Public interface ──────────────────────────────────────────────

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

    req   = FrankfurterRequest(date=txn_date, base=query.from_currency, quotes=query.to_currency)
    rates = _call_frankfurter(req)     # {"MYR": 4.725}
    rate_id, rate = _insert_rate(supabase, from_currency.upper(), to_currency.upper(),
                                 rates[to_currency.upper()], txn_date)

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
    Return a dict of (from_currency, to_currency, date_str) → (rate_id, rate).

    Batches cache misses by (base_currency, date) to minimise Frankfurter calls —
    one API call returns multiple target currencies at once.
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

    # Group misses by (base_currency, date) — one Frankfurter call per group
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for q in misses:
        groups[(q.from_currency.upper(), str(q.on_date))].append(q.to_currency.upper())

    for (base, date_str), targets in groups.items():
        txn_date = date.fromisoformat(date_str)
        req      = FrankfurterRequest(date=txn_date, base=base, quotes=",".join(targets))

        try:
            rates_dict = _call_frankfurter(req)   # {"MYR": 4.725, "EUR": 0.92, ...}
        except Exception as exc:
            logger.error("Frankfurter failed for %s on %s: %s", base, date_str, exc)
            _log(supabase, job_id, "rate_api_error",
                 f"Frankfurter failed for {base} on {date_str}.",
                 {"error": str(exc)})
            continue

        for to_currency, rate_value in rates_dict.items():
            try:
                rate_id, rate = _insert_rate(supabase, base, to_currency, rate_value, txn_date)
                results[(base, to_currency, date_str)] = (rate_id, rate)
                _log(supabase, job_id, "rate_inserted",
                     f"{base}→{to_currency} on {date_str} = {rate}.",
                     {"rate_id": rate_id, "rate": rate})
            except Exception as exc:
                logger.error("Insert failed for %s→%s: %s", base, to_currency, exc)

    return results


if __name__ == "__main__":
    import os
    from supabase import create_client
    from dotenv import load_dotenv

    load_dotenv()

    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_API_KEY"])

    job = supabase.table("reconciliation_job").insert({
        "sme_id":  "111e4567-e89b-12d3-a456-426614174111",
        "status":  "processing",
    }).execute()
    JOB_ID = job.data[0]["job_id"]
    print(f"\nCreated test job: {JOB_ID}")

    print("\n── Test 1: single rate (Frankfurter call) ──")
    rate_id, rate = get_rate(supabase, "USD", "MYR", date(2025, 5, 14), JOB_ID)
    print(f"  rate_id : {rate_id}")
    print(f"  rate    : {rate}")

    print("\n── Test 2: same call again (cache hit) ──")
    rate_id2, rate2 = get_rate(supabase, "USD", "MYR", date(2025, 5, 14), JOB_ID)
    print(f"  rate_id : {rate_id2}")
    assert rate_id == rate_id2, "FAIL — cache not working"
    print("  ✓ same rate_id — cache working")

    print("\n── Test 3: batch (USD+EUR → MYR, one API call) ──")
    batch = get_rates_batch(supabase, [
        ForexCacheQuery(from_currency="USD", to_currency="MYR", on_date=date(2025, 5, 14)),
        ForexCacheQuery(from_currency="EUR", to_currency="MYR", on_date=date(2025, 5, 14)),
    ], JOB_ID)
    for (frm, to, d), (rid, r) in batch.items():
        print(f"  {frm}→{to} on {d} : {r}  (rate_id={rid})")

    supabase.table("reconciliation_job").delete().eq("job_id", JOB_ID).execute()
    print("\nDone.")