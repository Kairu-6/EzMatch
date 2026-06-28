"use client";

import { useAuth } from "./lib/AuthContext";
import { LandingPage } from "./components/LandingPage";
import { DashboardPage } from "./components/DashboardPage";

export default function Page() {
  const { session, loading } = useAuth();
  if (loading) return null;
  if (!session) return <LandingPage />;
  return <DashboardPage />;
}
