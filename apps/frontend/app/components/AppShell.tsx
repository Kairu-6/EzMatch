"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  History,
  Clock,
  ReceiptText,
  FileSpreadsheet,
  ShieldCheck,
  LogOut,
  RefreshCw,
  Landmark,
  ChevronDown,
  CircleUser,
  Menu,
  X,
} from "lucide-react";
import { useAuth } from "../lib/AuthContext";
import { ToastProvider } from "./ui/Toast";
import { MeshBackground } from "./MeshBackground";
import { cn } from "./ui/cn";

const AUTH_ROUTES = ["/login", "/signup"];
// Public routes render without the app shell and without an auth redirect.
// The page itself handles auth-conditional content (landing vs. dashboard).
const PUBLIC_ROUTES = ["/"];

type MenuLink = { href: string; label: string; icon: React.ElementType };

const HOME_ITEMS: MenuLink[] = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/audit", label: "Audit log", icon: History },
  { href: "/history", label: "History", icon: Clock },
];

const UPLOAD_ITEMS: MenuLink[] = [
  { href: "/uploads?tab=invoices", label: "Invoice", icon: ReceiptText },
  { href: "/uploads?tab=statements", label: "Bank statement", icon: FileSpreadsheet },
  { href: "/uploads?tab=proofs", label: "Payment proof", icon: ShieldCheck },
];

/** Desktop dropdown menu of links. Open state is owned by the parent so only
 *  one menu is open at a time; closes on outside click + Escape. */
function NavDropdown({
  id,
  label,
  active,
  items,
  openId,
  setOpenId,
  onNavigate,
}: {
  id: string;
  label: string;
  active: boolean;
  items: MenuLink[];
  openId: string | null;
  setOpenId: (v: string | null) => void;
  onNavigate?: () => void;
}) {
  const open = openId === id;
  return (
    <div className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpenId(open ? null : id)}
        className={cn(
          "flex items-center gap-1 px-3 h-9 rounded-md text-base transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent",
          active || open
            ? "text-ink bg-surface"
            : "text-ink-muted hover:text-ink hover:bg-surface/60",
        )}
      >
        {label}
        <ChevronDown
          className={cn(
            "w-3.5 h-3.5 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 top-full mt-1.5 min-w-[210px] rounded-lg border border-border bg-surface shadow-md p-1 z-30"
        >
          {items.map(({ href, label: l, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              role="menuitem"
              onClick={() => {
                setOpenId(null);
                onNavigate?.();
              }}
              className="flex items-center gap-2.5 px-3 h-9 rounded-md text-base text-ink-muted hover:bg-surface-2 hover:text-ink transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <Icon className="w-4 h-4 text-ink-subtle shrink-0" />
              {l}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { companyName, signOut } = useAuth();
  const [openId, setOpenId] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null);

  // Close menus on outside click + Escape.
  useEffect(() => {
    if (!openId && !mobileOpen) return;
    const onDown = (e: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpenId(null);
        setMobileOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpenId(null);
        setMobileOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [openId, mobileOpen]);

  // Close everything on route change.
  useEffect(() => {
    setOpenId(null);
    setMobileOpen(false);
  }, [pathname]);

  const homeActive =
    pathname === "/" || pathname === "/audit" || pathname === "/history";
  const uploadActive = pathname === "/uploads";

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };
  // One user = one workspace today, so "Change account" signs out to the login
  // screen where a different account can be used.
  const handleChangeAccount = handleSignOut;

  const workspaceName = companyName ?? "Workspace";

  return (
    <header
      ref={navRef}
      className="shrink-0 bg-surface-2 border-b border-border"
    >
      <div className="max-w-7xl mx-auto h-16 px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-4">
        {/* Left: logo + desktop menus */}
        <div className="flex items-center gap-6 min-w-0">
          <Link href="/" className="flex items-center gap-2.5 shrink-0 outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-md">
            <span className="flex items-center justify-center w-8 h-8 rounded-md bg-accent text-accent-fg">
              <Landmark className="w-4.5 h-4.5" />
            </span>
            <span className="font-semibold text-ink tracking-tight hidden sm:inline">
              TreasuryFlow <span className="text-ink-muted font-normal">AI</span>
            </span>
          </Link>

          <nav className="hidden lg:flex items-center gap-1" aria-label="Primary">
            <NavDropdown
              id="home"
              label="Home"
              active={homeActive}
              items={HOME_ITEMS}
              openId={openId}
              setOpenId={setOpenId}
            />
            <NavDropdown
              id="upload"
              label="Upload"
              active={uploadActive}
              items={UPLOAD_ITEMS}
              openId={openId}
              setOpenId={setOpenId}
            />
          </nav>
        </div>

        {/* Right: profile (desktop) + hamburger (mobile) */}
        <div className="flex items-center gap-2">
          {/* Desktop profile menu */}
          <div className="relative hidden lg:block">
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={openId === "profile"}
              onClick={() => setOpenId(openId === "profile" ? null : "profile")}
              className={cn(
                "flex items-center gap-2 pl-2 pr-2.5 h-9 rounded-md text-base transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent",
                openId === "profile"
                  ? "text-ink bg-surface"
                  : "text-ink-muted hover:text-ink hover:bg-surface/60",
              )}
            >
              <CircleUser className="w-5 h-5" />
              <span className="max-w-[140px] truncate text-sm font-medium">
                {workspaceName}
              </span>
              <ChevronDown
                className={cn(
                  "w-3.5 h-3.5 transition-transform",
                  openId === "profile" && "rotate-180",
                )}
              />
            </button>

            {openId === "profile" && (
              <div
                role="menu"
                className="absolute right-0 top-full mt-1.5 min-w-[200px] rounded-lg border border-border bg-surface shadow-md p-1 z-30"
              >
                <div className="px-3 py-2 border-b border-border mb-1">
                  <p className="text-sm font-medium text-ink truncate">
                    {workspaceName}
                  </p>
                  <p className="text-xs text-ink-subtle">SME workspace</p>
                </div>
                <button
                  role="menuitem"
                  onClick={handleChangeAccount}
                  className="flex w-full items-center gap-2.5 px-3 h-9 rounded-md text-base text-ink-muted hover:bg-surface-2 hover:text-ink transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  <RefreshCw className="w-4 h-4 text-ink-subtle shrink-0" />
                  Change account
                </button>
                <button
                  role="menuitem"
                  onClick={handleSignOut}
                  className="flex w-full items-center gap-2.5 px-3 h-9 rounded-md text-base text-ink-muted hover:bg-surface-2 hover:text-danger-fg transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  <LogOut className="w-4 h-4 text-ink-subtle shrink-0" />
                  Log out
                </button>
              </div>
            )}
          </div>

          {/* Mobile hamburger */}
          <button
            type="button"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={mobileOpen}
            className="lg:hidden flex items-center justify-center w-9 h-9 rounded-md text-ink-muted hover:bg-surface hover:text-ink transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile dropdown panel */}
      {mobileOpen && (
        <div className="lg:hidden border-t border-border bg-surface-2 animate-[fade-in_150ms_ease-out]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 space-y-4">
            <MobileSection title="Home" items={HOME_ITEMS} onNavigate={() => setMobileOpen(false)} />
            <MobileSection title="Upload" items={UPLOAD_ITEMS} onNavigate={() => setMobileOpen(false)} />
            <div className="pt-3 border-t border-border space-y-0.5">
              <div className="px-3 pb-1">
                <p className="text-sm font-medium text-ink truncate">{workspaceName}</p>
                <p className="text-xs text-ink-subtle">SME workspace</p>
              </div>
              <button
                onClick={handleChangeAccount}
                className="flex w-full items-center gap-2.5 px-3 h-10 rounded-md text-base text-ink-muted hover:bg-surface hover:text-ink transition-colors"
              >
                <RefreshCw className="w-4 h-4 text-ink-subtle shrink-0" /> Change account
              </button>
              <button
                onClick={handleSignOut}
                className="flex w-full items-center gap-2.5 px-3 h-10 rounded-md text-base text-ink-muted hover:bg-surface hover:text-danger-fg transition-colors"
              >
                <LogOut className="w-4 h-4 text-ink-subtle shrink-0" /> Log out
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

function MobileSection({
  title,
  items,
  onNavigate,
}: {
  title: string;
  items: MenuLink[];
  onNavigate: () => void;
}) {
  return (
    <div className="space-y-0.5">
      <p className="px-3 text-xs font-medium text-ink-subtle mb-1">{title}</p>
      {items.map(({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          onClick={onNavigate}
          className="flex items-center gap-2.5 px-3 h-10 rounded-md text-base text-ink-muted hover:bg-surface hover:text-ink transition-colors"
        >
          <Icon className="w-4 h-4 text-ink-subtle shrink-0" />
          {label}
        </Link>
      ))}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, loading } = useAuth();

  const onAuthRoute = AUTH_ROUTES.includes(pathname);
  const onPublicRoute = PUBLIC_ROUTES.includes(pathname);

  useEffect(() => {
    if (loading) return;
    if (!session && !onAuthRoute && !onPublicRoute) {
      router.push("/login");
    } else if (session && onAuthRoute) {
      router.push("/");
    }
  }, [session, loading, onAuthRoute, onPublicRoute, router]);

  // Auth surface (login / signup) renders without the app shell.
  if (onAuthRoute) return <>{children}</>;

  // Wait for auth state to resolve before branching.
  if (loading) return null;

  // Public routes (e.g. landing page at "/"): render without the nav shell.
  // The page itself is responsible for auth-conditional content.
  if (onPublicRoute && !session) return <ToastProvider>{children}</ToastProvider>;

  // Block protected content for unauthenticated visitors (redirect fires above).
  if (!session) return null;

  return (
    <ToastProvider>
      <div className="relative flex flex-col h-screen w-screen overflow-hidden bg-bg text-ink">
        {/* Faint shared motive — sits behind the nav + content. */}
        <MeshBackground variant="app" />
        <div className="relative z-10 flex flex-col flex-1 min-h-0">
          <TopNav />
          <main className="flex-1 overflow-y-auto">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 lg:py-8 pb-24">
              {children}
            </div>
          </main>
        </div>
      </div>
      <style>{`
        @keyframes fade-in{from{opacity:0}to{opacity:1}}
      `}</style>
    </ToastProvider>
  );
}
