"use client";

import React, { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  FileSpreadsheet,
  ReceiptText,
  ShieldCheck,
  FileCheck2,
  Landmark,
  Plus,
  Trash2,
  RefreshCw,
  BadgeCheck,
  Plug,
  ChevronDown,
} from "lucide-react";
import Link from "next/link";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { Dropzone, type UploadStatus } from "../components/ui/Dropzone";
import { SegmentedControl } from "../components/ui/SegmentedControl";
import { StatusPill } from "../components/ui/StatusPill";
import { EmptyState } from "../components/ui/EmptyState";
import { Skeleton, SkeletonRows } from "../components/ui/Skeleton";
import { Table, TableScroll, Th, Td, Tr } from "../components/ui/Table";
import { Button } from "../components/ui/Button";
import { Field } from "../components/ui/Field";
import { useToast } from "../components/ui/Toast";
import { supabase } from "../lib/supabaseClient";
import { useAuth } from "../lib/AuthContext";
import { cn } from "../components/ui/cn";

const IMPORT_SOURCES = [
  { key: "myinvois", label: "LHDN MyInvois" },
  { key: "sql", label: "SQL Account" },
  { key: "autocount", label: "AutoCount" },
] as const;

// Backend base URL. Set NEXT_PUBLIC_API_URL (e.g. to a tunnelled https URL)
// when the app isn't served from the same machine as the backend.
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

type Tab = "statements" | "invoices" | "proofs";

type Account = {
  account_id: string;
  bank_name: string;
  account_number: string;
  account_holder: string;
  currency_code: string;
  is_primary: boolean;
};

const acctLabel = (a: Account) =>
  `${a.bank_name} ··${(a.account_number ?? "").slice(-4)}`;

// ── Statements ──────────────────────────────────────────────────────
type LedgerRow = {
  id: string;
  date: string;
  description: string;
  reference: string | null; // DuitNow/FPX recon key, when present
  currency: string;
  settled: number;
  matched: boolean;
  accountId: string | null;
};

const myr = (n: number) =>
  new Intl.NumberFormat("en-MY", {
    style: "currency",
    currency: "MYR",
    minimumFractionDigits: 2,
  }).format(n);

type Proof = {
  id: string;
  reference: string;
  amount: number | null;
  currency: string;
  status: string; // parse_status
  rail: string | null; // "FPX" | "DuitNow" from parsed_data
};

const proofTone = (s: string): "success" | "warning" | "danger" =>
  s === "completed" ? "success" : s === "failed" ? "danger" : "warning";
const proofLabel = (s: string) =>
  s === "completed" ? "Verified" : s === "failed" ? "Failed" : "Processing";

function UploadsInner() {
  const { toast } = useToast();
  const { authHeaders, smeId } = useAuth();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const validTab = (v: string | null): v is Tab =>
    v === "statements" || v === "invoices" || v === "proofs";
  const [tab, setTab] = useState<Tab>(validTab(tabParam) ? tabParam : "statements");

  // Deep-link support: the navbar Upload menu links to /uploads?tab=…; keep the
  // active tab in sync when that param changes (soft nav keeps us mounted).
  useEffect(() => {
    if (validTab(tabParam)) setTab(tabParam);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabParam]);

  // Accounts state (shared by the statements tab)
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [selectedAccount, setSelectedAccount] = useState<string>("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [adding, setAdding] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [busyPrimary, setBusyPrimary] = useState<string | null>(null);
  const [form, setForm] = useState({
    bank_name: "",
    account_holder: "",
    account_number: "",
    currency_code: "MYR",
    is_primary: false,
  });

  // Statements state
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [ledgerLoading, setLedgerLoading] = useState(true);
  const [stmtStatus, setStmtStatus] = useState<UploadStatus>("idle");
  const [feedSyncing, setFeedSyncing] = useState(false);

  // Invoices state
  const [invoices, setInvoices] = useState<any[]>([]);
  const [invoicesLoading, setInvoicesLoading] = useState(true);
  const [invStatus, setInvStatus] = useState<UploadStatus>("idle");

  // Proofs state (read from payment_proof, like statements/invoices)
  const [proofs, setProofs] = useState<Proof[]>([]);
  const [proofsLoading, setProofsLoading] = useState(true);
  const [proofStatus, setProofStatus] = useState<UploadStatus>("idle");

  // ── Accounts: fetch + add ──────────────────────────────────────────
  const fetchAccounts = useCallback(async () => {
    setAccountsLoading(true);
    const { data } = await supabase
      .from("bank_account")
      .select(
        "account_id,bank_name,account_number,account_holder,currency_code,is_primary",
      )
      .order("is_primary", { ascending: false });
    if (data) {
      setAccounts(data as Account[]);
      setSelectedAccount(
        (prev) =>
          prev ||
          (data.find((a: any) => a.is_primary)?.account_id ??
            data[0]?.account_id ??
            ""),
      );
    }
    setAccountsLoading(false);
  }, []);

  const addAccount = async () => {
    if (!form.bank_name.trim() || !form.account_number.trim()) {
      toast({
        tone: "danger",
        title: "Missing details",
        description: "Bank name and account number are required.",
      });
      return;
    }
    if (!smeId) {
      toast({
        tone: "danger",
        title: "Workspace not ready",
        description: "Still loading your workspace — try again in a moment.",
      });
      return;
    }
    setAdding(true);
    try {
      if (form.is_primary) {
        await supabase
          .from("bank_account")
          .update({ is_primary: false })
          .eq("sme_id", smeId);
      }
      const { error } = await supabase.from("bank_account").insert({
        account_id: crypto.randomUUID(),
        sme_id: smeId,
        bank_name: form.bank_name.trim(),
        account_holder: form.account_holder.trim() || form.bank_name.trim(),
        account_number: form.account_number.trim(),
        currency_code: (form.currency_code.trim() || "MYR").toUpperCase(),
        is_primary: form.is_primary,
        is_active: true,
      });
      if (error) throw error;
      toast({
        tone: "success",
        title: "Account added",
        description: `${form.bank_name.trim()} is ready for statement uploads.`,
      });
      setForm({
        bank_name: "",
        account_holder: "",
        account_number: "",
        currency_code: "MYR",
        is_primary: false,
      });
      setShowAddForm(false);
      fetchAccounts();
    } catch (e: any) {
      toast({
        tone: "danger",
        title: "Couldn't add account",
        description: e?.message ?? "Insert failed.",
      });
    } finally {
      setAdding(false);
    }
  };

  const accountLabel = (id: string | null) => {
    const a = accounts.find((x) => x.account_id === id);
    return a ? acctLabel(a) : "—";
  };

  // Make an existing account the primary (single primary per SME).
  const setPrimary = async (accountId: string) => {
    setBusyPrimary(accountId);
    try {
      await supabase
        .from("bank_account")
        .update({ is_primary: false })
        .eq("sme_id", smeId);
      const { error } = await supabase
        .from("bank_account")
        .update({ is_primary: true })
        .eq("account_id", accountId);
      if (error) throw error;
      toast({
        tone: "success",
        title: "Primary updated",
        description: "This account is now the default for uploads.",
      });
      fetchAccounts();
    } catch (e: any) {
      toast({
        tone: "danger",
        title: "Couldn't update primary",
        description: e?.message ?? "Update failed.",
      });
    } finally {
      setBusyPrimary(null);
    }
  };

  // Transactions belonging to an account (via its statements), from the ledger.
  const txCountFor = (id: string) =>
    ledger.filter((r) => r.accountId === id).length;

  // Delete an account + everything under it: its statements, their transactions,
  // any reconciliation matches on those transactions, and revert affected
  // invoices to "unmatched" so they aren't stranded.
  const deleteAccount = async (accountId: string) => {
    setDeleting(true);
    try {
      const { data: stmts } = await supabase
        .from("bank_statement")
        .select("statement_id")
        .eq("account_id", accountId);
      const statementIds = (stmts ?? []).map((s: any) => s.statement_id);

      let txIds: string[] = [];
      if (statementIds.length) {
        const { data: txs } = await supabase
          .from("bank_transaction")
          .select("transaction_id")
          .in("statement_id", statementIds);
        txIds = (txs ?? []).map((t: any) => t.transaction_id);
      }

      if (txIds.length) {
        // Invoices matched to these transactions → revert to unmatched.
        const { data: ms } = await supabase
          .from("reconciliation_match")
          .select("invoice_id")
          .in("transaction_id", txIds);
        const invIds = Array.from(
          new Set((ms ?? []).map((m: any) => m.invoice_id).filter(Boolean)),
        );
        await supabase
          .from("reconciliation_match")
          .delete()
          .in("transaction_id", txIds);
        if (invIds.length) {
          await supabase
            .from("invoice")
            .update({ status: "unmatched" })
            .in("invoice_id", invIds);
        }
        await supabase
          .from("bank_transaction")
          .delete()
          .in("statement_id", statementIds);
      }

      if (statementIds.length) {
        await supabase
          .from("bank_statement")
          .delete()
          .in("statement_id", statementIds);
      }

      const { error } = await supabase
        .from("bank_account")
        .delete()
        .eq("account_id", accountId);
      if (error) throw error;

      // Keep exactly one primary: if none remains, promote the oldest account.
      const { data: remaining } = await supabase
        .from("bank_account")
        .select("account_id, is_primary")
        .eq("sme_id", smeId)
        .order("created_at", { ascending: true });
      if (
        remaining &&
        remaining.length > 0 &&
        !remaining.some((r: any) => r.is_primary)
      ) {
        await supabase
          .from("bank_account")
          .update({ is_primary: true })
          .eq("account_id", remaining[0].account_id);
      }

      toast({
        tone: "success",
        title: "Account deleted",
        description: `Removed the account and ${txIds.length} transaction(s).`,
      });
      setConfirmingDelete(null);
      if (selectedAccount === accountId) setSelectedAccount("");
      fetchAccounts();
      fetchLedger();
    } catch (e: any) {
      toast({
        tone: "danger",
        title: "Couldn't delete account",
        description: e?.message ?? "Delete failed.",
      });
    } finally {
      setDeleting(false);
    }
  };

  // ── Statements: fetch + upload ─────────────────────────────────────
  const fetchLedger = useCallback(async () => {
    setLedgerLoading(true);
    const { data } = await supabase
      .from("bank_transaction")
      .select("*, bank_statement(account_id)")
      .order("transaction_date", { ascending: false });
    if (data) {
      setLedger(
        data.map((r: any) => {
          const st = Array.isArray(r.bank_statement)
            ? r.bank_statement[0]
            : r.bank_statement;
          return {
            id: r.transaction_id
              ? String(r.transaction_id).substring(0, 8).toUpperCase()
              : "—",
            date: r.transaction_date ?? r.value_date ?? "—",
            description:
              r.description_normalised ?? r.description ?? "Bank transaction",
            reference: r.reference_number ?? null,
            currency: r.currency_code ?? "MYR",
            settled: Math.abs(r.credit_amount ?? r.debit_amount ?? 0),
            matched: !!r.is_matched,
            accountId: st?.account_id ?? null,
          };
        }),
      );
    }
    setLedgerLoading(false);
  }, []);

  // ── Invoices: fetch + upload (verbatim from /invoices) ─────────────
  const fetchPending = useCallback(async () => {
    setInvoicesLoading(true);
    try {
      const { data, error } = await supabase
        .from("invoice")
        .select("*")
        .in("status", ["pending", "unmatched"]);
      if (error) throw error;
      if (data) setInvoices(data);
    } catch {
      /* surfaced via empty state */
    } finally {
      setInvoicesLoading(false);
    }
  }, []);

  // ── Proofs: fetch from payment_proof ───────────────────────────────
  const fetchProofs = useCallback(async () => {
    setProofsLoading(true);
    const { data } = await supabase
      .from("payment_proof")
      .select("*")
      .order("uploaded_at", { ascending: false });
    if (data) {
      setProofs(
        data.map((p: any) => ({
          id: p.proof_id,
          reference: p.parsed_reference ?? "—",
          amount: p.parsed_amount ?? null,
          currency: p.parsed_currency ?? "",
          status: p.parse_status ?? "pending",
          rail: p.parsed_data?.rail ?? null,
        })),
      );
    }
    setProofsLoading(false);
  }, []);

  useEffect(() => {
    fetchAccounts();
    fetchLedger();
    fetchPending();
    fetchProofs();
  }, [fetchAccounts, fetchLedger, fetchPending, fetchProofs]);

  const uploadStatement = async (files: FileList) => {
    const file = files[0];
    if (!file) return;
    setStmtStatus("uploading");
    const body = new FormData();
    body.append("file", file);
    if (selectedAccount) body.append("account_id", selectedAccount);
    try {
      const res = await fetch(`${API}/api/upload/statement`, {
        method: "POST",
        headers: authHeaders(),
        body,
      });
      if (!res.ok) throw new Error();
      setStmtStatus("done");
      toast({
        tone: "success",
        title: "Statement uploaded",
        description: "Parsing transactions and updating the ledger…",
      });
      setTimeout(() => {
        fetchLedger();
        setStmtStatus("idle");
      }, 2500);
    } catch {
      setStmtStatus("error");
      toast({
        tone: "danger",
        title: "Upload failed",
        description: "Couldn't reach the backend on port 8000.",
      });
      setTimeout(() => setStmtStatus("idle"), 4000);
    }
  };

  // ── Connected apps: which invoice connectors are configured + usable ──────
  const [connectors, setConnectors] = useState({
    myinvois: false,
    autocount: false,
    sql: false,
  });
  const [syncing, setSyncing] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const importRef = useRef<HTMLDivElement>(null);

  const fetchConnectors = useCallback(async () => {
    // RLS scopes both reads to the logged-in tenant. A connector is "available"
    // only if its saved config will actually run (mock, or the needed secret set).
    const [mi, acct] = await Promise.all([
      supabase.from("myinvois_credential").select("*").maybeSingle(),
      supabase.from("accounting_credential").select("*"),
    ]);
    const m = mi.data;
    const rows: any[] = acct.data ?? [];
    const ac = rows.find((r) => r.provider === "autocount");
    const sq = rows.find((r) => r.provider === "sql");
    setConnectors({
      myinvois: !!m && (m.environment === "mock" || (!!m.client_id && !!m.client_secret)),
      // AutoCount + SQL are mock-only (their real API docs need a paid SME subscription).
      autocount: !!ac && ac.environment === "mock",
      sql: !!sq && sq.environment === "mock",
    });
  }, []);

  useEffect(() => {
    fetchConnectors();
  }, [fetchConnectors]);

  useEffect(() => {
    if (!importOpen) return;
    const onDown = (e: MouseEvent) => {
      if (importRef.current && !importRef.current.contains(e.target as Node)) setImportOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [importOpen]);

  const runImport = async (key: "myinvois" | "autocount" | "sql") => {
    setImportOpen(false);
    setSyncing(true);
    try {
      const url =
        key === "myinvois"
          ? `${API}/api/myinvois/sync`
          : `${API}/api/accounting/sync?provider=${key}`;
      const res = await fetch(url, { method: "POST", headers: authHeaders() });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail || "");
      toast({
        tone: "success",
        title: `${data.imported ?? 0} invoice${data.imported === 1 ? "" : "s"} synced`,
        description: data.imported
          ? "Added to pending invoices for reconciliation."
          : "No new invoices found.",
      });
      fetchPending();
    } catch (e) {
      toast({
        tone: "danger",
        title: "Import failed",
        description: (e as Error)?.message || "Couldn't reach the connector. Check Settings.",
      });
    } finally {
      setSyncing(false);
    }
  };

  // ── Bank feed (Finverse): pull transactions for connected consents ──────────
  const syncFeed = async () => {
    setFeedSyncing(true);
    try {
      const res = await fetch(`${API}/api/bankfeed/sync`, { method: "POST", headers: authHeaders() });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail || "");
      toast({
        tone: "success",
        title: `${data.imported ?? 0} transaction${data.imported === 1 ? "" : "s"} synced`,
        description: data.imported ? "Ledger updated from your bank feed." : "No new transactions found.",
      });
      fetchAccounts();
      fetchLedger();
    } catch (e) {
      toast({
        tone: "danger",
        title: "Bank sync failed",
        description: (e as Error)?.message || "Connect a bank in Settings first.",
      });
    } finally {
      setFeedSyncing(false);
    }
  };

  // Toast the outcome of a Finverse Link redirect (?linked=1|0), once.
  const linkedHandled = useRef(false);
  useEffect(() => {
    if (linkedHandled.current) return;
    const linked = searchParams.get("linked");
    if (linked === "1") {
      linkedHandled.current = true;
      toast({ tone: "success", title: "Bank connected", description: "Use “Sync bank feed” to pull your transactions." });
      fetchAccounts();
    } else if (linked === "0") {
      linkedHandled.current = true;
      toast({ tone: "danger", title: "Bank connection failed", description: "Couldn't complete authorization. Please try again." });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const uploadInvoice = async (files: FileList) => {
    const file = files[0];
    if (!file) return;
    setInvStatus("uploading");
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch(`${API}/api/upload/invoice`, {
        method: "POST",
        headers: authHeaders(),
        body,
      });
      if (!res.ok) throw new Error();
      setInvStatus("done");
      toast({
        tone: "success",
        title: "Invoice extracted",
        description: "Added to pending receivables for reconciliation.",
      });
      setTimeout(() => {
        fetchPending();
        setInvStatus("idle");
      }, 1800);
    } catch {
      setInvStatus("error");
      toast({
        tone: "danger",
        title: "Upload failed",
        description: "Couldn't reach the backend on port 8000.",
      });
      setTimeout(() => setInvStatus("idle"), 4000);
    }
  };

  const uploadProof = async (files: FileList) => {
    const file = files[0];
    if (!file) return;
    setProofStatus("uploading");
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch(`${API}/api/upload/payment_proof`, {
        method: "POST",
        headers: authHeaders(),
        body,
      });
      if (!res.ok) throw new Error();
      setProofStatus("done");
      toast({
        tone: "success",
        title: "Proof verified",
        description: `${file.name} was parsed and accepted.`,
      });
      setTimeout(() => {
        fetchProofs();
        setProofStatus("idle");
      }, 2500);
    } catch {
      setProofStatus("error");
      toast({
        tone: "danger",
        title: "Upload failed",
        description: "Couldn't reach the backend on port 8000.",
      });
      setTimeout(() => setProofStatus("idle"), 4000);
    }
  };

  const tabs = [
    {
      value: "statements",
      label: "Bank statements",
      count: ledgerLoading ? undefined : ledger.length,
    },
    {
      value: "invoices",
      label: "Invoices",
      count: invoicesLoading ? undefined : invoices.length,
    },
    {
      value: "proofs",
      label: "Payment proofs",
      count: proofsLoading ? undefined : proofs.length,
    },
  ];

  return (
    <div className="max-w-4xl mx-auto">
      <PageHeader
        title="Uploads"
        description="Bring in bank statements, invoices, and payment proofs for reconciliation."
      />

      <div className="mb-6">
        <SegmentedControl
          aria-label="Upload type"
          items={tabs}
          value={tab}
          onChange={(v) => setTab(v as Tab)}
        />
      </div>

      {/* ── Statements ── */}
      {tab === "statements" && (
        <div role="tabpanel" id="seg-panel-statements" aria-labelledby="seg-tab-statements">
          {/* Accounts: pick the upload target + manage accounts */}
          <Panel className="p-4 mb-6">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-semibold text-ink flex items-center gap-2">
                <Landmark className="w-4 h-4 text-ink-subtle" /> Bank accounts
              </h3>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  loading={feedSyncing}
                  onClick={syncFeed}
                  icon={<RefreshCw className="w-4 h-4" />}
                >
                  Sync bank feed
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setShowAddForm((v) => !v)}
                  icon={showAddForm ? undefined : <Plus className="w-4 h-4" />}
                >
                  {showAddForm ? "Cancel" : "Add account"}
                </Button>
              </div>
            </div>
            <p className="text-sm text-ink-muted mb-3">
              Choose which account this statement belongs to — its transactions
              will be tagged to it.
            </p>

            {accountsLoading ? (
              <Skeleton className="h-10 w-full" />
            ) : accounts.length === 0 ? (
              <p className="text-sm text-ink-subtle">
                No accounts yet — add one to upload statements.
              </p>
            ) : (
              <div className="space-y-1.5">
                {accounts.map((a) => (
                  <div
                    key={a.account_id}
                    className={`rounded-md border transition-colors ${
                      selectedAccount === a.account_id
                        ? "border-accent bg-accent-subtle"
                        : "border-border"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3 px-3 py-2">
                      <label className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer">
                        <input
                          type="radio"
                          name="upload-account"
                          checked={selectedAccount === a.account_id}
                          onChange={() => setSelectedAccount(a.account_id)}
                        />
                        <span className="font-medium text-ink truncate">
                          {a.bank_name}
                        </span>
                        <span className="font-mono text-sm text-ink-muted">
                          ··{(a.account_number ?? "").slice(-4)}
                        </span>
                        <span className="text-sm text-ink-subtle">
                          {a.currency_code}
                        </span>
                      </label>
                      <div className="flex items-center gap-2 shrink-0">
                        {a.is_primary ? (
                          <StatusPill tone="info" icon={null}>
                            Primary
                          </StatusPill>
                        ) : (
                          <Button
                            size="sm"
                            variant="ghost"
                            loading={busyPrimary === a.account_id}
                            onClick={() => setPrimary(a.account_id)}
                          >
                            Make primary
                          </Button>
                        )}
                        <button
                          type="button"
                          onClick={() => setConfirmingDelete(a.account_id)}
                          aria-label={`Delete ${a.bank_name}`}
                          className="flex items-center justify-center w-8 h-8 rounded-md text-ink-subtle hover:bg-surface hover:text-danger-fg transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>

                    {confirmingDelete === a.account_id && (
                      <div className="px-3 py-3 border-t border-border bg-danger-subtle/40">
                        <p className="text-sm text-ink-muted mb-3">
                          Permanently delete <span className="font-medium text-ink">{a.bank_name}</span> and its{" "}
                          <span className="font-medium text-ink">
                            {txCountFor(a.account_id)} transaction(s)
                          </span>
                          ? Any invoices matched to those transactions return to
                          unmatched. This can&apos;t be undone.
                        </p>
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="danger"
                            loading={deleting}
                            onClick={() => deleteAccount(a.account_id)}
                          >
                            Delete account
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setConfirmingDelete(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {showAddForm && (
              <div className="mt-4 pt-4 border-t border-border grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field
                  label="Bank name"
                  value={form.bank_name}
                  onChange={(e) => setForm({ ...form, bank_name: e.target.value })}
                  placeholder="CIMB Bank"
                />
                <Field
                  label="Account holder"
                  value={form.account_holder}
                  onChange={(e) =>
                    setForm({ ...form, account_holder: e.target.value })
                  }
                  placeholder="WZB Group Sdn Bhd"
                />
                <Field
                  label="Account number"
                  value={form.account_number}
                  onChange={(e) =>
                    setForm({ ...form, account_number: e.target.value })
                  }
                  placeholder="8001234567"
                />
                <Field
                  label="Currency"
                  value={form.currency_code}
                  onChange={(e) =>
                    setForm({ ...form, currency_code: e.target.value })
                  }
                  placeholder="MYR"
                />
                <label className="flex items-center gap-2 text-sm text-ink-muted sm:col-span-2">
                  <input
                    type="checkbox"
                    checked={form.is_primary}
                    onChange={(e) =>
                      setForm({ ...form, is_primary: e.target.checked })
                    }
                  />
                  Set as primary account
                </label>
                <div className="sm:col-span-2">
                  <Button
                    size="sm"
                    loading={adding}
                    onClick={addAccount}
                    icon={<Plus className="w-4 h-4" />}
                  >
                    Add account
                  </Button>
                </div>
              </div>
            )}
          </Panel>

          <div className="mb-6">
            <Dropzone
              accept=".csv,.xlsx"
              onFiles={uploadStatement}
              status={stmtStatus}
              title="Upload a bank statement"
              hint="CSV or XLSX, exported from your bank"
              message={stmtStatus === "done" ? "Statement received" : undefined}
            />
          </div>

          <Panel className="overflow-hidden">
            <PanelHeader
              title="Transaction ledger"
              icon={<FileSpreadsheet className="w-4 h-4" />}
            />
            <TableScroll>
              <Table>
                <thead>
                  <Tr>
                    <Th>Value date</Th>
                    <Th>Account</Th>
                    <Th>Description</Th>
                    <Th align="right">Settled</Th>
                    <Th align="right">Status</Th>
                  </Tr>
                </thead>
                {ledgerLoading ? (
                  <SkeletonRows rows={5} cols={5} />
                ) : ledger.length === 0 ? (
                  <tbody>
                    <Tr>
                      <Td colSpan={5}>
                        <EmptyState
                          icon={<FileSpreadsheet className="w-5 h-5" />}
                          title="No transactions yet"
                          description="Upload a bank statement above to start building your ledger."
                        />
                      </Td>
                    </Tr>
                  </tbody>
                ) : (
                  <tbody>
                    {ledger.map((r, i) => (
                      <Tr key={`${r.id}-${i}`} hover>
                        <Td mono>{r.date}</Td>
                        <Td className="text-ink-muted">
                          {accountLabel(r.accountId)}
                        </Td>
                        <Td>
                          {r.description}
                          {r.reference && (
                            <span className="block text-xs text-ink-subtle font-mono">
                              Ref {r.reference}
                            </span>
                          )}
                        </Td>
                        <Td align="right" className="font-medium">
                          {r.currency} {r.settled.toFixed(2)}
                        </Td>
                        <Td align="right">
                          <StatusPill tone={r.matched ? "success" : "warning"}>
                            {r.matched ? "Reconciled" : "Pending"}
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
      )}

      {/* ── Invoices ── */}
      {tab === "invoices" && (
        <div role="tabpanel" id="seg-panel-invoices" aria-labelledby="seg-tab-invoices">
          <div className="mb-6 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm text-ink-muted">
                Import invoices from a connected app — or upload a file below.
              </p>
              <div className="relative" ref={importRef}>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setImportOpen((v) => !v)}
                  loading={syncing}
                  icon={<Plug className="w-4 h-4" />}
                  aria-haspopup="menu"
                  aria-expanded={importOpen}
                >
                  Import from connected apps
                  <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", importOpen && "rotate-180")} />
                </Button>
                {importOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 top-full mt-1.5 min-w-[240px] rounded-lg border border-border bg-surface shadow-md p-1 z-30"
                  >
                    {IMPORT_SOURCES.map(({ key, label }) => {
                      const available = connectors[key];
                      return (
                        <button
                          key={key}
                          role="menuitem"
                          disabled={!available}
                          onClick={() => runImport(key)}
                          className={cn(
                            "flex w-full items-center justify-between gap-3 px-3 h-9 rounded-md text-sm transition-colors outline-none",
                            available
                              ? "text-ink hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-accent cursor-pointer"
                              : "text-ink-subtle cursor-not-allowed",
                          )}
                        >
                          <span className="flex items-center gap-2">
                            <Plug className="w-4 h-4 shrink-0" />
                            {label}
                          </span>
                          {!available && <span className="text-xs">Not configured</span>}
                        </button>
                      );
                    })}
                    <Link
                      href="/settings"
                      onClick={() => setImportOpen(false)}
                      className="flex items-center gap-2 px-3 h-9 mt-1 border-t border-border rounded-md text-sm text-ink-muted hover:bg-surface-2 hover:text-ink transition-colors"
                    >
                      <RefreshCw className="w-3.5 h-3.5" /> Manage connectors in Settings
                    </Link>
                  </div>
                )}
              </div>
            </div>
            <Dropzone
              accept=".pdf,.jpg,.jpeg,.png"
              onFiles={uploadInvoice}
              status={invStatus}
              title="Upload an invoice"
              hint="PDF, JPG, or PNG"
              message={invStatus === "done" ? "Invoice extracted" : undefined}
            />
          </div>

          <Panel className="overflow-hidden">
            <PanelHeader
              title="Pending invoices"
              icon={<ReceiptText className="w-4 h-4" />}
              action={
                <span className="text-sm text-ink-muted tnum">
                  {invoicesLoading ? "" : `${invoices.length} pending`}
                </span>
              }
            />
            <TableScroll>
              <Table>
                <thead>
                  <Tr>
                    <Th>Invoice</Th>
                    <Th>Counterparty</Th>
                    <Th align="right">Amount</Th>
                    <Th align="right">Status</Th>
                  </Tr>
                </thead>
                {invoicesLoading ? (
                  <SkeletonRows rows={4} cols={4} />
                ) : invoices.length === 0 ? (
                  <tbody>
                    <Tr>
                      <Td colSpan={4}>
                        <EmptyState
                          icon={<ReceiptText className="w-5 h-5" />}
                          title="No pending invoices"
                          description="Upload an invoice above and it will appear here, ready to reconcile."
                        />
                      </Td>
                    </Tr>
                  </tbody>
                ) : (
                  <tbody>
                    {invoices.map((inv) => {
                      const failed = !!inv.error_message;
                      return (
                        <Tr key={inv.invoice_id} hover>
                          <Td
                            mono
                            className={
                              failed ? "text-ink-muted" : "text-accent-text font-medium"
                            }
                          >
                            <span className="inline-flex items-center gap-2">
                              <span title={failed ? inv.error_message : undefined}>
                                {inv.invoice_number ||
                                  (failed ? "Parse failed" : "Processing…")}
                              </span>
                              {inv.myinvois_uuid && (
                                <span title="Validated e-Invoice from LHDN MyInvois">
                                  <StatusPill tone="info" icon={BadgeCheck}>
                                    e-Invoice
                                  </StatusPill>
                                </span>
                              )}
                              {(inv.source === "autocount" || inv.source === "sql") && (
                                <span title={`Imported from ${inv.source === "autocount" ? "AutoCount" : "SQL Account"}`}>
                                  <StatusPill tone="info" icon={Plug}>
                                    {inv.source === "autocount" ? "AutoCount" : "SQL Account"}
                                  </StatusPill>
                                </span>
                              )}
                            </span>
                          </Td>
                          <Td>
                            {inv.counterparty_name ||
                              (failed ? "—" : "Unknown counterparty")}
                          </Td>
                          <Td align="right" className="font-medium">
                            {failed
                              ? "—"
                              : `${inv.invoice_currency ?? ""} ${inv.invoice_amount ?? ""}`}
                          </Td>
                          <Td align="right">
                            <StatusPill tone={failed ? "danger" : "warning"}>
                              {failed ? "Failed" : "Unmatched"}
                            </StatusPill>
                          </Td>
                        </Tr>
                      );
                    })}
                  </tbody>
                )}
              </Table>
            </TableScroll>
          </Panel>
        </div>
      )}

      {/* ── Proofs ── */}
      {tab === "proofs" && (
        <div role="tabpanel" id="seg-panel-proofs" aria-labelledby="seg-tab-proofs">
          <div className="mb-6">
            <Dropzone
              accept=".pdf,.jpg,.jpeg,.png"
              onFiles={uploadProof}
              status={proofStatus}
              title="Upload a payment proof"
              hint="PDF, JPG, or PNG"
              message={proofStatus === "done" ? "Proof verified" : undefined}
            />
          </div>

          <Panel className="overflow-hidden">
            <PanelHeader
              title="Payment proofs"
              icon={<ShieldCheck className="w-4 h-4" />}
              action={
                <span className="text-sm text-ink-muted tnum">
                  {proofsLoading ? "" : `${proofs.length} total`}
                </span>
              }
            />
            <TableScroll>
              <Table>
                <thead>
                  <Tr>
                    <Th>Reference</Th>
                    <Th align="right">Amount</Th>
                    <Th align="right">Status</Th>
                  </Tr>
                </thead>
                {proofsLoading ? (
                  <SkeletonRows rows={3} cols={3} />
                ) : proofs.length === 0 ? (
                  <tbody>
                    <Tr>
                      <Td colSpan={3}>
                        <EmptyState
                          icon={<ShieldCheck className="w-5 h-5" />}
                          title="No proofs yet"
                          description="Upload a payment proof above and it will appear here once parsed."
                        />
                      </Td>
                    </Tr>
                  </tbody>
                ) : (
                  <tbody>
                    {proofs.map((p) => (
                      <Tr key={p.id} hover>
                        <Td mono>
                          <span className="inline-flex items-center gap-2">
                            <FileCheck2 className="w-4 h-4 text-ink-subtle" />
                            {p.reference}
                            {p.rail && (
                              <span title={`${p.rail} payment rail`}>
                                <StatusPill tone="info" icon={Landmark}>
                                  {p.rail}
                                </StatusPill>
                              </span>
                            )}
                          </span>
                        </Td>
                        <Td align="right" className="font-medium">
                          {p.amount !== null
                            ? `${p.currency} ${p.amount.toFixed(2)}`
                            : "—"}
                        </Td>
                        <Td align="right">
                          <StatusPill tone={proofTone(p.status)}>
                            {proofLabel(p.status)}
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
      )}
    </div>
  );
}

export default function UploadsPage() {
  return (
    <Suspense fallback={null}>
      <UploadsInner />
    </Suspense>
  );
}
