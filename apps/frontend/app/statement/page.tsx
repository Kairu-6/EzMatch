"use client";

import React, { useState, useRef, useEffect } from "react";
import { FileSpreadsheet, UploadCloud, Loader2 } from "lucide-react";

const INITIAL_STATEMENTS = [
  { id: "TXN-8801", date: "2026-05-25", reference: "STRIPE-TRANSFER-77A", description: "Payout Settlement Corridor Clear", currency: "USD", foreignAmount: 10.00, landedMYR: 42.50, status: "Reconciled" },
  { id: "TXN-8802", date: "2026-05-24", reference: "INV-2026-088", description: "SME Software Subscription", currency: "USD", foreignAmount: 150.00, landedMYR: 631.50, status: "Reconciled" },
  { id: "TXN-8803", date: "2026-05-24", reference: "MY-BANK-REF-992", description: "Inter-Account Treasury Wire Pool", currency: "MYR", foreignAmount: 5000.00, landedMYR: 5000.00, status: "Pending" },
];

export default function BankStatementsPage() {
  const [statements, setStatements] = useState(INITIAL_STATEMENTS);
  const [isUploading, setIsUploading] = useState(false);
  const [isAutoMatching, setIsAutoMatching] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Simulation effect to match the "Morpheus Autonomous Engine" timeline from Screen 1
  const uploadCsv = (name: string) => {
    setIsUploading(true);
    setTimeout(() => {
      const newTxnId = `TXN-${Math.floor(1000 + Math.random() * 9000)}`;
      
      // 1. Ingest the raw file row as "Pending" (Requirement 3: The Status Badge)
      setStatements(prev => [{
        id: newTxnId,
        date: "2026-05-26",
        reference: "BULK-CSV-IMPORT-99X",
        description: `Ingested Feed (${name})`,
        currency: "USD",
        foreignAmount: 42.00,
        landedMYR: 176.82,
        status: "Pending"
      }, ...prev]);
      setIsUploading(false);

      // 2. Trigger automated background Morpheus reconciliation right after upload!
      setIsAutoMatching(true);
      setTimeout(() => {
        setStatements(currentStatements => 
          currentStatements.map(txn => 
            txn.id === newTxnId || txn.status === "Pending" 
              ? { ...txn, status: "Reconciled" } 
              : txn
          )
        );
        setIsAutoMatching(false);
      }, 3000); // After 3 seconds, flip the badge to Matched/Reconciled!

    }, 1200);
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="border-b border-slate-200 dark:border-slate-800 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h2 className="text-xl font-black uppercase tracking-wide text-slate-800 dark:text-white flex items-center gap-2">
          <FileSpreadsheet className="w-5 h-5 text-emerald-500" /> Ingested Cash Flow Records
        </h2>
        {isAutoMatching && (
          <span className="text-xs font-mono bg-emerald-950/40 text-emerald-400 border border-emerald-800/60 px-3 py-1 rounded-md animate-pulse">
            🤖 Morpheus Agent matching records live...
          </span>
        )}
      </div>

      {/* DROPZONE INTERFACE */}
      <div 
        onClick={() => fileInputRef.current?.click()}
        className="border-2 border-dashed rounded-xl p-6 text-center transition-all cursor-pointer bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-800 hover:border-slate-400 min-h-[130px] flex flex-col items-center justify-center"
      >
        <input type="file" ref={fileInputRef} onChange={(e) => e.target.files?.[0] && uploadCsv(e.target.files[0].name)} accept=".csv" className="hidden" />
        {isUploading ? (
          <div className="space-y-2 text-center">
            <Loader2 className="w-6 h-6 text-emerald-500 animate-spin mx-auto" />
            <p className="text-xs font-mono font-bold">Parsing CSV Pipeline structure...</p>
          </div>
        ) : (
          <div className="space-y-1">
            <UploadCloud className="w-6 h-6 text-slate-400 mx-auto" />
            <p className="text-xs font-bold">Drag or click to parse local statement <span className="text-emerald-500">.csv</span> layout sets</p>
          </div>
        )}
      </div>

      {/* DENSE FINANCE LEDGER TABLE */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-xs">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-slate-50 dark:bg-slate-950 border-b dark:border-slate-800 font-bold text-[10px]">
            <tr>
              <th className="p-3">Value Date</th>
              <th className="p-3">Transaction ID</th>
              <th className="p-3">Reference Description</th>
              <th className="p-3 text-right">Foreign Value</th>
              <th className="p-3 text-right">Settled (MYR)</th>
              <th className="p-3 text-center">Engine Match</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {statements.map((txn) => (
              <tr key={txn.id} className="hover:bg-slate-50/40 dark:hover:bg-slate-950/20">
                <td className="p-3 text-slate-500">{txn.date}</td>
                <td className="p-3 font-bold text-slate-400">{txn.id}</td>
                <td className="p-3 font-sans font-bold">{txn.description}</td>
                <td className="p-3 text-right font-bold">{txn.currency} {txn.foreignAmount.toFixed(2)}</td>
                <td className="p-3 text-right font-bold text-emerald-600">RM {txn.landedMYR.toFixed(2)}</td>
                <td className="p-3 text-center">
                  {/* STEP 3 COMPLIANCE: TAILWIND BADGE BINDING */}
                  <span className={`px-2 py-0.5 rounded-sm text-[9px] font-sans border uppercase font-bold transition-all duration-300 ${
                    txn.status === "Reconciled" 
                      ? "bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-900/40" 
                      : "bg-amber-50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-900/40 animate-pulse"
                  }`}>
                    {txn.status === "Reconciled" ? "🟢 Reconciled" : "🟡 Pending"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}