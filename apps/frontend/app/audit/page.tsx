"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Info, CheckCircle2 } from "lucide-react";
import { supabase } from "../lib/supabaseClient";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel } from "../components/ui/Panel";
import { Button } from "../components/ui/Button";
import { StatusPill } from "../components/ui/StatusPill";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonRows } from "../components/ui/Skeleton";
import { Table, TableScroll, Th, Td, Tr } from "../components/ui/Table";
import { useToast } from "../components/ui/Toast";

// One exception = a reconciliation_match the engine left for manual review.
type Exception = {
  matchId: string;
  invoiceId: string;
  transactionId: string;
  invoiceNumber: string;
  counterparty: string;
  date: string;
  confidence: number;
  invoiceAmount: number;
  invoiceCurrency: string;
  txAmount: number;
  txCurrency: string;
  convertedAmount: number;
  varianceAmount: number;
  variancePct: number;
};

const fmtVariance = (amount: number, currency: string) => {
  const sign = amount > 0 ? "+" : amount < 0 ? "−" : "";
  return `${sign}${currency} ${Math.abs(amount).toFixed(2)}`;
};

// High when the engine was unsure or the amounts diverge materially.
const isHighRisk = (e: Exception) =>
  e.confidence < 0.5 || Math.abs(e.variancePct) > 5;

export default function AuditLogPage() {
  const { toast } = useToast();
  const [exceptions, setExceptions] = useState<Exception[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState<{ id: string; action: "resolve" | "reject" } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const fetchExceptions = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("reconciliation_match")
      .select(
        `match_id, invoice_id, transaction_id, match_status, match_confidence,
         invoice_amount, invoice_currency,
         transaction_amount, tx_currency,
         converted_amount, variance_amount, variance_pct, matched_at,
         invoice ( invoice_number, counterparty_name )`,
      )
      .eq("match_status", "pending_review")
      .order("matched_at", { ascending: false });

    if (error) {
      toast({
        tone: "danger",
        title: "Couldn't load exceptions",
        description: error.message,
      });
      setExceptions([]);
      setLoading(false);
      return;
    }

    setExceptions(
      (data ?? []).map((m: any) => {
        const inv = Array.isArray(m.invoice) ? m.invoice[0] : m.invoice;
        return {
          matchId: m.match_id,
          invoiceId: m.invoice_id ?? "",
          transactionId: m.transaction_id ?? "",
          invoiceNumber: inv?.invoice_number ?? "—",
          counterparty: inv?.counterparty_name ?? "Unknown counterparty",
          date: m.matched_at ? String(m.matched_at).slice(0, 10) : "—",
          confidence: m.match_confidence ?? 0,
          invoiceAmount: m.invoice_amount ?? 0,
          invoiceCurrency: m.invoice_currency ?? "",
          txAmount: m.transaction_amount ?? 0,
          txCurrency: m.tx_currency ?? "",
          convertedAmount: m.converted_amount ?? 0,
          varianceAmount: m.variance_amount ?? 0,
          variancePct: m.variance_pct ?? 0,
        };
      }),
    );
    setLoading(false);
  }, [toast]);

  useEffect(() => {
    fetchExceptions();
  }, [fetchExceptions]);

  // Resolve = accept the match (mark manually reviewed). Reject = the human
  // disagrees: mark the match rejected and unlink it so the invoice and the
  // bank transaction go back into the pool and can be matched again.
  const apply = async (e: Exception, action: "resolve" | "reject") => {
    setBusy(e.matchId);
    const status = action === "resolve" ? "manual" : "rejected";
    const { error } = await supabase
      .from("reconciliation_match")
      .update({ match_status: status })
      .eq("match_id", e.matchId);

    // Best-effort unlink on reject; the match is already rejected either way, so
    // a failed unlink shouldn't block clearing the queue — surface it, no rollback.
    if (!error && action === "reject") {
      if (e.invoiceId)
        await supabase.from("invoice").update({ status: "unmatched" }).eq("invoice_id", e.invoiceId);
      if (e.transactionId)
        await supabase.from("bank_transaction").update({ is_matched: false }).eq("transaction_id", e.transactionId);
    }

    setBusy(null);
    setConfirming(null);

    if (error) {
      toast({
        tone: "danger",
        title: action === "resolve" ? "Couldn't resolve" : "Couldn't reject",
        description: error.message,
      });
      return;
    }

    setExceptions((prev) => prev.filter((x) => x.matchId !== e.matchId));
    toast(
      action === "resolve"
        ? {
            tone: "success",
            title: `${e.invoiceNumber} resolved`,
            description: "Marked as manually reviewed and cleared from the queue.",
          }
        : {
            tone: "success",
            title: `${e.invoiceNumber} rejected`,
            description: "Match removed — the invoice and transaction are unmatched and eligible again.",
          },
    );
  };

  return (
    <div className="max-w-5xl mx-auto">
      <PageHeader
        title="Audit log"
        description="Matches the reconciliation engine flagged for manual review. Resolve each once you've confirmed it."
      />

      <div className="flex items-start gap-3 rounded-md border border-info/30 bg-info-subtle px-4 py-3 mb-6 text-info-fg">
        <Info className="w-4.5 h-4.5 shrink-0 mt-0.5" />
        <p className="text-base">
          These matches scored below the auto-clear confidence threshold, so the
          engine left them for a human decision. Review the amounts and variance,
          then <strong>Resolve</strong> to accept the match or <strong>Reject</strong>{" "}
          to unlink it — rejecting frees the invoice and transaction to be matched again.
        </p>
      </div>

      <Panel className="overflow-hidden">
        {loading ? (
          <TableScroll>
            <Table>
              <thead>
                <Tr>
                  <Th>Reference</Th>
                  <Th>Detail</Th>
                  <Th align="right">Variance</Th>
                  <Th align="center">Risk</Th>
                  <Th align="right">Action</Th>
                </Tr>
              </thead>
              <SkeletonRows rows={3} cols={5} />
            </Table>
          </TableScroll>
        ) : exceptions.length === 0 ? (
          <EmptyState
            icon={<CheckCircle2 className="w-5 h-5" />}
            title="All clear"
            description="No matches are awaiting review. New exceptions will appear here after reconciliation."
          />
        ) : (
          <TableScroll>
            <Table>
              <thead>
                <Tr>
                  <Th>Reference</Th>
                  <Th>Detail</Th>
                  <Th align="right">Variance</Th>
                  <Th align="center">Risk</Th>
                  <Th align="right">Action</Th>
                </Tr>
              </thead>
              <tbody>
                {exceptions.map((e) => (
                  <Tr key={e.matchId} hover>
                    <Td>
                      <div className="font-mono text-sm font-medium text-ink">
                        {e.invoiceNumber}
                      </div>
                      <div className="text-sm text-ink-muted">
                        {e.counterparty} · {e.date}
                      </div>
                    </Td>
                    <Td className="max-w-md">
                      <p className="text-base text-ink-muted leading-relaxed">
                        Confidence {(e.confidence * 100).toFixed(0)}% — below the
                        auto-clear threshold. Billed {e.invoiceCurrency}{" "}
                        {e.invoiceAmount.toFixed(2)}, received {e.txCurrency}{" "}
                        {e.txAmount.toFixed(2)} (≈ {e.convertedAmount.toFixed(2)}{" "}
                        MYR).
                      </p>
                    </Td>
                    <Td align="right" className="font-medium text-ink tnum">
                      {fmtVariance(e.varianceAmount, e.txCurrency)}
                      <div className="text-xs text-ink-subtle font-normal">
                        {e.variancePct > 0 ? "+" : ""}
                        {e.variancePct.toFixed(2)}%
                      </div>
                    </Td>
                    <Td align="center">
                      <StatusPill tone={isHighRisk(e) ? "danger" : "warning"}>
                        {isHighRisk(e) ? "High" : "Low"}
                      </StatusPill>
                    </Td>
                    <Td align="right">
                      {confirming?.id === e.matchId ? (
                        <span className="inline-flex items-center gap-2">
                          <Button
                            size="sm"
                            loading={busy === e.matchId}
                            onClick={() => apply(e, confirming.action)}
                          >
                            {confirming.action === "resolve"
                              ? "Confirm match"
                              : "Remove match"}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setConfirming(null)}
                          >
                            Cancel
                          </Button>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => setConfirming({ id: e.matchId, action: "resolve" })}
                          >
                            Resolve
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setConfirming({ id: e.matchId, action: "reject" })}
                          >
                            Reject
                          </Button>
                        </span>
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableScroll>
        )}
      </Panel>
    </div>
  );
}
