"use client";

import React, { useState, useEffect, useCallback } from "react";
import { BadgeCheck, Plug, Landmark } from "lucide-react";
import { supabase } from "../lib/supabaseClient";
import { useAuth } from "../lib/AuthContext";

// Backend base URL (same convention as the uploads page).
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
import { PageHeader } from "../components/ui/PageHeader";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { Field } from "../components/ui/Field";
import { Button } from "../components/ui/Button";
import { StatusPill } from "../components/ui/StatusPill";
import { SegmentedControl } from "../components/ui/SegmentedControl";
import { SkeletonRows } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";

/** Shared "connected / not configured" header pill. */
function StatusChip({ configured, isReal }: { configured: boolean; isReal: boolean }) {
  if (!configured) return <StatusPill tone="neutral">Not configured</StatusPill>;
  return (
    <StatusPill tone={isReal ? "success" : "info"}>
      {isReal ? "Connected" : "Mock"}
    </StatusPill>
  );
}

/* ── LHDN MyInvois (own table + OAuth-style creds) ───────────────────────────── */
const MYINVOIS_ENVS = [
  { value: "mock", label: "Mock" },
  { value: "preprod", label: "Sandbox" },
  { value: "production", label: "Production" },
];

function MyInvoisCard() {
  const { smeId } = useAuth();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [environment, setEnvironment] = useState("mock");
  const [tin, setTin] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");

  const load = useCallback(async () => {
    if (!smeId) return;
    setLoading(true);
    const { data } = await supabase
      .from("myinvois_credential")
      .select("*")
      .eq("sme_id", smeId)
      .maybeSingle();
    if (data) {
      setConfigured(true);
      setEnvironment(data.environment ?? "mock");
      setTin(data.tin ?? "");
      setClientId(data.client_id ?? "");
      setClientSecret(data.client_secret ?? "");
    }
    setLoading(false);
  }, [smeId]);
  useEffect(() => {
    load();
  }, [load]);

  const isReal = environment !== "mock";

  const save = async () => {
    if (!smeId) return;
    if (isReal && (!tin || !clientId || !clientSecret)) {
      toast({ title: "Missing credentials", description: "TIN, Client ID and Client Secret are required for a live environment.", tone: "danger" });
      return;
    }
    setSaving(true);
    const { error } = await supabase.from("myinvois_credential").upsert(
      {
        sme_id: smeId,
        model: "taxpayer",
        environment,
        tin: tin || null,
        client_id: clientId || null,
        client_secret: clientSecret || null,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "sme_id" },
    );
    setSaving(false);
    if (error) return toast({ title: "Couldn't save", description: error.message, tone: "danger" });
    setConfigured(true);
    toast({ title: "Settings saved", tone: "success" });
  };

  return (
    <Panel>
      <PanelHeader
        title="LHDN MyInvois"
        icon={<BadgeCheck className="w-4 h-4" />}
        action={<StatusChip configured={configured} isReal={isReal} />}
      />
      <div className="p-4 space-y-5">
        {loading ? (
          <SkeletonRows rows={3} cols={1} />
        ) : (
          <>
            <p className="text-sm text-ink-muted">
              Pull validated e-Invoices from LHDN MyInvois straight into reconciliation.
            </p>
            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-ink">Environment</span>
              <SegmentedControl
                aria-label="MyInvois environment"
                items={MYINVOIS_ENVS}
                value={environment}
                onChange={setEnvironment}
              />
              <p className="text-sm text-ink-muted">
                {isReal
                  ? "Register ezMatch as an ERP in your MyInvois portal (Taxpayer Profile → Register ERP) to get these."
                  : "Mock uses sample e-Invoices so you can try the flow without real credentials."}
              </p>
            </div>
            {isReal && (
              <>
                <Field label="Tax Identification Number (TIN)" value={tin} onChange={(e) => setTin(e.target.value)} placeholder="C1234567890" />
                <Field label="Client ID" value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="from MyInvois Register ERP" />
                <Field label="Client Secret" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder="••••••••" />
              </>
            )}
            <div className="flex justify-end pt-1">
              <Button onClick={save} loading={saving}>Save</Button>
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

/* ── Finverse bank feed (open-banking consent — no creds form) ───────────────────
   Finverse app creds are GLOBAL (backend .env), and the per-tenant artifact is a
   consent obtained via a hosted redirect. So this card is a Connect button + the list
   of linked banks, not a credential form. "Connect" → backend mints a Link session →
   we redirect to Finverse's hosted UI (or, in mock mode, straight back to /uploads). */
function BankFeedCard() {
  const { smeId, authHeaders } = useAuth();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [links, setLinks] = useState<any[]>([]);

  const load = useCallback(async () => {
    if (!smeId) return;
    setLoading(true);
    // RLS scopes this to the logged-in tenant.
    const { data } = await supabase
      .from("bank_feed_link")
      .select("link_id,institution,status,created_at")
      .eq("status", "active")
      .order("created_at", { ascending: false });
    setLinks(data ?? []);
    setLoading(false);
  }, [smeId]);
  useEffect(() => {
    load();
  }, [load]);

  // Toast the outcome of the Finverse redirect (callback 302s back to /settings?linked=1|0).
  useEffect(() => {
    const linked = new URLSearchParams(window.location.search).get("linked");
    if (linked === "1") {
      toast({ tone: "success", title: "Bank connected", description: "Sync transactions from the Uploads → Bank statements tab." });
      load();
    } else if (linked === "0") {
      toast({ tone: "danger", title: "Bank connection failed", description: "Couldn't complete authorization. Please try again." });
    }
    if (linked) window.history.replaceState({}, "", "/settings");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connect = async () => {
    setConnecting(true);
    try {
      const res = await fetch(`${API}/api/bankfeed/link`, { method: "POST", headers: authHeaders() });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.link_url) throw new Error(data?.detail || "Couldn't start bank connection.");
      // Full-page redirect: Finverse's hosted bank picker (or, in mock mode, our own
      // callback → /uploads). App Router handles the return route with the session intact.
      window.location.href = data.link_url;
    } catch (e) {
      setConnecting(false);
      toast({ tone: "danger", title: "Connect failed", description: (e as Error)?.message || "Is the backend running on port 8000?" });
    }
  };

  const disconnect = async (linkId: string) => {
    const { error } = await supabase.from("bank_feed_link").update({ status: "revoked" }).eq("link_id", linkId);
    if (error) return toast({ tone: "danger", title: "Couldn't disconnect", description: error.message });
    toast({ tone: "success", title: "Bank disconnected" });
    load();
  };

  return (
    <Panel>
      <PanelHeader
        title="Bank feed (Finverse)"
        icon={<Landmark className="w-4 h-4" />}
        action={<StatusChip configured={links.length > 0} isReal />}
      />
      <div className="p-4 space-y-5">
        {loading ? (
          <SkeletonRows rows={2} cols={1} />
        ) : (
          <>
            <p className="text-sm text-ink-muted">
              Connect a bank through Finverse open banking to pull transactions automatically —
              no more weekly CSV exports. Authorize once at your bank, then sync from the Bank
              statements tab.
            </p>
            {links.length > 0 && (
              <ul className="space-y-1.5">
                {links.map((l) => (
                  <li
                    key={l.link_id}
                    className="flex items-center justify-between rounded-md border border-border px-3 py-2"
                  >
                    <span className="font-medium text-ink truncate">
                      {l.institution ?? "Connected bank"}
                    </span>
                    <Button size="sm" variant="ghost" onClick={() => disconnect(l.link_id)}>
                      Disconnect
                    </Button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex justify-end pt-1">
              <Button onClick={connect} loading={connecting} icon={<Plug className="w-4 h-4" />}>
                {links.length > 0 ? "Connect another bank" : "Connect bank"}
              </Button>
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

/* ── AutoCount / SQL Account (mock-only) ─────────────────────────────────────────
   Both are mock-only: their real API documentation is behind a paid SME subscription
   (SQL Account is also on-premise), so we deliberately don't ship a guessed API path.
   Enabling saves an environment='mock' row so the connector lights up in the importer. */
function AccountingCard({
  provider,
  title,
  description,
}: {
  provider: "autocount" | "sql";
  title: string;
  description: string;
}) {
  const { smeId } = useAuth();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [configured, setConfigured] = useState(false);

  const load = useCallback(async () => {
    if (!smeId) return;
    setLoading(true);
    const { data } = await supabase
      .from("accounting_credential")
      .select("provider")
      .eq("sme_id", smeId)
      .eq("provider", provider)
      .maybeSingle();
    setConfigured(!!data);
    setLoading(false);
  }, [smeId, provider]);
  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    if (!smeId) return;
    setSaving(true);
    const { error } = await supabase.from("accounting_credential").upsert(
      { sme_id: smeId, provider, environment: "mock", updated_at: new Date().toISOString() },
      { onConflict: "sme_id,provider" },
    );
    setSaving(false);
    if (error) return toast({ title: "Couldn't save", description: error.message, tone: "danger" });
    setConfigured(true);
    toast({ title: `${title} mock import enabled`, tone: "success" });
  };

  return (
    <Panel>
      <PanelHeader
        title={title}
        icon={<Plug className="w-4 h-4" />}
        action={<StatusChip configured={configured} isReal={false} />}
      />
      <div className="p-4 space-y-4">
        {loading ? (
          <SkeletonRows rows={2} cols={1} />
        ) : (
          <>
            <p className="text-sm text-ink-muted">{description}</p>
            <div className="flex justify-end">
              <Button onClick={save} loading={saving} variant={configured ? "secondary" : "primary"}>
                {configured ? "Enabled" : "Enable mock import"}
              </Button>
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

export default function SettingsPage() {
  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8 space-y-6">
      <PageHeader
        title="Integrations"
        description="Connect the systems your invoices already live in. Configured connectors light up under “Import from connected apps” on the Invoices tab."
      />
      <BankFeedCard />
      <MyInvoisCard />
      <AccountingCard
        provider="autocount"
        title="AutoCount"
        description="Pull sales invoices from AutoCount — one of Malaysia's most-used SME accounting systems."
      />
      <AccountingCard
        provider="sql"
        title="SQL Account"
        description="Pull sales invoices from SQL Account, another leading Malaysian SME accounting system."
      />
    </div>
  );
}
