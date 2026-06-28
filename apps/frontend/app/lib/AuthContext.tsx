"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabaseClient";

type AuthValue = {
  session: Session | null;
  smeId: string | null;
  companyName: string | null;
  loading: boolean;
  signOut: () => Promise<void>;
  /** Authorization header for backend (FastAPI) calls. Empty when signed out. */
  authHeaders: () => Record<string, string>;
};

const AuthContext = createContext<AuthValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [smeId, setSmeId] = useState<string | null>(null);
  const [companyName, setCompanyName] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setSession(data.session);
      setLoading(false);
    });

    // IMPORTANT: this callback MUST stay synchronous. Awaiting a supabase call
    // (e.g. a `.from(...)` query) inside onAuthStateChange deadlocks the auth
    // client's internal lock — every later query then hangs until a full page
    // reload. Auth events fire on tab focus and token refresh, so doing async
    // work here makes navigation intermittently freeze data loading. Workspace
    // resolution lives in the effect below instead.
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => {
      if (!mounted) return;
      setSession(s);
    });

    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  // Resolve the workspace (sme row) whenever the signed-in user changes —
  // outside the auth-state callback to avoid the deadlock described above.
  const userId = session?.user?.id ?? null;
  useEffect(() => {
    let active = true;
    (async () => {
      if (!userId) {
        setSmeId(null);
        setCompanyName(null);
        return;
      }
      const { data } = await supabase
        .from("sme")
        .select("sme_id, company_name")
        .eq("user_id", userId)
        .limit(1)
        .maybeSingle();
      if (!active) return;
      setSmeId(data?.sme_id ?? null);
      setCompanyName(data?.company_name ?? null);
    })();
    return () => {
      active = false;
    };
  }, [userId]);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
  }, []);

  const authHeaders = useCallback((): Record<string, string> => {
    const token = session?.access_token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [session]);

  return (
    <AuthContext.Provider
      value={{ session, smeId, companyName, loading, signOut, authHeaders }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
