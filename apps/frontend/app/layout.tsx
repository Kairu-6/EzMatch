"use client";
import React, { useEffect } from "react";
import "./globals.css";
import { ThemeProvider, useTheme } from "./ThemeContext";
import Link from "next/link"; 
import { usePathname, useRouter } from "next/navigation";
import { Landmark, Scale, FileSpreadsheet, History, ShieldAlert, LogOut, Sun, Moon } from "lucide-react";

function LayoutContent({ children }: { children: React.ReactNode }) {
  const { darkMode, toggleDarkMode } = useTheme();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    const isSignedUp = sessionStorage.getItem("isSignedUp");
    if (!isSignedUp && pathname !== "/signup") {
      router.push("/signup");
    }
  }, [pathname, router]);

  const handleSignOut = () => {
    sessionStorage.removeItem("isSignedUp");
    router.push("/signup");
  };

  if (pathname === "/signup") return <>{children}</>;

  // Navigation Items Configuration
  const navItems = [
    { href: "/", label: "Reconciliation", icon: Scale },
    { href: "/statement", label: "Bank Statements", icon: FileSpreadsheet },
    { href: "/invoices", label: "Invoices", icon: FileSpreadsheet },
    { href: "/proofs", label: "Payment Proofs", icon: ShieldAlert },
    { href: "/audit", label: "Audit Log", icon: History },
  ];

  return (
    <div className={`flex h-screen w-screen overflow-hidden ${darkMode ? "dark bg-slate-950 text-slate-100" : "bg-slate-50 text-slate-900"}`}>
      <aside className="w-64 bg-slate-900 text-slate-300 flex flex-col p-5 border-r border-slate-800">
        <div className="flex items-center gap-3 mb-8 px-2">
            <div className="bg-emerald-500 text-slate-950 p-2 rounded-lg"><Landmark className="w-5 h-5" /></div>
            <span className="font-extrabold text-white uppercase">TreasuryFlow AI</span>
        </div>
        
        <nav className="space-y-1 flex-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link 
                key={item.href} 
                href={item.href} 
                className={`flex items-center gap-3 px-3 py-2 rounded-md transition-all ${
                  isActive 
                    ? "bg-slate-800 text-white shadow-md border-l-4 border-emerald-500" 
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
              >
                <Icon className="w-4 h-4" /> {item.label}
              </Link>
            );
          })}
          
          <button 
            onClick={handleSignOut} 
            className="flex w-full items-center gap-3 px-3 py-2 mt-4 rounded-md text-red-400 hover:bg-red-950/30 transition-colors"
          > 
            <LogOut className="w-4 h-4" /> Sign Out 
          </button>
        </nav>

        <button 
          onClick={toggleDarkMode} 
          className="p-2 bg-slate-800 rounded-lg flex items-center justify-center gap-2 hover:bg-slate-700 transition-colors"
        >
            {darkMode ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4" />}
        </button>
      </aside>
      
      <main className="flex-1 overflow-y-auto p-8 bg-slate-50 dark:bg-slate-950">{children}</main>
    </div>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased"><ThemeProvider><LayoutContent>{children}</LayoutContent></ThemeProvider></body>
    </html>
  );
}