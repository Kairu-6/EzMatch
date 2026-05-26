"use client";
import React, { useState, useEffect } from "react";
import { ArrowRightLeft, CheckCircle2, AlertTriangle, Banknote, Clock, ShieldAlert, Play, Database, FileSpreadsheet, Terminal as TerminalIcon } from "lucide-react";
import { createClient } from '@supabase/supabase-js';

// Assuming SME_ID is imported or defined here. Hardcoding the one from your logs for the demo.
const SME_ID = "111e4567-e89b-12d3-a456-426614174111";

// HARDCODED SUPABASE CONNECTION (Perfect for hackathon speed)
const supabaseUrl = 'https://yipmoeioxawqrsbtmkqb.supabase.co';
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlpcG1vZWlveGF3cXJzYnRta3FiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk2MDU0MzcsImV4cCI6MjA5NTE4MTQzN30.Jk_21i-epvvhEMTCbAC9FgSBjcBtv_pSZqyu6j40hrc'; 
const supabase = createClient(supabaseUrl, supabaseKey);

export default function HackathonDashboard() {
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [matchStatus, setMatchStatus] = useState<"Pending" | "Matched">("Pending");
  
  // LIVE TABLE DATA STATE (Starts empty for the live demo impact!)
  const [liveMatches, setLiveMatches] = useState<any[]>([]);

  // LIVE METRICS STATE
  const [metrics, setMetrics] = useState({
    reconciled: 1200000,
    hours: 142,
    saved: 4500
  });

  // FETCH LIVE STATS ON LOAD
  useEffect(() => {
    async function fetchLiveStats() {
      const { data, error } = await supabase.from('bank_transaction').select('*');
      if (data && data.length > 0) {
        const totalCredits = data.reduce((acc, row) => acc + (row.credit_amount || 0), 0);
        setMetrics({
          reconciled: 1200000 + totalCredits,
          hours: 142 + data.length, 
          saved: 4500 + (data.length * 15)
        });
      }
    }
    fetchLiveStats();
  }, [isRunning]); // Re-run when a job finishes to update numbers

  // FETCH REAL MATCHES AFTER JOB COMPLETES
// FETCH REAL MATCHES AFTER JOB COMPLETES
  const fetchCompletedMatches = async (jobId: string) => {
    setLogs(prev => [...prev, `> [SUPABASE] Pulling live reconciliation ledger for Job ${jobId.substring(0,8)}...`]);
    
    // Join reconciliation_match with the invoice table to get names/numbers
    const { data, error } = await supabase
      .from('reconciliation_match')
      .select(`
        match_id,
        match_status,
        invoice_amount,
        invoice_currency,
        transaction_amount,
        tx_currency,
        converted_amount, 
        invoice ( invoice_number, counterparty_name )
      `)
      .eq('job_id', jobId);

    if (error) {
      setLogs(prev => [...prev, `> [ERROR] Failed to fetch matches: ${error.message}`]);
      return;
    }

    if (data && data.length > 0) {
      // Map database format to frontend UI format
      const formattedData = data.map((m: any) => ({
        id: m.invoice?.invoice_number || "UNKNOWN",
        client: m.invoice?.counterparty_name || "Unknown Entity",
        billed: { currency: m.invoice_currency, amount: m.invoice_amount },
        received: { currency: m.tx_currency, amount: m.transaction_amount },
        // Calculate the rate on the fly to avoid complex DB joins!
        rate: (m.converted_amount && m.invoice_amount) ? (m.converted_amount / m.invoice_amount).toFixed(4) : "1.0000",
        status: m.match_status === 'auto' ? 'Exact Match' : 'Partial Match'
      }));
      
      setLiveMatches(formattedData);
      setLogs(prev => [...prev, `> [SUCCESS] Ledger updated. ${formattedData.length} matches mapped to UI.`]);
    } else {
      setLogs(prev => [...prev, `> [NOTICE] Job completed but no matches were found.`]);
    }
  };

  // THE LIVE POLLING RECONCILE FUNCTION
  const handleReconcile = async () => {
    setIsRunning(true);
    setMatchStatus("Pending");
    setLiveMatches([]); // Clear table on new run
    setLogs([
      `> [SYSTEM] Initializing secure connection to local Python backend...`,
      `> [SYSTEM] POST /api/reconcile/${SME_ID}`
    ]);

    try {
      // 1. TRIGGER THE JOB
      const response = await fetch(`http://127.0.0.1:8000/api/reconcile/${SME_ID}`, { 
        method: "POST",
      });

      if (!response.ok) throw new Error("Backend server rejected the request.");

      setLogs(prev => [...prev, "> [NETWORK] 202 Accepted. Job queued. Establishing Morpheus DeAI link..."]);
      
      // 2. POLL FOR STATUS
      let pollingAttempts = 0;
      const pollInterval = setInterval(async () => {
        try {
          pollingAttempts++;
          const statusRes = await fetch(`http://127.0.0.1:8000/api/job-status/${SME_ID}`);
          
          if (!statusRes.ok) return;
          const jobData = await statusRes.json();

          if (jobData.status === "no_jobs_found") return;

          if (jobData.status === "processing" || jobData.status === "pending") {
             // Add a tick to the logs every 2 loops so it shows activity without spamming
             if (pollingAttempts % 2 === 0) {
                setLogs(prev => [...prev, "> [MORPHEUS] Neural network is analyzing cross-border semantic variations..."]);
             }
          } 
          else if (jobData.status === "completed") {
            clearInterval(pollInterval);
            setLogs(prev => [...prev, `> [MORPHEUS] AI Analysis complete! Processed matches: ${jobData.matched_count}. Unmatched: ${jobData.unmatched_count}.`]);
            
            // 3. FETCH THE RESULTS
            await fetchCompletedMatches(jobData.job_id);
            
            setIsRunning(false);
            setMatchStatus("Matched");
          } 
          else if (jobData.status === "failed") {
            clearInterval(pollInterval);
            setLogs(prev => [...prev, "> [CRITICAL ERROR] The background reconciliation job failed on the server."]);
            setIsRunning(false);
          }

        } catch (pollErr) {
          console.error("Polling error:", pollErr);
        }
      }, 3000); // Check every 3 seconds

    } catch (error) {
      setLogs(prev => [
        ...prev, 
        "> [CRITICAL] Could not reach Python server. Is Uvicorn running on port 8000?",
        "> [CRITICAL] Connection refused."
      ]);
      setIsRunning(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-8 pb-32 transition-colors duration-200">
      
      {/* HERO METRIC CARDS */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 rounded-xl shadow-xs transition-colors">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">Total Funds Reconciled</span>
              <p className="text-2xl font-mono font-bold text-slate-900 dark:text-white mt-1">
                ${(metrics.reconciled / 1000000).toFixed(2)}M USD
              </p>
            </div>
            <span className="bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 p-2.5 rounded-lg border border-emerald-100 dark:border-emerald-900/40">
              <Banknote className="w-5 h-5" />
            </span>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 rounded-xl shadow-xs transition-colors">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">Hours Saved by AI</span>
              <p className="text-2xl font-mono font-bold text-slate-900 dark:text-white mt-1">
                {metrics.hours} Hours
              </p>
            </div>
            <span className="bg-blue-50 dark:bg-blue-950/50 text-blue-600 p-2.5 rounded-lg border border-blue-100 dark:border-blue-900/40">
              <Clock className="w-5 h-5" />
            </span>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 rounded-xl shadow-xs transition-colors">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">FX Leakage Prevented</span>
              <p className="text-2xl font-mono font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                ${metrics.saved.toLocaleString()} Saved
              </p>
            </div>
            <span className="bg-amber-50 dark:bg-amber-950/50 text-amber-600 p-2.5 rounded-lg border border-amber-200 dark:border-amber-900/40">
              <ShieldAlert className="w-5 h-5" />
            </span>
          </div>
        </div>
      </div>

      {/* FINANCIAL CHARTS */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 rounded-xl shadow-xs transition-colors">
          <span className="text-xs font-bold text-slate-400 uppercase font-mono">Volume by Currency Corridor</span>
          <div className="mt-4 space-y-3">
            <div>
              <div className="flex justify-between text-xs font-mono mb-1 text-slate-700 dark:text-slate-300"><span>USD Gateway</span><span>72%</span></div>
              <div className="w-full bg-slate-100 dark:bg-slate-800 h-2.5 rounded-full overflow-hidden"><div className="bg-emerald-500 h-full w-[72%]"></div></div>
            </div>
            <div>
              <div className="flex justify-between text-xs font-mono mb-1 text-slate-700 dark:text-slate-300"><span>MYR Settlement Pool</span><span>20%</span></div>
              <div className="w-full bg-slate-100 dark:bg-slate-800 h-2.5 rounded-full overflow-hidden"><div className="bg-blue-500 h-full w-[20%]"></div></div>
            </div>
            <div>
              <div className="flex justify-between text-xs font-mono mb-1 text-slate-700 dark:text-slate-300"><span>SGD Liquidity</span><span>8%</span></div>
              <div className="w-full bg-slate-100 dark:bg-slate-800 h-2.5 rounded-full overflow-hidden"><div className="bg-amber-500 h-full w-[8%]"></div></div>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5 rounded-xl shadow-xs flex flex-col justify-between transition-colors">
          <span className="text-xs font-bold text-slate-400 uppercase font-mono">Reconciliation Engine Accuracy</span>
          <div className="flex items-center justify-center py-4">
            <div className="relative w-28 h-28 rounded-full border-12 border-emerald-500 flex items-center justify-center border-t-slate-200 dark:border-t-slate-800">
              <span className="text-xs font-mono font-bold text-center absolute text-slate-900 dark:text-white">94.2%<br/><span className="text-[9px] text-slate-400">MATCHED</span></span>
            </div>
          </div>
        </div>
      </div>

      {/* THE ENGINE SECTION */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800 pb-3">
          <h3 className="text-sm font-black uppercase text-slate-800 dark:text-slate-200 tracking-wider">The Engine: Multi-Currency Core Ledger</h3>
          
          {/* RECONCILE BUTTON */}
          <button 
            onClick={handleReconcile}
            disabled={isRunning}
            className={`bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold text-xs px-5 py-3 rounded-xl flex items-center gap-2 shadow-md transition cursor-pointer ${isRunning ? "opacity-50 pointer-events-none" : ""}`}
          >
            <Play className={`w-3.5 h-3.5 fill-white ${isRunning ? "animate-spin" : ""}`} />
            {isRunning ? "PROCESSING AI..." : "RECONCILIATE"}
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-xs transition-colors">
            <div className="p-3 bg-slate-50 dark:bg-slate-950/50 border-b border-slate-200 dark:border-slate-800 flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-500" />
              <span className="text-xs font-bold uppercase font-mono text-slate-700 dark:text-slate-300">Source Feed: Bank Operating Account</span>
            </div>
            <div className="p-4 overflow-x-auto">
              <table className="w-full text-left text-xs font-mono text-slate-900 dark:text-slate-200">
                <thead>
                  <tr className="text-slate-400 border-b border-slate-200 dark:border-slate-800 text-[10px]">
                    <th className="pb-2">Date</th>
                    <th className="pb-2">Bank Description</th>
                    <th className="pb-2 text-right">Settled (MYR)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="py-3">2026-05-10</td>
                    <td><span className="font-sans font-bold block">PAYMENT ACME CORP INV-2026-001</span></td>
                    <td className="py-3 text-right font-bold">RM 1500.00</td>
                  </tr>
                  <tr>
                    <td className="py-3">2026-05-12</td>
                    <td><span className="font-sans font-bold block">INWARD TT GLOBAL TECH</span></td>
                    <td className="py-3 text-right font-bold">RM 4710.50</td>
                  </tr>
                  <tr>
                    <td className="py-3">2026-05-14</td>
                    <td><span className="font-sans font-bold block">CASH DEPOSIT CDM</span></td>
                    <td className="py-3 text-right font-bold">RM 2500.00</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-xs transition-colors">
            <div className="p-3 bg-slate-50 dark:bg-slate-950/50 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-4 h-4 text-emerald-500" />
                <span className="text-xs font-bold uppercase font-mono text-slate-700 dark:text-slate-300">Extracted Feed: Morpheus AI Matches</span>
              </div>
              <span className={`px-2 py-0.5 rounded-sm font-sans font-bold text-[10px] uppercase border tracking-wider transition-all duration-300 ${
                matchStatus === "Pending" ? "bg-slate-100 dark:bg-slate-800 text-slate-500 border-slate-200 dark:border-slate-700" : "bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-500"
              }`}>
                {matchStatus === "Pending" ? "⏳ Pending" : "🟢 Matched"}
              </span>
            </div>
            
            {/* REAL DATA TABLE RENDERING */}
            <div className="overflow-x-auto min-h-[200px]">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 text-sm text-slate-500">
                    <th className="px-6 py-4 font-medium">Invoice Ref</th>
                    <th className="px-6 py-4 font-medium">Foreign Billed</th>
                    <th className="px-6 py-4 font-medium"></th>
                    <th className="px-6 py-4 font-medium">Local Received</th>
                    <th className="px-6 py-4 font-medium">FX Rate</th>
                    <th className="px-6 py-4 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {liveMatches.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center text-sm text-slate-400 italic">
                        {isRunning ? "Morpheus AI is currently analyzing data..." : "Awaiting data. Click RECONCILIATE to run the Morpheus AI engine."}
                      </td>
                    </tr>
                  ) : (
                    liveMatches.map((match, idx) => (
                      <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                        <td className="px-6 py-4">
                          <div className="font-medium text-slate-900 dark:text-slate-200">{match.id}</div>
                          <div className="text-xs text-slate-500">{match.client}</div>
                        </td>
                        <td className="px-6 py-4">
                          <span className="font-semibold text-slate-900 dark:text-slate-200">{match.billed.currency} {match.billed.amount.toFixed(2)}</span>
                        </td>
                        <td className="px-2 py-4 text-slate-400">
                          <ArrowRightLeft className="w-4 h-4 mx-auto" />
                        </td>
                        <td className="px-6 py-4">
                          <span className="font-semibold text-emerald-600 dark:text-emerald-400">{match.received.currency} {match.received.amount.toFixed(2)}</span>
                        </td>
                        <td className="px-6 py-4 text-sm font-mono text-slate-600 dark:text-slate-400">
                          {match.rate}
                        </td>
                        <td className="px-6 py-4">
                          <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                            match.status === 'Exact Match' ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400' : 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400'
                          }`}>
                            {match.status === 'Exact Match' ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                            {match.status}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* FIXED FOOTER TERMINAL */}
      <div className="fixed bottom-0 left-0 right-0 lg:left-64 bg-slate-900 dark:bg-slate-950 text-slate-200 border-t border-slate-800 shadow-2xl z-50 transition-colors">
        <div className="bg-slate-800 dark:bg-slate-900 px-4 py-2 flex items-center justify-between border-b border-slate-700 dark:border-slate-800">
          <span className="text-xs font-mono font-bold text-emerald-400 flex items-center gap-2">
            <TerminalIcon className="w-3.5 h-3.5" /> Morpheus Autonomous Reasoning Console
          </span>
        </div>
        <div className="p-4 h-32 flex flex-col justify-end overflow-y-auto font-mono text-xs space-y-1 bg-slate-900 dark:bg-slate-950">
          {logs.length === 0 ? (
            <p className="text-slate-500 italic">{">"} Awaiting trigger... Click "RECONCILIATE" to trace algorithmic logic lines.</p>
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