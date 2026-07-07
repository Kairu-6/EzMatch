"use client";

import React, { useState, useEffect, useCallback } from "react";
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

type Env = "mock" | "preprod" | "production";

const ENV_ITEMS = [
  { value: "mock", label: "Mock" },
  { value: "preprod", label: "Sandbox" },
  { value: "production", label: "Production" },
];

export default function SettingsPage() {
  const { smeId } = useAuth();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [environment, setEnvironment] = useState<Env>("mock");
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
      setEnvironment((data.environment as Env) ?? "mock");
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
    if (error) {
      toast({ title: "Couldn't save", description: error.message, tone: "danger" });
      return;
    }
    setConfigured(true);
    toast({ title: "MyInvois settings saved", tone: "success" });
  };

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
      <PageHeader
        title="MyInvois integration"
        description="Pull validated e-Invoices from LHDN MyInvois straight into reconciliation — no PDF uploads, no parse failures."
        action={
          configured ? (
            <StatusPill tone={isReal ? "success" : "info"}>
              {isReal ? "Connected" : "Connected — sandbox mock"}
            </StatusPill>
          ) : (
            <StatusPill tone="neutral">Not configured</StatusPill>
          )
        }
      />

      <Panel>
        <PanelHeader title="Taxpayer credentials" />
        <div className="p-4 space-y-5">
          {loading ? (
            <SkeletonRows rows={3} cols={1} />
          ) : (
            <>
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium text-ink">Environment</span>
                <SegmentedControl
                  aria-label="MyInvois environment"
                  items={ENV_ITEMS}
                  value={environment}
                  onChange={(v) => setEnvironment(v as Env)}
                />
                <p className="text-sm text-ink-muted">
                  {isReal
                    ? "Register TreasuryFlow as an ERP in your MyInvois portal (Taxpayer Profile → Register ERP) to get these."
                    : "Mock uses sample e-Invoices so you can try the flow without real credentials."}
                </p>
              </div>

              {isReal && (
                <>
                  <Field
                    label="Tax Identification Number (TIN)"
                    value={tin}
                    onChange={(e) => setTin(e.target.value)}
                    placeholder="C1234567890"
                  />
                  <Field
                    label="Client ID"
                    value={clientId}
                    onChange={(e) => setClientId(e.target.value)}
                    placeholder="from MyInvois Register ERP"
                  />
                  <Field
                    label="Client Secret"
                    type="password"
                    value={clientSecret}
                    onChange={(e) => setClientSecret(e.target.value)}
                    placeholder="••••••••"
                  />
                </>
              )}

              <div className="flex justify-end pt-1">
                <Button onClick={save} loading={saving}>
                  Save
                </Button>
              </div>
            </>
          )}
        </div>
      </Panel>

      <p className="text-sm text-ink-subtle mt-4">
        After saving, go to <span className="text-ink-muted">Uploads → Invoices</span> and click{" "}
        <span className="text-ink-muted">Sync from MyInvois</span>.
      </p>
    </div>
  );
}
