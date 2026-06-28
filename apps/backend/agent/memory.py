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
from datetime import datetime

from supabase import Client

# Reuse the orchestrator's logger so agent + legacy paths write identical rows.
from orchestrator import _log as _orch_log

# Keep working memory from growing unbounded over a long loop. The durable copy
# of everything lives in reconciliation_log, so trimming the in-flight thread is
# safe. System + goal (first two messages) are always retained.
MAX_WORKING_CHARS = 24000


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


# ── long-term learned memory (Phase B) ────────────────────────────
def load_learned(db: Client, sme_id: str) -> dict:
    """
    Phase B: derive heuristics/few-shots from past human corrections
    (reconciliation_match.match_status IN ('manual','rejected')). Returns an
    empty memory in Phase A so the loop runs identically.
    """
    return {"summary": "", "exemplars": [], "blocklist": []}
