"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Landmark,
  ArrowRight,
  CheckCircle2,
  Building2,
  Hash,
  Mail,
  Lock,
} from "lucide-react";
import { Field } from "../components/ui/Field";
import { Button } from "../components/ui/Button";
import { supabase } from "../lib/supabaseClient";

const valueProps = [
  "Match bank transactions to invoices automatically",
  "Reconcile across currencies with FX accounted for",
  "Surface only the exceptions that need your decision",
];

export default function SignUpPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    company_name: "",
    registration_no: "",
    email: "",
    password: "",
  });

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    const { data, error: signUpError } = await supabase.auth.signUp({
      email: form.email.trim(),
      password: form.password,
      options: {
        data: {
          company_name: form.company_name.trim(),
          registration_no: form.registration_no.trim(),
        },
      },
    });

    if (signUpError) {
      setError(signUpError.message);
      setIsLoading(false);
      return;
    }

    // With email confirmation off, signUp returns an active session and the
    // handle_new_user trigger has already created the workspace.
    if (data.session) {
      setSuccess(true);
      setTimeout(() => router.push("/"), 1000);
    } else {
      setError(
        "Check your inbox to confirm your email, then sign in to continue.",
      );
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-bg">
      {/* Brand panel */}
      <aside className="hidden lg:flex flex-col justify-between bg-surface-2 border-r border-border p-12">
        <div className="flex items-center gap-2.5">
          <span className="flex items-center justify-center w-8 h-8 rounded-md bg-accent text-accent-fg">
            <Landmark className="w-4.5 h-4.5" />
          </span>
          <span className="font-semibold text-ink tracking-tight">
            TreasuryFlow <span className="text-ink-muted font-normal">AI</span>
          </span>
        </div>

        <div className="max-w-md space-y-6">
          <h2 className="text-2xl font-semibold text-ink leading-snug">
            Close the loop on every cross-border payment.
          </h2>
          <ul className="space-y-3">
            {valueProps.map((p) => (
              <li key={p} className="flex items-start gap-3 text-base text-ink-muted">
                <CheckCircle2 className="w-5 h-5 text-accent-text shrink-0 mt-0.5" />
                {p}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-sm text-ink-subtle">
          Built for finance teams at growing SMEs.
        </p>
      </aside>

      {/* Form */}
      <main className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <span className="flex items-center justify-center w-8 h-8 rounded-md bg-accent text-accent-fg">
              <Landmark className="w-4.5 h-4.5" />
            </span>
            <span className="font-semibold text-ink">TreasuryFlow AI</span>
          </div>

          {success ? (
            <div className="flex flex-col items-center text-center gap-4 py-8">
              <span className="flex items-center justify-center w-12 h-12 rounded-full bg-success-subtle text-success-fg">
                <CheckCircle2 className="w-6 h-6" />
              </span>
              <div className="space-y-1">
                <h1 className="text-lg font-semibold text-ink">
                  Workspace ready
                </h1>
                <p className="text-base text-ink-muted">
                  Taking you to your reconciliation dashboard…
                </p>
              </div>
            </div>
          ) : (
            <>
              <div className="mb-8 space-y-1.5">
                <h1 className="text-xl font-semibold text-ink">
                  Create your workspace
                </h1>
                <p className="text-base text-ink-muted">
                  A few details about your company to get started.
                </p>
              </div>

              <form onSubmit={handleSignUp} className="space-y-4">
                <Field
                  label="Company name"
                  placeholder="WZB Group Sdn Bhd"
                  required
                  icon={<Building2 className="w-4 h-4" />}
                  autoComplete="organization"
                  value={form.company_name}
                  onChange={(e) =>
                    setForm({ ...form, company_name: e.target.value })
                  }
                />
                <Field
                  label="Registration number"
                  placeholder="202301000000 (1234567-X)"
                  required
                  icon={<Hash className="w-4 h-4" />}
                  value={form.registration_no}
                  onChange={(e) =>
                    setForm({ ...form, registration_no: e.target.value })
                  }
                />
                <Field
                  label="Corporate email"
                  type="email"
                  placeholder="finance@company.com"
                  required
                  icon={<Mail className="w-4 h-4" />}
                  autoComplete="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
                <Field
                  label="Password"
                  type="password"
                  placeholder="At least 6 characters"
                  required
                  icon={<Lock className="w-4 h-4" />}
                  autoComplete="new-password"
                  value={form.password}
                  onChange={(e) =>
                    setForm({ ...form, password: e.target.value })
                  }
                />

                {error && (
                  <p className="text-sm text-danger-fg" role="alert">
                    {error}
                  </p>
                )}

                <Button
                  type="submit"
                  loading={isLoading}
                  className="w-full mt-2"
                  icon={!isLoading ? <ArrowRight className="w-4 h-4" /> : undefined}
                >
                  {isLoading ? "Setting up…" : "Create workspace"}
                </Button>
              </form>

              <p className="text-sm text-ink-subtle mt-6 text-center">
                Already have a workspace?{" "}
                <Link href="/login" className="text-accent-text font-medium hover:underline">
                  Sign in
                </Link>
              </p>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
