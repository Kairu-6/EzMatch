"""
agent/memory.py
===============
Two of the agent's three memory layers live here:

  1. Working memory  — the in-flight `messages[]` thread the model reasons over.
                       This is what turns a one-shot call into a *loop*.
  2. Episodic memory — every step is also persisted to `reconciliation_log`
                       (the table already exists) with a {step, phase, ts}
                       envelope. That durable trace is what the frontend replays
                       and what an auditor reads after the fact.

The third layer (long-term *learned* memory, derived from human corrections) is
Phase B and lives in `load_learned()` below — a stub for now.
"""
import logging
import os
import statistics
from collections import defaultdict
from datetime import datetime

from supabase import Client

# Reuse the orchestrator's logger so agent + legacy paths write identical rows.
from orchestrator import _log as _orch_log

logger = logging.getLogger(__name__)

# Keep working memory from growing unbounded over a long loop. The durable copy
# of everything lives in reconciliation_log, so trimming the in-flight thread is
# safe. System + goal (first two messages) are always retained.
MAX_WORKING_CHARS = 24000

# Long-term learned memory bounds (env-overridable). SCAN_LIMIT caps how many
# rows we pull; the MAX_* caps how many lines actually reach the prompt.
LEARNED_SCAN_LIMIT    = int(os.getenv("LEARNED_SCAN_LIMIT", "200"))
LEARNED_MAX_EXEMPLARS = int(os.getenv("LEARNED_MAX_EXEMPLARS", "8"))
LEARNED_MAX_BLOCKLIST = int(os.getenv("LEARNED_MAX_BLOCKLIST", "5"))


class AgentMemory:
    def __init__(self, db: Client, job_id: str):
        self.db = db
        self.job_id = job_id
        self._messages: list[dict] = []
        self.step = 0
        self.phase = "plan"

    # ── working memory ────────────────────────────────────────────
    def add_system(self, content: str) -> None:
        self._messages.append({"role": "system", "content": content})

    def add_user(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def add(self, message: dict) -> None:
        """Append a raw message dict (assistant turn or tool/observation result)."""
        self._messages.append(message)

    @property
    def messages(self) -> list[dict]:
        """The thread sent to the model, trimmed to a character budget."""
        if len(self._messages) <= 2:
            return self._messages
        head = self._messages[:2]                 # system + goal, always kept
        tail = self._messages[2:]
        budget = MAX_WORKING_CHARS
        kept: list[dict] = []
        for msg in reversed(tail):                # keep most-recent within budget
            size = len(str(msg.get("content") or "")) + 200
            if budget - size < 0 and kept:
                break
            budget -= size
            kept.append(msg)
        kept.reverse()
        return head + kept

    # ── episodic memory (durable trace) ───────────────────────────
    def persist(self, event_type: str, message: str, metadata: dict = None,
                phase: str = None) -> None:
        envelope = {
            "step":  self.step,
            "phase": phase or self.phase,
            "ts":    datetime.utcnow().isoformat(),
        }
        if metadata:
            envelope.update(metadata)
        _orch_log(self.db, self.job_id, event_type, message, envelope)


# ── long-term learned memory (Phase B.1) ──────────────────────────
_EMPTY_LEARNED = {"summary": "", "exemplars": [], "blocklist": []}


def _fmt_variance(v) -> str:
    try:
        return f"{float(v):+.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _trim(text, width: int = 48) -> str:
    text = (text or "").strip()
    return text if len(text) <= width else text[: width - 1] + "…"


def load_learned(db: Client, sme_id: str) -> dict:
    """
    Long-term learned memory: distil priors from this workspace's history.

    Positive signal — `reconciliation_match.match_status = 'manual'`: matches a
    human confirmed (resolved from the audit queue) despite the agent being
    unsure. We group these by counterparty to teach the agent which recurring
    vendor / bank-description / variance shapes humans keep validating.

    Negative signal — `reconciliation_log` rows with `event_type='match_rejected'`:
    pairings the deterministic gate killed (there is no `rejected` status in
    reconciliation_match — a rejected proposal is never written). These become a
    small avoid-list.

    Returns {"summary", "exemplars", "blocklist"}; only `summary` is injected into
    the system prompt today. On a fresh workspace (or any error) it returns the
    empty contract so the loop runs byte-identically to Phase A.
    """
    try:
        # 1. Scope to this SME — reconciliation_match has no sme_id; reach it via
        #    job_id → reconciliation_job.sme_id.
        jobs = (db.table("reconciliation_job")
                  .select("job_id").eq("sme_id", sme_id).execute().data) or []
        job_ids = [j["job_id"] for j in jobs]
        if not job_ids:
            return dict(_EMPTY_LEARNED)

        exemplars = _load_positives(db, job_ids)
        blocklist = _load_blocklist(db, job_ids)
        summary = _format_summary(exemplars, blocklist)
        return {"summary": summary, "exemplars": exemplars, "blocklist": blocklist}
    except Exception as exc:  # learned memory must never break a run
        logger.warning("load_learned failed for sme %s: %s", sme_id, exc)
        return dict(_EMPTY_LEARNED)


def _load_positives(db: Client, job_ids: list[str]) -> list[dict]:
    """Human-confirmed matches, aggregated into one exemplar per counterparty."""
    rows = (db.table("reconciliation_match")
              .select("transaction_id, match_confidence, variance_pct, matched_at, "
                      "invoice(counterparty_name)")
              .in_("job_id", job_ids).eq("match_status", "manual")
              .order("matched_at", desc=True)
              .limit(LEARNED_SCAN_LIMIT).execute().data) or []
    if not rows:
        return []

    # A representative bank description per transaction (separate lookup — avoids
    # depending on a match→bank_transaction embed relationship).
    txn_ids = [r["transaction_id"] for r in rows if r.get("transaction_id")]
    desc_by_txn: dict[str, str] = {}
    if txn_ids:
        txns = (db.table("bank_transaction")
                  .select("transaction_id, description_normalised")
                  .in_("transaction_id", txn_ids).execute().data) or []
        desc_by_txn = {t["transaction_id"]: t.get("description_normalised") or ""
                       for t in txns}

    grouped: dict[str, dict] = defaultdict(
        lambda: {"variances": [], "count": 0, "desc": ""})
    for r in rows:  # rows are newest-first, so the first desc seen is most recent
        name = ((r.get("invoice") or {}).get("counterparty_name") or "Unknown").strip()
        g = grouped[name]
        g["count"] += 1
        if r.get("variance_pct") is not None:
            g["variances"].append(float(r["variance_pct"]))
        if not g["desc"]:
            g["desc"] = desc_by_txn.get(r.get("transaction_id"), "")

    # Most-confirmed counterparties first.
    ordered = sorted(grouped.items(), key=lambda kv: kv[1]["count"], reverse=True)
    exemplars: list[dict] = []
    for name, g in ordered[:LEARNED_MAX_EXEMPLARS]:
        median_var = statistics.median(g["variances"]) if g["variances"] else None
        exemplars.append({
            "counterparty": name,
            "count": g["count"],
            "bank_desc": _trim(g["desc"]),
            "median_variance_pct": (round(median_var, 1)
                                    if median_var is not None else None),
        })
    return exemplars


def _load_blocklist(db: Client, job_ids: list[str]) -> list[dict]:
    """Recent gate-rejected pairings, deduped, as a small avoid-list."""
    rows = (db.table("reconciliation_log")
              .select("metadata, created_at")
              .in_("job_id", job_ids).eq("event_type", "match_rejected")
              .order("created_at", desc=True)
              .limit(LEARNED_SCAN_LIMIT).execute().data) or []

    seen: set[tuple] = set()
    blocklist: list[dict] = []
    for r in rows:
        meta = r.get("metadata") or {}
        inv_no = meta.get("invoice_number") or "?"
        txn = (meta.get("transaction_id") or "")[:8]
        key = (inv_no, txn)
        if key in seen:
            continue
        seen.add(key)
        blocklist.append({
            "invoice_number": inv_no,
            "transaction_id": txn,
            "variance_pct": meta.get("variance_pct"),
        })
        if len(blocklist) >= LEARNED_MAX_BLOCKLIST:
            break
    return blocklist


def _format_summary(exemplars: list[dict], blocklist: list[dict]) -> str:
    """Deterministic prose block. Empty string when there is nothing to teach."""
    parts: list[str] = []

    if exemplars:
        total = sum(e["count"] for e in exemplars)
        lines = [f"Based on {total} past human-confirmed match(es) for this workspace:"]
        for e in exemplars:
            desc = f' (bank desc "{e["bank_desc"]}")' if e["bank_desc"] else ""
            var = (f"; typical variance {e['median_variance_pct']:+.1f}%"
                   if e["median_variance_pct"] is not None else "")
            times = "1×" if e["count"] == 1 else f"{e['count']}×"
            lines.append(f'  - "{e["counterparty"]}"{desc} — confirmed {times}{var}')
        lines.append(
            "When a current invoice matches one of these (same counterparty or a "
            "similar bank description), prefer that pairing and calibrate confidence "
            "upward — a human has already validated this shape. Cross-border fees "
            "make a small negative variance normal.")
        parts.append("\n".join(lines))

    if blocklist:
        lines = ["Pairings previously rejected — avoid unless the evidence is now clearly stronger:"]
        for b in blocklist:
            lines.append(f"  - {b['invoice_number']} ✗ txn {b['transaction_id']}… "
                         f"(variance {_fmt_variance(b['variance_pct'])})")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)
