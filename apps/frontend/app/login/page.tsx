"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Landmark, ArrowRight, CheckCircle2, Mail, Lock } from "lucide-react";
import { Field } from "../components/ui/Field";
import { Button } from "../components/ui/Button";
import { MeshBackground } from "../components/MeshBackground";
import { supabase } from "../lib/supabaseClient";

const valueProps = [
  "Match bank transactions to invoices automatically",
  "Reconcile across currencies with FX accounted for",
  "Surface only the exceptions that need your decision",
];

export default function LoginPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ email: "", password: "" });

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: form.email.trim(),
      password: form.password,
    });

    if (signInError) {
      setError(signInError.message);
      setIsLoading(false);
      return;
    }

    // onAuthStateChange updates the AuthContext; push to the dashboard.
    router.push("/");
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-bg">
      {/* Brand panel */}
      <aside className="relative overflow-hidden hidden lg:flex flex-col justify-between bg-surface-2 border-r border-border p-12">
        <MeshBackground variant="auth" />
        <div className="relative z-10 flex flex-col justify-between h-full">
        <Link
          href="/"
          aria-label="ezMatch home"
          className="flex items-center gap-2.5 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent w-fit"
        >
          <span className="flex items-center justify-center w-8 h-8 rounded-md bg-accent text-accent-fg">
            <Landmark className="w-4.5 h-4.5" />
          </span>
          <span className="font-semibold text-ink tracking-tight">
            ezMatch
          </span>
        </Link>

        <div className="max-w-md space-y-6">
          <h2 className="text-2xl font-semibold text-ink leading-snug">
            Welcome back to your reconciliation desk.
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
        </div>
      </aside>

      {/* Form */}
      <main className="flex items-center justify-center p-6 sm:p-12">
        <div className="w-full max-w-sm">
          <Link
            href="/"
            aria-label="ezMatch home"
            className="lg:hidden flex items-center gap-2.5 mb-8 w-fit rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <span className="flex items-center justify-center w-8 h-8 rounded-md bg-accent text-accent-fg">
              <Landmark className="w-4.5 h-4.5" />
            </span>
            <span className="font-semibold text-ink">ezMatch</span>
          </Link>

          <div className="mb-8 space-y-1.5">
            <h1 className="text-xl font-semibold text-ink">Sign in</h1>
            <p className="text-base text-ink-muted">
              Access your reconciliation dashboard.
            </p>
          </div>

          <form onSubmit={handleSignIn} className="space-y-4">
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
              placeholder="Your password"
              required
              icon={<Lock className="w-4 h-4" />}
              autoComplete="current-password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
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
              {isLoading ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <p className="text-sm text-ink-subtle mt-6 text-center">
            New to ezMatch?{" "}
            <Link href="/signup" className="text-accent-text font-medium hover:underline">
              Create a workspace
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
