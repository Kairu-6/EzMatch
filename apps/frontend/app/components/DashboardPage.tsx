"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  ArrowRight,
  Play,
  Database,
  Sparkles,
  Banknote,
  Receipt,
  ScrollText,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { supabase } from "../lib/supabaseClient";
import { useAuth } from "../lib/AuthContext";
import { PageHeader } from "./ui/PageHeader";
import { Panel, PanelHeader } from "./ui/Panel";
import { Button } from "./ui/Button";
import { StatusPill } from "./ui/StatusPill";
import { RingProgress } from "./ui/RingProgress";
import { EmptyState } from "./ui/EmptyState";
import { Skeleton, SkeletonRows } from "./ui/Skeleton";
import { ActivityDrawer, type LogLine } from "./ui/ActivityDrawer";
import { Table, TableScroll, Th, Td, Tr } from "./ui/Table";
import { SegmentedControl } from "./ui/SegmentedControl";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

type Match = {
  id: string;
  client: string;
  billed: { currency: string; amount: number };
  received: { currency: string; amount: number };
  rate: string;
  exact: boolean;
};

type SourceRow = {
  date: string;
  description: string;
  amount: number;
  credit: boolean;
};

type TxRow = SourceRow & { creditAmount: number; accountId: string | null };

type Account = {
  account_id: string;
  bank_name: string;
  account_number: string;
  currency_code: string;
  is_primary: boolean;
};

const myr = (n: number) =>
  new Intl.NumberFormat("en-MY", {
    style: "currency",
    currency: "MYR",
    maximumFractionDigits: 0,
  }).format(n);

// Map a reconciliation_log event_type to an ActivityDrawer line level so the
// agent's reasoning trace reads with the right emphasis.
const levelFor = (eventType: string): LogLine["level"] => {
  const e = (eventType ?? "").toLowerCase();
  if (e.includes("fail") || e.includes("error")) return "error";
  if (
    e.includes("escalat") ||
    e.includes("reject") ||
    e.includes("unmatched") ||
    e.includes("anomaly") ||
    e.includes("cancel") ||
    e.includes("exhausted")
  )
    return "warning";
  if (e.includes("commit") || e.includes("completed") || e.includes("finished"))
    return "success";
  if (e === "agent_thought") return "muted";
  return "info";
};

export function DashboardPage() {
  const router = useRouter();
  const { authHeaders } = useAuth();
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [hasRun, setHasRun] = useState(false);

  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<string>("all");
  const [allTx, setAllTx] = useState<TxRow[]>([]);
  const [stats, setStats] = useState({ txCountAll: 0, invoiceCount: 0, proofCount: 0 });
  const [statsLoading, setStatsLoading] = useState(true);
  const [jobStats, setJobStats] = useState<{ matched: number; unmatched: number } | null>(
    null,
  );
  const [matchFunds, setMatchFunds] = useState<
    { accountId: string | null; txAmount: number; converted: number }[]
  >([]);
  const [reconLoading, setReconLoading] = useState(true);

  const log = (text: string, level: LogLine["level"] = "muted") =>
    setLogs((prev) => [...prev, { text, level }]);

  // Guards against rendering the *previous* job's trace before this run's job
  // row appears. Set just before we POST /api/reconcile.
  const runStartRef = useRef<number>(0);

  // Replace the activity log with the real agent reasoning trace persisted in
  // reconciliation_log for this job (RLS-scoped to the tenant).
  const renderTrace = useCallback(async (jobId: string) => {
    const { data } = await supabase
      .from("reconciliation_log")
      .select("event_type, message, created_at")
      .eq("job_id", jobId)
      .order("created_at", { ascending: true });
    if (!data || data.length === 0) return;
    setLogs(
      data.map((r: any) => ({
        text: r.message ?? r.event_type,
        level: levelFor(r.event_type),
      })),
    );
  }, []);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    const [{ data }, { count: invoiceCount }, { count: proofCount }, { data: accs }] =
      await Promise.all([
        supabase.from("bank_transaction").select("*, bank_statement(account_id)"),
        supabase
          .from("invoice")
          .select("invoice_id", { count: "exact", head: true })
          .in("status", ["pending", "unmatched"]),
        supabase
          .from("payment_proof")
          .select("proof_id", { count: "exact", head: true }),
        supabase
          .from("bank_account")
          .select("account_id,bank_name,account_number,currency_code,is_primary")
          .order("is_primary", { ascending: false }),
      ]);

    if (accs) setAccounts(accs as Account[]);

    const tx: TxRow[] = (data ?? []).map((r: any) => {
      const st = Array.isArray(r.bank_statement)
        ? r.bank_statement[0]
        : r.bank_statement;
      return {
        date: r.transaction_date ?? r.value_date ?? "—",
        description:
          r.description_normalised ?? r.description ?? "Bank transaction",
        amount: Math.abs(r.credit_amount ?? r.debit_amount ?? 0),
        credit: r.credit_amount != null,
        creditAmount: r.credit_amount ?? 0,
        accountId: st?.account_id ?? null,
      };
    });
    setAllTx(tx);
    setStats({
      txCountAll: tx.length,
      invoiceCount: invoiceCount ?? 0,
      proofCount: proofCount ?? 0,
    });
    setStatsLoading(false);
  }, []);

  const filteredTx = useMemo(
    () =>
      selectedAccount === "all"
        ? allTx
        : allTx.filter((t) => t.accountId === selectedAccount),
    [allTx, selectedAccount],
  );

  const reconciled = useMemo(() => {
    if (selectedAccount === "all")
      return matchFunds.reduce((a, m) => a + (m.converted || 0), 0);
    return matchFunds
      .filter((m) => m.accountId === selectedAccount)
      .reduce((a, m) => a + (m.txAmount || 0), 0);
  }, [matchFunds, selectedAccount]);

  const sourceRows = useMemo(() => filteredTx.slice(0, 8), [filteredTx]);
  const txCount = filteredTx.length;
  const sourceLoading = statsLoading;

  const activeCurrency =
    selectedAccount === "all"
      ? "MYR"
      : accounts.find((a) => a.account_id === selectedAccount)?.currency_code ??
        "MYR";
  const fmt = (n: number) =>
    new Intl.NumberFormat("en-MY", {
      style: "currency",
      currency: activeCurrency,
      maximumFractionDigits: 0,
    }).format(n);

  const accountToggle = [
    { value: "all", label: "All accounts" },
    ...accounts.map((a) => ({
      value: a.account_id,
      label: `${a.bank_name} ··${(a.account_number ?? "").slice(-4)}`,
    })),
  ];

  const loadReconciliationState = useCallback(async () => {
    setReconLoading(true);
    const [{ data: matchData }, { count: unmatchedCount }] = await Promise.all([
      supabase
        .from("reconciliation_match")
        .select(
          `match_id, match_status, invoice_amount, invoice_currency,
           transaction_amount, tx_currency, converted_amount,
           invoice ( invoice_number, counterparty_name ),
           bank_transaction ( bank_statement ( account_id ) )`,
        )
        .order("matched_at", { ascending: false }),
      supabase
        .from("invoice")
        .select("invoice_id", { count: "exact", head: true })
        .eq("status", "unmatched"),
    ]);

    if (matchData && matchData.length > 0) {
      setMatches(
        matchData.map((m: any) => {
          const inv = Array.isArray(m.invoice) ? m.invoice[0] : m.invoice;
          return {
            id: inv?.invoice_number ?? "—",
            client: inv?.counterparty_name ?? "Unknown counterparty",
            billed: { currency: m.invoice_currency, amount: m.invoice_amount },
            received: { currency: m.tx_currency, amount: m.transaction_amount },
            rate:
              m.converted_amount && m.invoice_amount
                ? (m.converted_amount / m.invoice_amount).toFixed(4)
                : "1.0000",
            exact: m.match_status === "auto",
          };
        }),
      );
      setMatchFunds(
        matchData.map((m: any) => {
          const tx = Array.isArray(m.bank_transaction)
            ? m.bank_transaction[0]
            : m.bank_transaction;
          const st = Array.isArray(tx?.bank_statement)
            ? tx.bank_statement[0]
            : tx?.bank_statement;
          return {
            accountId: st?.account_id ?? null,
            txAmount: m.transaction_amount ?? 0,
            converted: m.converted_amount ?? 0,
          };
        }),
      );
      setHasRun(true);
      setJobStats({ matched: matchData.length, unmatched: unmatchedCount ?? 0 });
    } else {
      setMatches([]);
      setMatchFunds([]);
      setJobStats(null);
    }
    setReconLoading(false);
  }, []);

  useEffect(() => {
    loadStats();
    loadReconciliationState();
  }, [loadStats, loadReconciliationState]);

  const handleReconcile = async () => {
    setIsRunning(true);
    setHasRun(true);
    setMatches([]);
    setJobStats(null);
    // 3s buffer so a job started moments before the click isn't mistaken for ours.
    runStartRef.current = Date.now() - 3000;
    setLogs([{ text: "Connecting to reconciliation service…", level: "info" }]);

    try {
      const res = await fetch(`${API_BASE}/api/reconcile`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Service rejected the request.");
      log("Reconciliation job queued.", "info");

      const poll = setInterval(async () => {
        try {
          const sr = await fetch(`${API_BASE}/api/job-status`, {
            headers: authHeaders(),
          });
          if (!sr.ok) return;
          const job = await sr.json();
          if (job.status === "no_jobs_found" || !job.job_id) return;

          // Don't render a stale previous job before ours is visible.
          const jobStart = job.started_at
            ? new Date(job.started_at).getTime()
            : 0;
          if (jobStart < runStartRef.current) return;

          // Stream the real agent reasoning trace into the activity drawer.
          await renderTrace(job.job_id);

          if (job.status === "completed") {
            clearInterval(poll);
            await loadReconciliationState();
            await loadStats();
            setIsRunning(false);
          } else if (job.status === "failed" || job.status === "cancelled") {
            clearInterval(poll);
            setIsRunning(false);
          }
        } catch {
          /* transient poll error — keep trying */
        }
      }, 2000);
    } catch {
      log(
        "Couldn't reach the reconciliation service. Is the backend running on port 8000?",
        "error",
      );
      setIsRunning(false);
    }
  };

  const accuracy =
    jobStats && jobStats.matched + jobStats.unmatched > 0
      ? (jobStats.matched / (jobStats.matched + jobStats.unmatched)) * 100
      : null;

  return (
    <>
      <PageHeader
        title="Reconciliation"
        description="Match incoming bank transactions to your invoices across currencies."
      />

      {accounts.length > 0 && (
        <div className="mb-5">
          <SegmentedControl
            aria-label="Account scope"
            items={accountToggle}
            value={selectedAccount}
            onChange={setSelectedAccount}
          />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-8">
        <Panel className="lg:col-span-2 p-6">
          <p className="text-sm font-medium text-ink-muted">Funds reconciled</p>
          {statsLoading || reconLoading ? (
            <Skeleton className="h-9 w-48 mt-2" />
          ) : (
            <p className="text-3xl font-semibold text-ink tnum mt-1">
              {fmt(reconciled)}
            </p>
          )}
          <div className="grid grid-cols-3 gap-4 mt-6 pt-5 border-t border-border">
            <Stat
              icon={<Database className="w-4 h-4" />}
              label="Transactions"
              value={statsLoading ? null : String(txCount)}
            />
            <Stat
              icon={<Sparkles className="w-4 h-4" />}
              label="Matched"
              value={jobStats ? String(jobStats.matched) : "—"}
            />
            <Stat
              icon={<ScrollText className="w-4 h-4" />}
              label="Unmatched"
              value={jobStats ? String(jobStats.unmatched) : "—"}
            />
          </div>
        </Panel>

        <Panel className="p-6 flex flex-col items-center justify-center text-center">
          <p className="text-sm font-medium text-ink-muted mb-3 self-start">
            Match accuracy
          </p>
          {accuracy === null ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 py-2">
              <RingProgress value={0} label="—" sublabel="No run yet" />
              <p className="text-sm text-ink-subtle">
                Run reconciliation to measure accuracy.
              </p>
            </div>
          ) : (
            <RingProgress
              value={accuracy}
              label={`${accuracy.toFixed(1)}%`}
              sublabel="matched"
            />
          )}
        </Panel>
      </div>

      {/* Documents — readiness + actions (uploads entry + run reconciliation) */}
      <Panel className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 mb-8">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink-muted">Documents</p>
          {statsLoading ? (
            <Skeleton className="h-5 w-64 mt-1.5" />
          ) : (
            <p className="text-base text-ink mt-0.5 tnum">
              {stats.txCountAll} transactions · {stats.invoiceCount} invoices ·{" "}
              {stats.proofCount} proofs
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2.5 shrink-0">
          <Button variant="secondary" onClick={() => router.push("/uploads")}>
            Go to uploads
            <ArrowRight className="w-4 h-4" />
          </Button>
          <Button
            onClick={handleReconcile}
            loading={isRunning}
            icon={!isRunning ? <Play className="w-4 h-4" /> : undefined}
          >
            {isRunning ? "Running…" : "Run reconciliation"}
          </Button>
        </div>
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Panel className="overflow-hidden">
          <PanelHeader
            title="Source feed — bank account"
            icon={<Banknote className="w-4 h-4" />}
          />
          <TableScroll>
            <Table>
              <thead>
                <Tr>
                  <Th>Value date</Th>
                  <Th>Description</Th>
                  <Th align="right">Amount</Th>
                </Tr>
              </thead>
              {sourceLoading ? (
                <SkeletonRows rows={4} cols={3} />
              ) : sourceRows.length === 0 ? (
                <tbody>
                  <Tr>
                    <Td colSpan={3}>
                      <EmptyState
                        icon={<Banknote className="w-5 h-5" />}
                        title="No transactions yet"
                        description="Upload a bank statement to populate the source feed."
                      />
                    </Td>
                  </Tr>
                </tbody>
              ) : (
                <tbody>
                  {sourceRows.map((r, i) => (
                    <Tr key={i} hover>
                      <Td mono>{r.date}</Td>
                      <Td>{r.description}</Td>
                      <Td
                        align="right"
                        className={`font-medium tnum ${
                          r.credit ? "text-success-fg" : "text-ink-muted"
                        }`}
                      >
                        {r.credit ? "+" : "−"}
                        {fmt(r.amount)}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              )}
            </Table>
          </TableScroll>
        </Panel>

        <Panel className="overflow-hidden">
          <PanelHeader
            title="Reconciled matches"
            icon={<Sparkles className="w-4 h-4" />}
            action={
              hasRun ? (
                <StatusPill tone={isRunning ? "warning" : "success"}>
                  {isRunning ? "Running" : "Complete"}
                </StatusPill>
              ) : (
                <StatusPill tone="neutral" icon={null}>
                  Idle
                </StatusPill>
              )
            }
          />
          <TableScroll>
            <Table>
              <thead>
                <Tr>
                  <Th>Invoice</Th>
                  <Th align="right">Billed</Th>
                  <Th align="right">Received</Th>
                  <Th align="right">FX rate</Th>
                  <Th align="right">Status</Th>
                </Tr>
              </thead>
              {matches.length === 0 ? (
                <tbody>
                  <Tr>
                    <Td colSpan={5}>
                      <EmptyState
                        icon={<Sparkles className="w-5 h-5" />}
                        title={isRunning ? "Matching in progress" : "No matches yet"}
                        description={
                          isRunning
                            ? "Reconciling transactions against your invoices…"
                            : "Run reconciliation to match transactions to invoices."
                        }
                      />
                    </Td>
                  </Tr>
                </tbody>
              ) : (
                <tbody>
                  {matches.map((m, i) => (
                    <Tr key={i} hover>
                      <Td>
                        <div className="font-medium text-ink">{m.id}</div>
                        <div className="text-sm text-ink-muted">{m.client}</div>
                      </Td>
                      <Td align="right" mono>
                        {m.billed.currency} {m.billed.amount.toFixed(2)}
                      </Td>
                      <Td align="right" mono className="text-accent-text">
                        {m.received.currency} {m.received.amount.toFixed(2)}
                      </Td>
                      <Td align="right" mono>
                        {m.rate}
                      </Td>
                      <Td align="right">
                        <StatusPill tone={m.exact ? "success" : "warning"}>
                          {m.exact ? "Exact" : "Partial"}
                        </StatusPill>
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              )}
            </Table>
          </TableScroll>
        </Panel>
      </div>

      <ActivityDrawer
        lines={logs}
        running={isRunning}
        title="Reconciliation activity"
      />
    </>
  );
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-ink-subtle mb-1">
        {icon}
        <span className="text-xs font-medium">{label}</span>
      </div>
      {value === null ? (
        <Skeleton className="h-6 w-12" />
      ) : (
        <p className="text-lg font-semibold text-ink tnum">{value}</p>
      )}
    </div>
  );
}
