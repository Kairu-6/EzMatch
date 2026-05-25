"use client";

import React, { useState } from "react";
import { Banknote, Clock, ShieldAlert, Play, Database, FileSpreadsheet, Terminal as TerminalIcon } from "lucide-react";

export default function HackathonDashboard() {
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [matchStatus, setMatchStatus] = useState<"Pending" | "Matched">("Pending");

  const terminalSequence = [
    "> [0:01] Morpheus Agent activated...",
    "> [0:02] Querying Chutes AI for Invoice inv_2026_089...",
    "> [0:03] Extracting text... Found $10.00 USD.",
    "> [0:04] Fetching historical FX rate for 2026-05-20... (1 USD = 4.21 MYR).",
    "> [0:05] Scanning Bank Ledger... Match found: -42.50 MYR line entry.",
    "> [0:06] Variance accounts for payment corridor spread (1.5%). Approved.",
    "> [0:07] Balance complete. Matrix records updated successfully."
  ];

  const runMorpheusAgent = () => {
    setIsRunning(true);
    setLogs([]);
    setMatchStatus("Pending");

    terminalSequence.forEach((logLine, index) => {
      setTimeout(() => {
        setLogs((prev) => [...prev, logLine]);
        if (index === terminalSequence.length - 1) {
          setIsRunning(false);
          setMatchStatus("Matched");
        }
      }, (index + 1) * 600);
    });
  };

  return (
    <div className="max-w-7xl mx-auto space-y-8 pb-32">
      {/* HERO METRIC CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 rounded-xl shadow-xs">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">Total Funds Reconciled</span>
              <p className="text-2xl font-mono font-bold text-slate-900 dark:text-white mt-1">$1.2M USD</p>
            </div>
            <span className="bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 p-2.5 rounded-lg border border-emerald-100 dark:border-emerald-900/40">
              <Banknote className="w-5 h-5" />
            </span>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 rounded-xl shadow-xs">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">Hours Saved by AI</span>
              <p className="text-2xl font-mono font-bold text-slate-900 dark:text-white mt-1">142 Hours</p>
            </div>
            <span className="bg-blue-50 dark:bg-blue-950/50 text-blue-600 p-2.5 rounded-lg border border-blue-100 dark:border-blue-900/40">
              <Clock className="w-5 h-5" />
            </span>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 rounded-xl shadow-xs">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">FX Leakage Prevented</span>
              <p className="text-2xl font-mono font-bold text-emerald-600 dark:text-emerald-400 mt-1">$4,500 Saved</p>
            </div>
            <span className="bg-amber-50 dark:bg-amber-950/50 text-amber-600 p-2.5 rounded-lg border border-amber-200 dark:border-amber-900/40">
              <ShieldAlert className="w-5 h-5" />
            </span>
          </div>
        </div>
      </div>

      {/* FINANCIAL CHARTS GRAPHICAL SIMULATION */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 rounded-xl shadow-xs">
          <span className="text-xs font-bold text-slate-400 uppercase font-mono">Volume by Currency Corridor</span>
          <div className="mt-4 space-y-3">
            <div>
              <div className="flex justify-between text-xs font-mono mb-1"><span>USD Gateway</span><span>72%</span></div>
              <div className="w-full bg-slate-100 dark:bg-slate-800 h-2.5 rounded-full overflow-hidden"><div className="bg-emerald-500 h-full w-[72%]"></div></div>
            </div>
            <div>
              <div className="flex justify-between text-xs font-mono mb-1"><span>MYR Settlement Pool</span><span>20%</span></div>
              <div className="w-full bg-slate-100 dark:bg-slate-800 h-2.5 rounded-full overflow-hidden"><div className="bg-blue-500 h-full w-[20%]"></div></div>
            </div>
            <div>
              <div className="flex justify-between text-xs font-mono mb-1"><span>SGD Liquidity</span><span>8%</span></div>
              <div className="w-full bg-slate-100 dark:bg-slate-800 h-2.5 rounded-full overflow-hidden"><div className="bg-amber-500 h-full w-[8%]"></div></div>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 rounded-xl shadow-xs flex flex-col justify-between">
          <span className="text-xs font-bold text-slate-400 uppercase font-mono">Reconciliation Engine Accuracy</span>
          <div className="flex items-center justify-center py-4">
            <div className="relative w-28 h-28 rounded-full border-[12px] border-emerald-500 flex items-center justify-center border-t-slate-200 dark:border-t-slate-800">
              <span className="text-xs font-mono font-bold text-center absolute">94.2%<br/><span className="text-[9px] text-slate-400">MATCHED</span></span>
            </div>
          </div>
        </div>
      </div>

      {/* THE ENGINE SECTION */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b dark:border-slate-800 pb-3">
          <h3 className="text-sm font-black uppercase text-slate-800 dark:text-slate-200 tracking-wider">The Engine: Multi-Currency Core Ledger</h3>
          <button
            onClick={runMorpheusAgent}
            disabled={isRunning}
            className="bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold text-xs px-5 py-3 rounded-xl flex items-center gap-2 shadow-md transition cursor-pointer disabled:opacity-50"
          >
            <Play className={`w-3.5 h-3.5 fill-white ${isRunning ? "animate-spin" : ""}`} />
            RUN MORPHEUS AGENT
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-xs">
            <div className="p-3 bg-slate-100/60 dark:bg-slate-950/50 border-b dark:border-slate-800 flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-500" />
              <span className="text-xs font-bold uppercase font-mono">Source Feed: Bank Operating Account</span>
            </div>
            <div className="p-4 overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="text-slate-400 border-b dark:border-slate-800 text-[10px]">
                    <th className="pb-2">Date</th>
                    <th className="pb-2">Bank Description</th>
                    <th className="pb-2 text-right">Settled (MYR)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="py-3">2026-05-20</td>
                    <td><span className="font-sans font-bold block">STRIPE PAYOUT OUTBOUND</span></td>
                    <td className="py-3 text-right font-bold">RM 42.50</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-xs">
            <div className="p-3 bg-slate-100/60 dark:bg-slate-950/50 border-b dark:border-slate-800 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4 text-emerald-500" />
                <span className="text-xs font-bold uppercase font-mono">Extracted Feed: Chutes AI OCR</span>
              </div>
              <span className={`px-2 py-0.5 rounded-sm font-sans font-bold text-[10px] uppercase border tracking-wider transition-all duration-300 ${
                matchStatus === "Pending" ? "bg-slate-100 dark:bg-slate-800 text-slate-500 border-slate-200" : "bg-emerald-50 dark:bg-emerald-950 text-emerald-400 border-emerald-500"
              }`}>
                {matchStatus === "Pending" ? "⏳ Pending" : "🟢 Matched"}
              </span>
            </div>
            <div className="p-4 overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="text-slate-400 border-b dark:border-slate-800 text-[10px]">
                    <th className="pb-2">Document ID</th>
                    <th className="pb-2">Foreign Value</th>
                    <th className="pb-2 text-right">Target FX Rate</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="py-3 font-bold text-emerald-600">INV-2026-089.pdf</td>
                    <td className="py-3 font-bold">$10.00 USD</td>
                    <td className="py-3 text-right">1 USD = 4.21 MYR</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* FIXED FOOTER TERMINAL */}
      <div className="fixed bottom-0 left-0 right-0 lg:left-64 bg-slate-950 text-slate-200 border-t border-slate-800 shadow-2xl z-50">
        <div className="bg-slate-900 px-4 py-2 flex items-center justify-between border-b border-slate-800">
          <span className="text-xs font-mono font-bold text-emerald-400 flex items-center gap-2">
            <TerminalIcon className="w-3.5 h-3.5" /> Morpheus Autonomous Reasoning Console
          </span>
        </div>
        <div className="p-4 h-32 overflow-y-auto font-mono text-xs space-y-1 bg-slate-950">
          {logs.length === 0 ? (
            <p className="text-slate-500 italic">{">"} Awaiting trigger... Click "RUN MORPHEUS AGENT" to trace algorithmic logic lines.</p>
          ) : (
            logs.map((line, idx) => (
              <p key={idx} className={idx === logs.length - 1 ? "text-emerald-400 font-bold" : "text-slate-300"}>{line}</p>
            ))
          )}
        </div>
      </div>
    </div>
  );
}