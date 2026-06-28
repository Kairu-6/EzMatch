"""
agent/gate.py
=============
The deterministic governance gate. This — NOT the model — decides whether a
proposed match auto-commits, gets routed to a human, or is rejected outright.

The model's `confidence` is one input; the gate also weighs the FX-converted
amount variance and a per-job auto-commit cap. Keeping this logic in plain,
auditable Python (not the LLM) is what makes an autonomous finance agent
trustworthy: the model can only *propose*, the gate *governs*.
"""
import os
from enum import Enum


class Verdict(str, Enum):
    AUTO_COMMIT    = "auto_commit"      # confident + amounts line up  -> write as 'auto'
    ROUTE_TO_HUMAN = "route_to_human"   # plausible but uncertain      -> write as 'pending_review'
    REJECT         = "reject"           # amounts don't line up at all -> no write


# Tunable thresholds (env-overridable). Defaults chosen for the demo dataset.
CONFIDENCE_THRESHOLD   = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))
# Auto-commit only when the bank amount is within this band of the converted
# invoice amount. Cross-border fees shave a few % off, so the negative side is
# more generous than the positive side (a transaction *exceeding* the invoice is
# more suspicious than one falling slightly short).
AUTO_MAX_POS_VARIANCE  = float(os.getenv("GATE_AUTO_MAX_POS_VARIANCE_PCT", "2.0"))
AUTO_MAX_NEG_VARIANCE  = float(os.getenv("GATE_AUTO_MAX_NEG_VARIANCE_PCT", "8.0"))
# Beyond this absolute variance the amounts simply don't match — reject.
REJECT_VARIANCE_PCT    = float(os.getenv("GATE_REJECT_VARIANCE_PCT", "25.0"))
# Cap on the converted value the agent may auto-commit without a human.
AUTO_MAX_VALUE         = float(os.getenv("GATE_AUTO_MAX_VALUE", "1000000"))
# Safety cap on how many matches one run may auto-commit.
MAX_AUTO_PER_JOB       = int(os.getenv("GATE_MAX_AUTO_PER_JOB", "100"))


def decide(
    confidence: float,
    variance_pct: float,
    converted_amount: float,
    auto_count: int,
) -> tuple[Verdict, list[str]]:
    """
    Return (verdict, reasons). `reasons` is a human-readable, audit-friendly
    explanation of why the gate ruled the way it did — persisted to the trace.
    """
    reasons: list[str] = []

    # 1. Amounts wildly off -> reject regardless of model confidence.
    if abs(variance_pct) > REJECT_VARIANCE_PCT:
        reasons.append(
            f"variance {variance_pct:+.1f}% exceeds reject limit ±{REJECT_VARIANCE_PCT:.0f}%"
        )
        return Verdict.REJECT, reasons

    # 2. Evaluate the auto-commit bar (all must hold).
    if confidence < CONFIDENCE_THRESHOLD:
        reasons.append(f"confidence {confidence:.2f} below auto threshold {CONFIDENCE_THRESHOLD:.2f}")
    if not (-AUTO_MAX_NEG_VARIANCE <= variance_pct <= AUTO_MAX_POS_VARIANCE):
        reasons.append(
            f"variance {variance_pct:+.1f}% outside auto band "
            f"[-{AUTO_MAX_NEG_VARIANCE:.0f}%, +{AUTO_MAX_POS_VARIANCE:.0f}%]"
        )
    if converted_amount > AUTO_MAX_VALUE:
        reasons.append(f"value {converted_amount:.0f} above auto cap {AUTO_MAX_VALUE:.0f}")
    if auto_count >= MAX_AUTO_PER_JOB:
        reasons.append(f"auto-commit cap {MAX_AUTO_PER_JOB} reached this run")

    if reasons:
        return Verdict.ROUTE_TO_HUMAN, reasons

    reasons.append(
        f"confidence {confidence:.2f} ≥ {CONFIDENCE_THRESHOLD:.2f} and "
        f"variance {variance_pct:+.1f}% within band"
    )
    return Verdict.AUTO_COMMIT, reasons
