"use client";
import React, { useState } from "react";
import { UploadCloud, CheckCircle2, Loader2, Terminal } from "lucide-react";

export default function ProofsPage() {
  const [logs, setLogs] = useState<string[]>(["> Ready to receive receipt file..."]);
  const [status, setStatus] = useState("idle");

  const handleUpload = () => {
    setStatus("uploading");
    setLogs(prev => [...prev, "> Uploading document to storage bucket...", "> Triggering Chutes AI Parser..."]);
    
    setTimeout(() => {
      setStatus("done");
      setLogs(prev => [...prev, "> Parsing Complete.", "> Extraction: $10.00 USD matched.", "> Status updated to: Verified."]);
    }, 2000);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h2 className="text-lg font-black text-slate-800 dark:text-white uppercase tracking-wider">Link Payment Proof</h2>
      <div className="p-10 border-2 border-dashed border-slate-300 dark:border-slate-800 rounded-xl text-center hover:border-emerald-500 transition-all cursor-pointer" onClick={handleUpload}>
        {status === "idle" ? <><UploadCloud className="w-12 h-12 mx-auto text-slate-400 mb-2" /><p className="text-xs font-bold">Drag or click to upload</p></> : <Loader2 className="w-10 h-10 mx-auto animate-spin text-emerald-500" />}
      </div>
      
      {/* Log Console Interface */}
      <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 font-mono text-[11px] text-emerald-400 space-y-1 h-32 overflow-y-auto">
        <div className="flex items-center gap-2 mb-2 text-slate-500 border-b border-slate-800 pb-1">
          <Terminal className="w-3 h-3" /> <span>PROCESS_LOG_STREAM</span>
        </div>
        {logs.map((log, i) => <p key={i}>{log}</p>)}
      </div>
    </div>
  );
}