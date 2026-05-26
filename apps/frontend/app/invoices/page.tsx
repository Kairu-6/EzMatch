"use client";

import React, { useState, useRef, useEffect } from "react";
import { UploadCloud, CheckCircle2, Loader2, Terminal, FileText } from "lucide-react";
import { createClient } from "@supabase/supabase-js";
// THE HACKATHON OVERRIDE
const SUPABASE_URL = "https://yipmoeioxawqrsbtmkqb.supabase.co"
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlpcG1vZWlveGF3cXJzYnRta3FiIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTYwNTQzNywiZXhwIjoyMDk1MTgxNDM3fQ.BZqrTxSMwuRL1MOelSASCmwF1VuuY-Wco5M_AAaZ_UY";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

export default function InvoicesPage() {
  const [logs, setLogs] = useState<string[]>(["> Ready to receive invoice document..."]);
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const [pendingInvoices, setPendingInvoices] = useState<any[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // FETCH UNMATCHED INVOICES ON LOAD
// FETCH UNMATCHED INVOICES ON LOAD
const fetchPendingInvoices = async () => {
    try {
      const { data, error } = await supabase
        .from('invoice')
        .select('*')
        .eq('status', 'unmatched');
        
      if (error) throw error;
      if (data) setPendingInvoices(data);
    } catch (err) {
      console.error("Error fetching invoices:", err);
    }
  };

  useEffect(() => {
    fetchPendingInvoices();
  }, []);

  const handleUpload = async (file: File) => {
    setStatus("uploading");
    setLogs(prev => [
      ...prev, 
      `> Captured file: ${file.name}`,
      "> Uploading document to Python backend...", 
      "> Triggering Morpheus AI Extraction..."
    ]);
    
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/upload/invoice", {
        method: "POST",
        body: formData
      });

      if (response.ok) {
        setStatus("done");
        setLogs(prev => [
          ...prev, 
          "> AI Extraction Complete.", 
          "> Database record persisted and updated.", 
          "> Status updated to: Pending Reconciliation."
        ]);
        
        // REFRESH THE TABLE AFTER SUCCESSFUL UPLOAD
        setTimeout(() => {
          fetchPendingInvoices();
        }, 1500);

      } else {
        throw new Error("Server rejected file");
      }
    } catch (error) {
      console.error("Upload failed:", error);
      setStatus("error");
      setLogs(prev => [
        ...prev,
        "> [ERROR] Connection failed.",
        "> Is the FastAPI server running on port 8000?"
      ]);
      
      setTimeout(() => setStatus("idle"), 4000);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      
      {/* HEADER */}
      <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-4">
        <h2 className="text-xl font-black text-slate-800 dark:text-white uppercase tracking-wider flex items-center gap-2">
          <FileText className="text-emerald-500" />
          Invoice Management
        </h2>
      </div>

      {/* DROPZONE INTERFACE */}
      <div 
        className={`p-10 border-2 border-dashed rounded-xl text-center transition-all cursor-pointer flex flex-col items-center justify-center min-h-[160px]
          ${status === 'uploading' ? 'border-emerald-500 bg-emerald-50/10 dark:bg-emerald-950/20' : 'border-slate-300 dark:border-slate-800 hover:border-emerald-500 bg-white dark:bg-slate-900'}
        `} 
        onClick={() => status === "idle" && fileInputRef.current?.click()}
      >
        <input 
          type="file" 
          ref={fileInputRef} 
          onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])} 
          accept=".pdf, .jpg, .png, .jpeg" 
          className="hidden" 
        />
        
        {status === "idle" && (
          <>
            <UploadCloud className="w-12 h-12 mx-auto text-slate-400 mb-2" />
            <p className="text-sm font-bold text-slate-600 dark:text-slate-300">Drag or click to upload invoice</p>
            <p className="text-xs text-slate-400 mt-1">Supports PDF, JPG, PNG</p>
          </>
        )}
        
        {status === "uploading" && (
          <>
            <Loader2 className="w-10 h-10 mx-auto animate-spin text-emerald-500 mb-2" />
            <p className="text-sm font-bold font-mono text-emerald-600 dark:text-emerald-400">Processing via AI Engine...</p>
          </>
        )}

        {status === "done" && (
          <>
            <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-500 mb-2" />
            <p className="text-sm font-bold font-mono text-emerald-600 dark:text-emerald-400">Invoice Parsed Successfully</p>
          </>
        )}

        {status === "error" && (
          <>
            <p className="text-sm font-bold text-red-500">Upload Failed. Check logs.</p>
          </>
        )}
      </div>
      
      {/* LOG CONSOLE INTERFACE */}
      <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 font-mono text-xs text-emerald-400 space-y-1 h-32 overflow-y-auto">
        <div className="flex items-center gap-2 mb-2 text-slate-500 border-b border-slate-800 pb-1">
          <Terminal className="w-3 h-3" /> <span>PROCESS_LOG_STREAM</span>
        </div>
        {logs.map((log, i) => (
          <p key={i} className={log.includes("ERROR") ? "text-red-400" : ""}>{log}</p>
        ))}
      </div>

      {/* DYNAMIC PENDING LEDGER */}
      <div className="mt-8 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden bg-white dark:bg-slate-950 shadow-sm">
        <div className="bg-slate-50 dark:bg-slate-900 px-5 py-4 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center">
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200 uppercase tracking-wider">Pending Accounts Receivable</h3>
          <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50/50 dark:bg-slate-900/50 text-slate-500 text-xs uppercase">
              <tr>
                <th className="px-5 py-3 font-semibold">Invoice #</th>
                <th className="px-5 py-3 font-semibold">Counterparty</th>
                <th className="px-5 py-3 text-right font-semibold">Amount</th>
                <th className="px-5 py-3 text-center font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/50">
              
              {pendingInvoices.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-5 py-8 text-center text-slate-500 italic">
                    No pending invoices found.
                  </td>
                </tr>
              ) : (
                pendingInvoices.map((inv) => (
                  <tr key={inv.invoice_id} className="hover:bg-slate-50 dark:hover:bg-slate-900/50 transition-colors">
                    <td className="px-5 py-4 font-mono text-emerald-600 dark:text-emerald-400 font-medium">
                      {inv.invoice_number || 'Processing...'}
                    </td>
                    <td className="px-5 py-4 font-medium text-slate-700 dark:text-slate-300">
                      {inv.counterparty_name || 'Unknown Client'}
                    </td>
                    <td className="px-5 py-4 text-right font-mono font-medium text-slate-700 dark:text-slate-300">
                      {inv.invoice_currency} {inv.amount}
                    </td>
                    <td className="px-5 py-4 text-center">
                      <span className="px-2.5 py-1 bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400 rounded text-[10px] font-black uppercase tracking-widest border border-amber-200 dark:border-amber-800/50">
                        {inv.status.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                ))
              )}

            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}