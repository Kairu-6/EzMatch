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
from fastapi import BackgroundTasks, HTTPException
from supabase import create_client
from dotenv import load_dotenv

# Import the existing tested app — all /api/upload routes stay intact
from server import app

from orchestrator import run_reconciliation

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_API_KEY"),
)


@app.post("/api/reconcile/{sme_id}")
async def reconcile(sme_id: str, background_tasks: BackgroundTasks):
    """
    Trigger reconciliation for an SME after their statement has been uploaded.

    Frontend calls this immediately after /api/upload succeeds.
    Returns 202 Accepted straight away — matching runs in the background.
    Poll /api/job-status/{sme_id} to check when it's done.
    """
    # Confirm the sme_id actually exists before queuing the job
    sme = (
        supabase.table("sme")
        .select("sme_id")
        .eq("sme_id", sme_id)
        .single()
        .execute()
    )
    if not sme.data:
        raise HTTPException(status_code=404, detail=f"SME {sme_id} not found.")

    background_tasks.add_task(run_reconciliation, sme_id)

    return {
        "status":  "accepted",
        "sme_id":  sme_id,
        "message": "Reconciliation started. Poll /api/job-status for updates.",
    }


@app.get("/api/job-status/{sme_id}")
async def job_status(sme_id: str):
    """
    Returns the most recent reconciliation job for this SME.
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