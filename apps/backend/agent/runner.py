"""
agent/runner.py
===============
The agent loop — the public entry point that replaces the linear
`run_reconciliation` when USE_AGENT=true.

A single tool-using agent reasons over one message thread (working memory),
calling tools until it finishes or hits a guardrail. Every step is persisted to
reconciliation_log (episodic memory / the frontend trace). The model only
*proposes*; the deterministic gate inside `propose_match` governs commits.

Guardrails: step cap, wall-clock deadline, per-call timeout (in llm.py),
tool errors fed back to the model, user-cancellable, and a one-shot fallback to
the legacy pipeline if the model is unreachable before any progress. The job row
ALWAYS reaches a terminal state (completed / cancelled / failed).
"""
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from dotenv import load_dotenv
from supabase import create_client

import orchestrator
from agent import llm, prompts, verifier, anomaly
from agent import tools as tools_mod
from agent.memory import AgentMemory, load_learned

load_dotenv()
logger = logging.getLogger(__name__)

SUPABASE_URL       = os.getenv("SUPABASE_URL")
SUPABASE_KEY       = os.getenv("SUPABASE_API_KEY")
# Reconciliation runs in BATCHES: the invoices left after the reference pre-pass are
# split into small groups, and each group gets a short, focused sub-loop with a
# candidate-retrieval tool instead of a whole-ledger dump. This keeps working memory
# bounded (the old single loop drowned in context and re-listed forever) and scales to
# hundreds of rows. Tunable via env.
BATCH_SIZE         = int(os.getenv("AGENT_BATCH_SIZE", "12"))
BATCH_STEP_CAP     = int(os.getenv("AGENT_BATCH_STEP_CAP", "40"))
DEADLINE_SECONDS   = float(os.getenv("AGENT_DEADLINE_SECONDS", "600"))
# Independent batches can run concurrently to cut wall-clock (recon time is dominated by
# per-invoice model latency). Shared mutable state (consumed transactions) is lock-guarded
# in propose_match; invoices are disjoint per batch so they never contend.
CONCURRENCY        = int(os.getenv("AGENT_BATCH_CONCURRENCY", "4"))
FALLBACK_TO_LEGACY = os.getenv("AGENT_FALLBACK_LEGACY", "true").lower() == "true"
MAX_NUDGES         = 3


def _short_args(args: dict) -> str:
    parts = []
    for k, v in (args or {}).items():
        s = str(v)
        parts.append(f"{k}={s[:24]}" + ("…" if len(s) > 24 else ""))
    return ", ".join(parts)


def _job_cancelled(db, job_id: str) -> bool:
    try:
        row = (db.table("reconciliation_job").select("status")
               .eq("job_id", job_id).limit(1).execute())
        return bool(row.data) and row.data[0]["status"] == "cancelled"
    except Exception:
        return False


def run_agent(sme_id: str, mode: str = "auto") -> dict:
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    job_id = orchestrator._start_job(db, sme_id)
    try:
        db.table("reconciliation_job").update({"model_version": llm.AGENT_MODEL}) \
          .eq("job_id", job_id).execute()
    except Exception:
        pass

    # Deterministic exact-reference matches first (DuitNow/FPX recon key). These
    # commit through the same gate + writer and drop out of the batches' candidate
    # searches, so the agent only reasons over the unreferenced remainder.
    try:
        pre_written, pre_ids = orchestrator._reference_prematch(db, job_id, sme_id)
    except Exception:
        logger.exception("Reference pre-match failed; continuing with LLM only.")
        pre_written, pre_ids = 0, set()

    mem = AgentMemory(db, job_id)

    # Choose tool-calling mode (probe). A failure here means the model is
    # unreachable -> fall back to the legacy pipeline.
    try:
        llm_mode = llm.get_mode()
    except Exception as exc:
        logger.exception("Agent LLM init failed.")
        return _fail_or_fallback(db, job_id, sme_id, exc, did_progress=False)

    learned = load_learned(db, sme_id)

    # Split the unreferenced remainder into small batches the agent can actually hold in
    # working memory. Shared, mutable state lives in `shared` (referenced by every batch);
    # per-batch state (inv_map/txn_map/proof_map/auto_count) is created per worker so
    # concurrent batches don't clobber each other. `_all_txns` is pre-fetched ONCE here so
    # find_candidates never races to populate it.
    invoices = [inv for inv in orchestrator._fetch_invoices(db, sme_id)
                if inv.invoice_id not in pre_ids]
    batches = [invoices[i:i + BATCH_SIZE] for i in range(0, len(invoices), BATCH_SIZE)]
    shared = {"matched_ids": set(pre_ids), "consumed_txns": set(), "rates": {},
              "_all_txns": orchestrator._fetch_transactions(db, sme_id),
              "lock": threading.Lock()}
    workers = min(CONCURRENCY, max(1, len(batches)))
    mem.persist("agent_started",
                f"Agent loop started (mode={llm_mode}, model={llm.AGENT_MODEL}); "
                f"{pre_written} pre-matched, {len(invoices)} invoice(s) in {len(batches)} "
                f"batch(es), {workers} concurrent.", phase="plan")

    start = datetime.utcnow()

    def _worker(item):
        bi, batch = item
        try:
            bdb = create_client(SUPABASE_URL, SUPABASE_KEY)     # own client per thread
            bctx = {"inv_map": {inv.invoice_id: inv for inv in batch},
                    "txn_map": {}, "proof_map": {}, "auto_count": 0,
                    "matched_ids": shared["matched_ids"], "consumed_txns": shared["consumed_txns"],
                    "rates": shared["rates"], "_all_txns": shared["_all_txns"], "lock": shared["lock"]}
            return _run_batch(bdb, job_id, sme_id, bctx, batch, bi, len(batches),
                              llm_mode, learned, mode, start)
        except Exception:                                   # a batch must never kill the job
            logger.exception("Batch %s crashed.", bi)
            return "ok"

    statuses = []
    if batches:
        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                statuses = list(ex.map(_worker, enumerate(batches, 1)))
        else:
            statuses = [_worker(it) for it in enumerate(batches, 1)]
    if any(s == "cancelled" for s in statuses):
        return _finalise(db, job_id, sme_id, {"matched_ids": shared["matched_ids"]},
                         status="cancelled")

    # Governed verification + anomaly passes — run ONCE over the whole job with FULL
    # visibility (all invoices + all transactions), so downgrade checks see every match.
    vctx = {"matched_ids": shared["matched_ids"], "consumed_txns": shared["consumed_txns"],
            "rates": shared["rates"], "auto_count": 0,
            "inv_map": {i.invoice_id: i for i in invoices},
            "txn_map": {t.transaction_id: t for t in shared["_all_txns"]}}
    try:
        verifier.run_verification(db, job_id, sme_id, vctx, mem, apply=True)
    except Exception as exc:
        logger.exception("Verifier pass failed.")
        mem.persist("verify_error", f"Verification skipped: {exc}", phase="verify")
    try:
        anomaly.scan_anomalies(db, job_id, sme_id, vctx, mem, apply=True)
    except Exception as exc:
        logger.exception("Anomaly scan failed.")
        mem.persist("anomaly_error", f"Anomaly scan skipped: {exc}", phase="verify")

    return _finalise(db, job_id, sme_id, {"matched_ids": shared["matched_ids"]})


def _run_batch(db, job_id, sme_id, ctx, batch, batch_no, total, llm_mode, learned,
               mode, overall_start) -> str:
    """One focused sub-loop over a small batch of invoices. Bounded working memory:
    a batch goal + a candidate-retrieval tool, no whole-ledger dumps. Safe to run
    concurrently with other batches (shared consumed_txns is lock-guarded in
    propose_match). Returns 'ok' | 'cancelled' | 'deadline' — never raises for control flow."""
    ctx["inv_map"] = {inv.invoice_id: inv for inv in batch}
    tool_names = tools_mod.BATCH_TOOL_NAMES
    mem = AgentMemory(db, job_id)
    mem.add_system(prompts.build_system_prompt(
        llm_mode, learned.get("summary", ""),
        tools_mod.react_tool_descriptions(tool_names), batched=True))
    mem.add_user(prompts.build_batch_goal(batch, batch_no, total))
    mem.persist("batch_started",
                f"Batch {batch_no}/{total}: {len(batch)} invoice(s) to reconcile.", phase="plan")
    tools_param = tools_mod.openai_tools_param(tool_names) if llm_mode == "native" else None
    nudges = 0

    for step in range(BATCH_STEP_CAP):
        mem.step = step
        if (datetime.utcnow() - overall_start).total_seconds() > DEADLINE_SECONDS:
            mem.persist("loop_exhausted", "Wall-clock deadline reached; finishing.", phase="verify")
            return "deadline"
        if _job_cancelled(db, job_id):
            mem.persist("job_cancelled", "Run cancelled by user.", phase="verify")
            return "cancelled"

        try:
            out = llm.step(mem.messages, tools_param)
        except Exception as exc:
            logger.exception("LLM step failed (batch %s).", batch_no)
            mem.persist("llm_error", f"Model call failed: {exc}", phase="act")
            return "ok"                          # abandon this batch, continue the run

        mem.add(out.assistant_message)
        if out.text:
            mem.persist("agent_thought", out.text)

        if out.parse_error:
            nudges += 1
            if nudges > MAX_NUDGES:
                mem.persist("loop_exhausted", "Too many invalid responses; ending batch.", phase="verify")
                return "ok"
            mem.add_user("Your last message was not a single valid JSON object. "
                         "Respond with ONLY the JSON action.")
            continue

        if not out.tool_calls:
            nudges += 1
            if nudges > MAX_NUDGES:
                mem.persist("loop_exhausted", "Model stopped acting; ending batch.", phase="verify")
                return "ok"
            mem.add_user("Call a tool, or finish if every invoice in this batch is resolved.")
            continue
        nudges = 0

        for tc in out.tool_calls:
            if tc.name == "finish":
                mem.persist("batch_finished",
                            str(tc.args.get("summary", "batch resolved")),
                            {"finish": tc.args}, phase="advise")
                return "ok"
            mem.persist("tool_call", f"→ {tc.name}({_short_args(tc.args)})",
                        {"tool": tc.name, "args": tc.args})
            fn = tools_mod.REGISTRY.get(tc.name)
            if fn is None:
                result = {"error": f"unknown_tool '{tc.name}'"}
            else:
                try:
                    result = fn(db, job_id, sme_id, ctx, mem, mode, **tc.args)
                except Exception as exc:
                    logger.exception("Tool %s failed.", tc.name)
                    result = {"error": str(exc)}
                    mem.persist("tool_error", f"{tc.name} failed: {exc}", {"tool": tc.name})
            mem.add(llm.tool_result_message(tc, result))
    else:
        mem.persist("loop_exhausted",
                    f"Batch {batch_no} hit step cap ({BATCH_STEP_CAP}); moving on.", phase="verify")
    return "ok"


def _finalise(db, job_id: str, sme_id: str, ctx: dict, status: str = "completed") -> dict:
    """Sweep still-unmatched invoices and write the job to a terminal state."""
    try:
        matched_ids = ctx.get("matched_ids", set())
        remaining = orchestrator._fetch_invoices(db, sme_id)        # only still-pending rows
        unmatched = [inv for inv in remaining if inv.invoice_id not in matched_ids]
        for inv in unmatched:
            db.table("invoice").update({"status": "unmatched"}) \
              .eq("invoice_id", inv.invoice_id).execute()

        matched_count = len(matched_ids)
        if status == "cancelled":
            db.table("reconciliation_job").update({
                "status": "cancelled",
                "completed_at": datetime.utcnow().isoformat(),
                "matched_count": matched_count,
                "unmatched_count": len(unmatched),
            }).eq("job_id", job_id).execute()
        else:
            orchestrator._complete_job(db, job_id, matched_count, len(unmatched))

        return {"status": status, "job_id": job_id,
                "matched_count": matched_count, "unmatched_count": len(unmatched)}
    except Exception as exc:
        # Job must never be left stuck in 'processing' — force it terminal.
        logger.exception("Finalise failed; forcing job to failed.")
        try:
            db.table("reconciliation_job").update({
                "status": orchestrator.JobStatus.FAILED,
                "completed_at": datetime.utcnow().isoformat(),
            }).eq("job_id", job_id).execute()
        except Exception:
            pass
        return {"status": "failed", "job_id": job_id, "error": str(exc)}


def _fail_or_fallback(db, job_id: str, sme_id: str, exc: Exception, did_progress: bool) -> dict:
    """Model unreachable: optionally run the legacy pipeline; else mark failed."""
    if FALLBACK_TO_LEGACY and not did_progress:
        try:
            db.table("reconciliation_job").update({
                "status": "cancelled",
                "completed_at": datetime.utcnow().isoformat(),
            }).eq("job_id", job_id).execute()
            orchestrator._log(db, job_id, "agent_fallback",
                              f"Agent unavailable ({exc}); running legacy pipeline.")
        except Exception:
            pass
        logger.warning("Agent unavailable; falling back to legacy run_reconciliation.")
        return orchestrator.run_reconciliation(sme_id)

    db.table("reconciliation_job").update({
        "status": orchestrator.JobStatus.FAILED,
        "completed_at": datetime.utcnow().isoformat(),
    }).eq("job_id", job_id).execute()
    orchestrator._log(db, job_id, "job_failed", str(exc))
    return {"status": "failed", "job_id": job_id, "error": str(exc)}
