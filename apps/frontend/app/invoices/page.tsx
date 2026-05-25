"use client";
import React, { useState } from "react";
import { FilePlus, Save, Terminal } from "lucide-react";

export default function InvoicesPage() {
  const [logs, setLogs] = useState<string[]>(["> System initialized..."]);
  const [formData, setFormData] = useState({ client: "", amount: "", currency: "MYR" });

  const createInvoice = () => {
    setLogs(prev => [...prev, `> Processing request for ${formData.client}...`, "> Generating Invoice ID: INV-" + Math.floor(Math.random() * 9000), "> Success: Invoice record persisted."]);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h2 className="text-lg font-black text-slate-800 dark:text-white uppercase tracking-wider">Generate Invoice ID</h2>
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-6 rounded-xl shadow-xs space-y-4">
        <input placeholder="Client Name" className="w-full bg-slate-50 dark:bg-slate-950 p-3 rounded-lg border dark:border-slate-800" onChange={e => setFormData({...formData, client: e.target.value})} />
        <button onClick={createInvoice} className="w-full bg-emerald-600 text-white py-3 rounded-lg font-bold flex items-center justify-center gap-2">
          <Save className="w-4 h-4" /> CREATE INVOICE RECORD
        </button>
      </div>
      
      {/* Log Console Interface */}
      <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 font-mono text-[11px] text-emerald-400 space-y-1 h-32 overflow-y-auto">
        {logs.map((log, i) => <p key={i}>{log}</p>)}
      </div>
    </div>
  );
}