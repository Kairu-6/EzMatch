"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Info, ListChecks } from "lucide-react";
import { supabase } from "../lib/supabaseClient";
import { sendToReview, rejectMatch } from "../lib/matchActions";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel } from "../components/ui/Panel";
import { Button } from "../components/ui/Button";
import { StatusPill } from "../components/ui/StatusPill";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonRows } from "../components/ui/Skeleton";
import { Table, TableScroll, Th, Td, Tr } from "../components/ui/Table";
import { SegmentedControl } from "../components/ui/SegmentedControl";
import { useToast } from "../components/ui/Toast";

// One row = a reconciliation_match that has left the review queue: accepted
// automatically (auto), confirmed by a human (manual), or rejected.
type MatchStatus = "auto" | "manual" | "rejected";
type MatchRow = {
  matchId: string;
  invoiceId: string;
  transactionId: string;
  jobId: string;
  invoiceNumber: string;
  counterparty: string;
  date: string;
  matchStatus: MatchStatus;
  invoiceAmount: number;
  invoiceCurrency: string;
  txAmount: number;
  txCurrency: string;
  convertedAmount: number;
  varianceAmount: number;
  variancePct: number;
};

type Filter = "all" | MatchStatus;

const fmtVariance = (amount: number, currency: string) => {
  const sign = amount > 0 ? "+" : amount < 0 ? "−" : "";
  return `${sign}${currency} ${Math.abs(amount).toFixed(2)}`;
};

function SourcePill({ status }: { status: MatchStatus }) {
  if (status === "auto") return <StatusPill tone="info">Automated</StatusPill>;
  if (status === "manual") return <StatusPill tone="success">Manual</StatusPill>;
  return <StatusPill tone="neutral">Rejected</StatusPill>;
}

export default function HistoryPage() {
  const { toast } = useToast();
  const [rows, setRows] = useState<MatchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");
  const [confirming, setConfirming] = useState<{ id: string; action: "review" | "reject" } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("reconciliation_match")
      .select(
        `match_id, invoice_id, transaction_id, job_id, match_status,
         invoice_amount, invoice_currency,
         transaction_amount, tx_currency,
         converted_amount, variance_amount, variance_pct, matched_at,
         invoice ( invoice_number, counterparty_name )`,
      )
      // pending_review lives on /audit; History is the ledger of resolved matches.
      .in("match_status", ["auto", "manual", "rejected"])
      .order("matched_at", { ascending: false });

    if (error) {
      toast({ tone: "danger", title: "Couldn't load history", description: error.message });
      setRows([]);
      setLoading(false);
      return;
    }

    setRows(
      (data ?? []).map((m: any) => {
        const inv = Array.isArray(m.invoice) ? m.invoice[0] : m.invoice;
        return {
          matchId: m.match_id,
          invoiceId: m.invoice_id ?? "",
          transactionId: m.transaction_id ?? "",
          jobId: m.job_id ?? "",
          invoiceNumber: inv?.invoice_number ?? "—",
          counterparty: inv?.counterparty_name ?? "Unknown counterparty",
          date: m.matched_at ? String(m.matched_at).slice(0, 10) : "—",
          matchStatus: (m.match_status ?? "auto") as MatchStatus,
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
    fetchRows();
  }, [fetchRows]);

  // Send to review reverts an accepted match to pending_review (drops it from
  // learned memory and re-queues it in /audit). Reject unlinks it and teaches the
  // engine to avoid the pairing. Both via the shared helpers.
  const act = async (row: MatchRow, action: "review" | "reject") => {
    setBusy(row.matchId);
    const { error } = action === "review" ? await sendToReview(row) : await rejectMatch(row);
    setBusy(null);
    setConfirming(null);

    if (error) {
      toast({
        tone: "danger",
        title: action === "review" ? "Couldn't send to review" : "Couldn't reject",
        description: error,
      });
      return;
    }

    if (action === "review") {
      // Now pending_review — no longer part of this ledger; it reappears in /audit.
      setRows((prev) => prev.filter((r) => r.matchId !== row.matchId));
      toast({
        tone: "success",
        title: `${row.invoiceNumber} sent to review`,
        description: "Moved back to the audit queue and removed from learned memory.",
      });
    } else {
      setRows((prev) =>
        prev.map((r) => (r.matchId === row.matchId ? { ...r, matchStatus: "rejected" } : r)),
      );
      toast({
        tone: "success",
        title: `${row.invoiceNumber} rejected`,
        description: "Unlinked, and the engine will learn to avoid this pairing.",
      });
    }
  };

  const counts = {
    all: rows.length,
    auto: rows.filter((r) => r.matchStatus === "auto").length,
    manual: rows.filter((r) => r.matchStatus === "manual").length,
    rejected: rows.filter((r) => r.matchStatus === "rejected").length,
  };
  const shown = filter === "all" ? rows : rows.filter((r) => r.matchStatus === filter);

  return (
    <div className="max-w-5xl mx-auto">
      <PageHeader
        title="Match history"
        description="Every match the engine committed automatically or a human confirmed. Correct any mistake here — nothing is permanent."
      />

      <div className="flex items-start gap-3 rounded-md border border-info/30 bg-info-subtle px-4 py-3 mb-6 text-info-fg">
        <Info className="w-4.5 h-4.5 shrink-0 mt-0.5" />
        <p className="text-base">
          Confirmed matches teach the engine. If one is wrong, <strong>Send to review</strong>{" "}
          to re-queue it in Audit (and drop it from what the system has learned), or{" "}
          <strong>Reject</strong> to unlink it and teach the engine to avoid the pairing.
        </p>
      </div>

      <div className="mb-4">
        <SegmentedControl
          aria-label="Filter matches by source"
          value={filter}
          onChange={(v) => setFilter(v as Filter)}
          items={[
            { value: "all", label: "All", count: counts.all },
            { value: "auto", label: "Automated", count: counts.auto },
            { value: "manual", label: "Manual", count: counts.manual },
            { value: "rejected", label: "Rejected", count: counts.rejected },
          ]}
        />
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
                  <Th align="center">Source</Th>
                  <Th align="right">Action</Th>
                </Tr>
              </thead>
              <SkeletonRows rows={3} cols={5} />
            </Table>
          </TableScroll>
        ) : shown.length === 0 ? (
          <EmptyState
            icon={<ListChecks className="w-5 h-5" />}
            title="Nothing here yet"
            description="Matches appear here once reconciliation runs or you resolve an exception in Audit."
          />
        ) : (
          <TableScroll>
            <Table>
              <thead>
                <Tr>
                  <Th>Reference</Th>
                  <Th>Detail</Th>
                  <Th align="right">Variance</Th>
                  <Th align="center">Source</Th>
                  <Th align="right">Action</Th>
                </Tr>
              </thead>
              <tbody>
                {shown.map((row) => (
                  <Tr key={row.matchId} hover>
                    <Td>
                      <div className="font-mono text-sm font-medium text-ink">
                        {row.invoiceNumber}
                      </div>
                      <div className="text-sm text-ink-muted">
                        {row.counterparty} · {row.date}
                      </div>
                    </Td>
                    <Td className="max-w-md">
                      <p className="text-base text-ink-muted leading-relaxed">
                        Billed {row.invoiceCurrency} {row.invoiceAmount.toFixed(2)}, received{" "}
                        {row.txCurrency} {row.txAmount.toFixed(2)} (≈{" "}
                        {row.convertedAmount.toFixed(2)} MYR).
                      </p>
                    </Td>
                    <Td align="right" className="font-medium text-ink tnum">
                      {fmtVariance(row.varianceAmount, row.txCurrency)}
                      <div className="text-xs text-ink-subtle font-normal">
                        {row.variancePct > 0 ? "+" : ""}
                        {row.variancePct.toFixed(2)}%
                      </div>
                    </Td>
                    <Td align="center">
                      <SourcePill status={row.matchStatus} />
                    </Td>
                    <Td align="right">
                      {row.matchStatus === "rejected" ? (
                        <span className="text-sm text-ink-subtle">—</span>
                      ) : confirming?.id === row.matchId ? (
                        <span className="inline-flex items-center gap-2">
                          <Button
                            size="sm"
                            loading={busy === row.matchId}
                            onClick={() => act(row, confirming.action)}
                          >
                            {confirming.action === "review" ? "Confirm review" : "Confirm reject"}
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setConfirming(null)}>
                            Cancel
                          </Button>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => setConfirming({ id: row.matchId, action: "review" })}
                          >
                            Send to review
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setConfirming({ id: row.matchId, action: "reject" })}
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
