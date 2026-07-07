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
MAX_STEPS          = int(os.getenv("AGENT_MAX_STEPS", "30"))
DEADLINE_SECONDS   = float(os.getenv("AGENT_DEADLINE_SECONDS", "300"))
FALLBACK_TO_LEGACY = os.getenv("AGENT_FALLBACK_LEGACY", "true").lower() == "true"
MAX_NUDGES         = 3


class _Finish(Exception):
    def __init__(self, args: dict):
        self.finish_args = args or {}


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
    # commit through the same gate + writer and drop out of the loop's list_*
    # fetches, so the agent only reasons over the unreferenced remainder.
    try:
        pre_written, pre_ids = orchestrator._reference_prematch(db, job_id, sme_id)
    except Exception:
        logger.exception("Reference pre-match failed; continuing with LLM only.")
        pre_written, pre_ids = 0, set()

    ctx = {"inv_map": {}, "txn_map": {}, "proof_map": {},
           "rates": {}, "matched_ids": set(pre_ids), "auto_count": pre_written}
    mem = AgentMemory(db, job_id)

    # Choose tool-calling mode (probe). A failure here means the model is
    # unreachable -> fall back to the legacy pipeline.
    try:
        llm_mode = llm.get_mode()
    except Exception as exc:
        logger.exception("Agent LLM init failed.")
        return _fail_or_fallback(db, job_id, sme_id, exc, did_progress=False)

    learned = load_learned(db, sme_id)
    mem.add_system(prompts.build_system_prompt(
        llm_mode, learned.get("summary", ""), tools_mod.react_tool_descriptions()))
    mem.add_user(prompts.GOAL_MESSAGE)
    mem.persist("agent_started",
                f"Agent loop started (mode={llm_mode}, model={llm.AGENT_MODEL}).",
                phase="plan")

    tools_param = tools_mod.openai_tools_param() if llm_mode == "native" else None
    start = datetime.utcnow()
    nudges = 0

    try:
        for step in range(MAX_STEPS):
            mem.step = step
            if (datetime.utcnow() - start).total_seconds() > DEADLINE_SECONDS:
                mem.persist("loop_exhausted", "Wall-clock deadline reached; finishing.",
                            phase="verify")
                break
            if _job_cancelled(db, job_id):
                mem.persist("job_cancelled", "Run cancelled by user.", phase="verify")
                return _finalise(db, job_id, sme_id, ctx, status="cancelled")

            try:
                out = llm.step(mem.messages, tools_param)
            except Exception as exc:
                logger.exception("LLM step failed.")
                if step == 0:
                    return _fail_or_fallback(db, job_id, sme_id, exc,
                                             did_progress=bool(ctx["matched_ids"]))
                mem.persist("llm_error", f"Model call failed: {exc}", phase="act")
                break

            mem.add(out.assistant_message)
            if out.text:
                mem.persist("agent_thought", out.text)

            if out.parse_error:
                nudges += 1
                if nudges > MAX_NUDGES:
                    mem.persist("loop_exhausted", "Too many invalid responses; finishing.",
                                phase="verify")
                    break
                mem.add_user("Your last message was not a single valid JSON object. "
                             "Respond with ONLY the JSON action.")
                continue

            if not out.tool_calls:
                nudges += 1
                if nudges > MAX_NUDGES:
                    mem.persist("loop_exhausted", "Model stopped acting; finishing.",
                                phase="verify")
                    break
                mem.add_user("Call a tool, or finish if you're done.")
                continue
            nudges = 0

            for tc in out.tool_calls:
                if tc.name == "finish":
                    raise _Finish(tc.args)
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
                        mem.persist("tool_error", f"{tc.name} failed: {exc}",
                                    {"tool": tc.name})
                mem.add(llm.tool_result_message(tc, result))
        else:
            mem.persist("loop_exhausted", f"Reached step cap ({MAX_STEPS}); finishing.",
                        phase="verify")
    except _Finish as f:
        mem.persist("agent_finished", str(f.finish_args.get("summary", "Done.")),
                    {"finish": f.finish_args}, phase="advise")

    # Governed verification pass — runs even if the model skipped its VERIFY phase.
    # Must never fail the job; a verifier error is logged, not raised.
    try:
        verifier.run_verification(db, job_id, sme_id, ctx, mem, apply=True)
    except Exception as exc:
        logger.exception("Verifier pass failed.")
        mem.persist("verify_error", f"Verification skipped: {exc}", phase="verify")

    # Anomaly/fraud scan — runs after verification, can escalate high-severity
    # signals. Also non-fatal: a detector error is logged, never raised.
    try:
        anomaly.scan_anomalies(db, job_id, sme_id, ctx, mem, apply=True)
    except Exception as exc:
        logger.exception("Anomaly scan failed.")
        mem.persist("anomaly_error", f"Anomaly scan skipped: {exc}", phase="verify")

    return _finalise(db, job_id, sme_id, ctx)


def _finalise(db, job_id: str, sme_id: str, ctx: dict, status: str = "completed") -> dict:
    """Sweep still-unmatched invoices and write the job to a terminal state."""
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
