import { supabase } from "./supabaseClient";

// Everything the two review surfaces (/audit, /history) need to alter a match.
// A match links three tables (see orchestrator._write_match): the match row,
// bank_transaction.is_matched, and invoice.status — so altering one reverts them.
export type MatchRef = {
  matchId: string;
  invoiceId: string;
  transactionId: string;
  jobId: string;
  invoiceNumber: string;
  variancePct: number;
};

type Result = { error: string | null };

// Revert an accepted (auto/manual) match to the review queue. Because learned
// memory is derived live from match_status='manual' (agent/memory.py load_learned),
// this alone un-teaches a mis-confirmed match; it also re-surfaces it in /audit.
// Leaves the transaction linked (still a candidate, just under review) — mirrors
// verifier._downgrade.
export async function sendToReview(m: MatchRef): Promise<Result> {
  const { error } = await supabase
    .from("reconciliation_match")
    .update({ match_status: "pending_review" })
    .eq("match_id", m.matchId);
  if (error) return { error: error.message };
  if (m.invoiceId)
    await supabase.from("invoice").update({ status: "partial" }).eq("invoice_id", m.invoiceId);
  return { error: null };
}

// Reject + unlink a match, and TEACH the engine to avoid the pairing by writing a
// match_rejected log event — the negative signal load_learned._load_blocklist reads
// (it pulls invoice_number, transaction_id, variance_pct from metadata). The status
// flip is authoritative; the unlink and log write are best-effort so a hiccup can't
// wedge the queue.
export async function rejectMatch(m: MatchRef): Promise<Result> {
  const { error } = await supabase
    .from("reconciliation_match")
    .update({ match_status: "rejected" })
    .eq("match_id", m.matchId);
  if (error) return { error: error.message };

  if (m.invoiceId)
    await supabase.from("invoice").update({ status: "unmatched" }).eq("invoice_id", m.invoiceId);
  if (m.transactionId)
    await supabase.from("bank_transaction").update({ is_matched: false }).eq("transaction_id", m.transactionId);

  if (m.jobId)
    await supabase.from("reconciliation_log").insert({
      job_id: m.jobId,
      event_type: "match_rejected",
      message: `Human rejected ${m.invoiceNumber} → txn ${m.transactionId.slice(0, 8)}`,
      metadata: {
        invoice_number: m.invoiceNumber,
        transaction_id: m.transactionId,
        variance_pct: m.variancePct,
      },
    });

  return { error: null };
}
