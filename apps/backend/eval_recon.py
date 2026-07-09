"""
eval_recon.py — score a real reconcile run against the seeded ground truth
==========================================================================
The seed (`seed_data.py` → `test_files/expected_reconciliation.json`) records, per
pre-seeded invoice, the CORRECT outcome: which transaction it should match and whether
that match should auto-commit, route to a human, or stay unmatched. This script runs a
real reconciliation for the demo tenant (the same engine the app uses — agent or legacy,
per USE_AGENT), then compares what the engine actually did against that baseline:

  • headline accuracy / error rate (disposition + correct pairing per invoice),
  • auto-commit precision / recall (how trustworthy the auto-commits are),
  • a per-tier breakdown (so the ~80–90% is explainable, not a black box),
  • estimated time saved vs a fully-manual baseline.

Accuracy is EXPECTED to be < 100% — the D/E tiers are deliberately ambiguous. A ~100%
result almost always means the hard cases stopped biting (regenerate the seed).

Run (backend venv, after seed_demo.py + seed_files.py):
  cd apps/backend && PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe eval_recon.py
  ./venv/Scripts/python.exe eval_recon.py --score-only   # score latest job, don't re-run
  ./venv/Scripts/python.exe eval_recon.py --selftest     # scoring-math self-check only
"""
import json
import os
import sys
from datetime import datetime

TEST_FILES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "test_files"))
MANIFEST = os.path.join(TEST_FILES, "expected_reconciliation.json")


# ── pure scoring (unit-tested) ───────────────────────────────────────────────────
def score(expectations: list[dict], actual: dict[str, dict], time_model: dict,
          job_seconds: float = 0.0) -> dict:
    """actual: invoice_id -> {"match_status": ..., "transaction_id": ...} for match rows
    written by the run (absent → the engine wrote no match for that invoice)."""
    tp = fp = fn = 0                       # auto-commit confusion matrix
    n_correct = 0
    predicted_auto = 0
    per_tier = {}
    per_matcher = {}                       # reference / rules / llm  — llm = the "AI" number
    rows = []
    for e in expectations:
        row = actual.get(e["invoice_id"])
        status = row["match_status"] if row else None
        got_txn = row["transaction_id"] if row else None
        is_auto = status == "auto"
        is_review = status == "pending_review"
        exp = e["expected_status"]
        exp_txn = e["expected_transaction_id"]

        if exp == "auto":
            correct = is_auto and got_txn == exp_txn
        elif exp == "pending_review":
            correct = is_review and (exp_txn is None or got_txn == exp_txn)
        elif exp == "unmatched":
            correct = row is None
        else:
            correct = False

        should_auto = exp == "auto"
        got_correct_auto = is_auto and got_txn == exp_txn
        if is_auto:
            predicted_auto += 1
            if should_auto and got_correct_auto:
                tp += 1
            else:
                fp += 1
        if should_auto and not got_correct_auto:
            fn += 1

        n_correct += int(correct)
        t = per_tier.setdefault(e["tier"], {"n": 0, "correct": 0})
        t["n"] += 1
        t["correct"] += int(correct)
        m = per_matcher.setdefault(e.get("matcher", "llm"), {"n": 0, "correct": 0})
        m["n"] += 1
        m["correct"] += int(correct)
        rows.append({"invoice_number": e["invoice_number"], "tier": e["tier"],
                     "matcher": e.get("matcher", "llm"),
                     "expected": exp, "actual": status or "none",
                     "correct": correct, "note": e.get("note", "")})

    total = len(expectations)
    accuracy = n_correct / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    manual = time_model["manual_min_per_invoice"]
    review = time_model["review_min_per_flag"]
    human_touch = total - predicted_auto          # everything not auto-committed needs a human
    saved_min = total * manual - human_touch * review - job_seconds / 60.0

    return {
        "total": total, "correct": n_correct, "accuracy": accuracy,
        "error_rate": 1 - accuracy,
        "auto_committed": predicted_auto, "tp": tp, "fp": fp, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1,
        "per_tier": {k: {"n": v["n"], "correct": v["correct"],
                         "accuracy": v["correct"] / v["n"] if v["n"] else 0.0}
                     for k, v in sorted(per_tier.items())},
        "per_matcher": {k: {"n": v["n"], "correct": v["correct"],
                            "accuracy": v["correct"] / v["n"] if v["n"] else 0.0}
                        for k, v in sorted(per_matcher.items())},
        "ai_accuracy": (per_matcher.get("llm", {}).get("correct", 0) /
                        per_matcher["llm"]["n"]) if per_matcher.get("llm", {}).get("n") else None,
        "time": {"manual_baseline_min": total * manual, "human_touch_invoices": human_touch,
                 "job_seconds": round(job_seconds, 1),
                 "saved_min": round(saved_min, 1), "saved_hours": round(saved_min / 60.0, 2)},
        "rows": rows,
    }


# ── run + fetch ──────────────────────────────────────────────────────────────────
def _job_seconds(job: dict) -> float:
    def _p(ts):
        if not ts:
            return None
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    a, b = _p(job.get("started_at")), _p(job.get("completed_at"))
    return (b - a).total_seconds() if a and b else 0.0


def _fetch_actual(db, job_id: str) -> dict:
    rows = db.table("reconciliation_match").select(
        "invoice_id, transaction_id, match_status").eq("job_id", job_id).execute().data or []
    out = {}
    for r in rows:
        out.setdefault(r["invoice_id"], r)   # first row per invoice
    return out


def main() -> None:
    if "--selftest" in sys.argv:
        _selftest()
        return

    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    sme_id = manifest["sme_id"]
    expectations = manifest["expectations"]
    time_model = manifest["time_model"]

    from dotenv import load_dotenv
    from supabase import create_client
    load_dotenv()
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_API_KEY"])

    if "--score-only" in sys.argv:
        jobs = db.table("reconciliation_job").select("*").eq("sme_id", sme_id) \
            .eq("status", "completed").order("completed_at", desc=True).limit(1).execute().data
        if not jobs:
            sys.exit("No completed job to score — run without --score-only first.")
        job = jobs[0]
    else:
        use_agent = os.getenv("USE_AGENT", "true").lower() == "true"
        if use_agent:
            from agent.runner import run_agent as run
        else:
            from orchestrator import run_reconciliation as run
        print(f"Running reconciliation ({'agent' if use_agent else 'legacy'}) for {sme_id} …")
        result = run(sme_id)
        job = db.table("reconciliation_job").select("*") \
            .eq("job_id", result["job_id"]).execute().data[0]

    actual = _fetch_actual(db, job["job_id"])
    report = score(expectations, actual, time_model, _job_seconds(job))
    _print(report, job)
    # The AI matcher hitting ~100% means the hard cases stopped biting — signal it.
    ai = report["ai_accuracy"]
    if ai is not None and ai >= 0.995:
        print("\nWARNING: LLM-matcher accuracy ~100% — the B/C/D ambiguity likely regressed; "
              "check the seed.")
        sys.exit(2)


def _print(r: dict, job: dict) -> None:
    print(f"\n== Reconciliation scored vs ground truth ==  job {job['job_id'][:8]} ({job['status']})")
    print(f"  invoices scored : {r['total']}")
    print(f"  overall accuracy: {r['accuracy']*100:5.1f}%   (error rate {r['error_rate']*100:.1f}%)")
    if r["ai_accuracy"] is not None:
        n_llm = r["per_matcher"]["llm"]["n"]
        print(f"  AI matcher (LLM): {r['ai_accuracy']*100:5.1f}%  over {n_llm} semantic invoice(s) "
              f"— the real matcher number")
    print(f"  auto-commits    : {r['auto_committed']}   precision {r['precision']*100:.1f}%  "
          f"recall {r['recall']*100:.1f}%  F1 {r['f1']*100:.1f}%")
    print(f"    TP={r['tp']}  FP={r['fp']}  FN={r['fn']}")
    print("  by matcher      :")
    for m, v in r["per_matcher"].items():
        print(f"     {m:10}: {v['correct']:>2}/{v['n']:<2} = {v['accuracy']*100:5.1f}%")
    print("  by tier         :")
    for tier, v in r["per_tier"].items():
        print(f"     {tier}: {v['correct']:>2}/{v['n']:<2} = {v['accuracy']*100:5.1f}%")
    t = r["time"]
    print(f"  time saved      : {t['saved_hours']} h  "
          f"(manual baseline {t['manual_baseline_min']:.0f} min, "
          f"{t['human_touch_invoices']} invoices still need a human, "
          f"job {t['job_seconds']}s)")
    wrong = [x for x in r["rows"] if not x["correct"]]
    if wrong:
        print(f"  misses ({len(wrong)}):")
        for x in wrong:
            print(f"     {x['invoice_number']:10} tier {x['tier']}  expected {x['expected']:14} "
                  f"got {x['actual']:14} — {x['note']}")


# ── scoring-math self-check ────────────────────────────────────────────────────────
def _selftest() -> None:
    exps = [
        {"invoice_id": "i1", "invoice_number": "A", "tier": "A", "expected_status": "auto",
         "expected_transaction_id": "t1", "note": ""},
        {"invoice_id": "i2", "invoice_number": "B", "tier": "B", "expected_status": "auto",
         "expected_transaction_id": "t2", "note": ""},
        {"invoice_id": "i3", "invoice_number": "D", "tier": "D", "expected_status": "auto",
         "expected_transaction_id": "t3", "note": ""},
        {"invoice_id": "i4", "invoice_number": "E1", "tier": "E", "expected_status": "unmatched",
         "expected_transaction_id": None, "note": ""},
        {"invoice_id": "i5", "invoice_number": "E2", "tier": "E", "expected_status": "pending_review",
         "expected_transaction_id": "t5", "note": ""},
    ]
    actual = {
        "i1": {"match_status": "auto", "transaction_id": "t1"},          # correct auto  → TP
        "i2": {"match_status": "auto", "transaction_id": "tX"},          # auto wrong txn → FP + FN
        "i3": {"match_status": "pending_review", "transaction_id": "t3"},  # missed auto  → FN
        # i4: no row → correctly unmatched
        "i5": {"match_status": "pending_review", "transaction_id": "t5"},  # correctly routed
    }
    tm = {"manual_min_per_invoice": 8.0, "review_min_per_flag": 3.0}
    r = score(exps, actual, tm, job_seconds=60.0)
    assert r["total"] == 5
    assert r["correct"] == 3, r["correct"]              # i1, i4, i5
    assert r["tp"] == 1 and r["fp"] == 1, (r["tp"], r["fp"])
    assert r["fn"] == 2, r["fn"]                        # i2 (wrong txn) + i3 (not auto)
    assert abs(r["accuracy"] - 0.6) < 1e-9
    assert r["auto_committed"] == 2
    # human_touch = 5 - 2 = 3 → saved = 5*8 - 3*3 - 1 = 30 min
    assert abs(r["time"]["saved_min"] - 30.0) < 1e-9, r["time"]["saved_min"]
    assert r["per_tier"]["A"]["accuracy"] == 1.0 and r["per_tier"]["B"]["accuracy"] == 0.0
    print("eval_recon scoring self-check passed.")


if __name__ == "__main__":
    main()
