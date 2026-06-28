"""
main.py
=======
Entry point for the Global Treasury Agent backend.
Imports the existing tested app from server.py and adds
reconciliation endpoints on top — server.py is not modified.

Run with:
    uvicorn main:app --reload --port 8000
"""

import os
import sys
from fastapi import BackgroundTasks, Depends, HTTPException
from supabase import create_client
from dotenv import load_dotenv

from auth import get_current_sme_id

# The codebase prints emoji to stdout for debug logging. On a non-UTF-8 Windows
# console (cp1252) those prints raise UnicodeEncodeError mid-request and fail the
# job. Force UTF-8 stdout/stderr so logging never breaks the pipeline.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Import the existing tested app — all /api/upload routes stay intact
from server import app

from orchestrator import run_reconciliation

load_dotenv()

# Agentic reconciliation is the DEFAULT. /api/reconcile runs the tool-using agent
# loop (agent/runner.py); set USE_AGENT=false to force the legacy linear pipeline.
# Either way the DB contract is identical, so /api/job-status + the dashboard are
# unchanged. The agent also auto-falls back to the legacy pipeline if the model is
# unreachable at job start (AGENT_FALLBACK_LEGACY).
USE_AGENT = os.getenv("USE_AGENT", "true").lower() == "true"

if USE_AGENT:
    from agent.runner import run_agent
    _reconcile_task = run_agent
else:
    _reconcile_task = run_reconciliation

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_API_KEY"),
)


@app.post("/api/reconcile")
async def reconcile(
    background_tasks: BackgroundTasks,
    sme_id: str = Depends(get_current_sme_id),
):
    """
    Trigger reconciliation for the authenticated tenant.

    Frontend calls this immediately after /api/upload succeeds. sme_id is
    derived from the caller's JWT — never trusted from the URL.
    Returns 202 Accepted straight away — matching runs in the background.
    Poll /api/job-status to check when it's done.
    """
    background_tasks.add_task(_reconcile_task, sme_id)

    return {
        "status":  "accepted",
        "sme_id":  sme_id,
        "mode":    "agent" if USE_AGENT else "legacy",
        "message": "Reconciliation started. Poll /api/job-status for updates.",
    }


@app.get("/api/job-status")
async def job_status(sme_id: str = Depends(get_current_sme_id)):
    """
    Returns the most recent reconciliation job for the authenticated tenant.
    Frontend polls this after calling /api/reconcile.

    Possible status values: pending | processing | completed | failed
    """
    jobs = (
        supabase.table("reconciliation_job")
        .select("job_id, status, matched_count, unmatched_count, started_at, completed_at")
        .eq("sme_id", sme_id)
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    if not jobs.data:
        return {"status": "no_jobs_found"}

    return jobs.data[0]


@app.get("/health")
async def health():
    return {"status": "ok"}