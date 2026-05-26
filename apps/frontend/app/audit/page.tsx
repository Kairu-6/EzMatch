"use client";

import React, { useState } from "react";
import { Info, ArrowRight } from "lucide-react";

const INITIAL_EXCEPTIONS = [
  { id: "ERR-902", date: "2026-05-22", scope: "EUR Conversion Corridor", amount: "RM -4.52", risk: "Low", description: "Unallocated tracking spread. Invoice calculation expected standard base rate, payment provider added custom margin.", resolved: false },
  { id: "ERR-894", date: "2026-05-19", scope: "USD Ingest Array", amount: "RM +82.40", risk: "High", description: "Severe balance breach. Ledger values match multiple document items on entry but actual bank slip lists inflated numbers.", resolved: false },
];

export default function AuditLogPage() {
  const [exceptions, setExceptions] = useState(INITIAL_EXCEPTIONS);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/40 rounded-xl p-4 flex gap-3 text-xs text-amber-800 dark:text-amber-400">
        <Info className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div><strong>Automated Variance Ledger Exceptions:</strong> This logs mathematical drift occurrences matching threshold breaches.</div>
      </div>

      <div className="space-y-4">
        {exceptions.map((exc) => (
          <div key={exc.id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-3 shadow-xs">
            <div className="flex justify-between items-start">
              <div>
                <div className="flex items-center gap-2 text-xs font-mono font-bold"><span>{exc.id}</span><span className="text-slate-400">{exc.scope}</span></div>
                <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 font-sans">{exc.description}</p>
              </div>
              <div className="text-right font-mono text-xs font-bold text-rose-500">{exc.amount}</div>
            </div>
            <div className="border-t dark:border-slate-800 pt-2 flex justify-between items-center text-[10px] text-slate-400">
              <span>RISK LAYER: <strong className="text-rose-500">{exc.risk.toUpperCase()}</strong></span>
              <button onClick={() => setExceptions(p => p.filter(x => x.id !== exc.id))} className="bg-slate-100 dark:bg-slate-800 px-2 py-1 text-slate-700 dark:text-slate-200 rounded-sm hover:bg-emerald-600 hover:text-white flex items-center gap-1 transition">Force Balance <ArrowRight className="w-3 h-3" /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}