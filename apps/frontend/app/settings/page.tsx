"use client";

import React, { useState, useEffect, useCallback } from "react";
import { BadgeCheck, Plug } from "lucide-react";
import { supabase } from "../lib/supabaseClient";
import { useAuth } from "../lib/AuthContext";
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
                  ? "Register TreasuryFlow as an ERP in your MyInvois portal (Taxpayer Profile → Register ERP) to get these."
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
