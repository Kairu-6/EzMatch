"use client";

import React, { useState, useRef } from "react";
import { UploadCloud, CheckCircle2, Loader2, Terminal } from "lucide-react";

export default function ProofsPage() {
  const [logs, setLogs] = useState<string[]>(["> Ready to receive receipt file..."]);
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (file: File) => {
    setStatus("uploading");
    setLogs(prev => [
      ...prev, 
      `> Captured file: ${file.name}`,
      "> Uploading document to Python backend...", 
      "> Triggering Chutes AI Parser..."
    ]);
    
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/upload/payment_proof", {
        method: "POST",
        body: formData
      });

      if (response.ok) {
        setStatus("done");
        setLogs(prev => [
          ...prev, 
          "> Parsing Complete.", 
          "> Backend accepted payment proof.", 
          "> Status updated to: Verified."
        ]);
        
        // Optional: Reset back to idle after a few seconds to upload another
        // setTimeout(() => setStatus("idle"), 5000); 
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
      
      // Revert back to idle after a few seconds so you can try again
      setTimeout(() => setStatus("idle"), 4000);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h2 className="text-lg font-black text-slate-800 dark:text-white uppercase tracking-wider">Link Payment Proof</h2>
      
      {/* DROPZONE INTERFACE */}
      <div 
        className={`p-10 border-2 border-dashed rounded-xl text-center transition-all cursor-pointer flex flex-col items-center justify-center min-h-[160px]
          ${status === 'uploading' ? 'border-emerald-500 bg-emerald-50/10 dark:bg-emerald-950/20' : 'border-slate-300 dark:border-slate-800 hover:border-emerald-500 bg-white dark:bg-slate-900'}
        `} 
        onClick={() => status === "idle" && fileInputRef.current?.click()}
      >
        {/* The actual hidden input field */}
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
            <p className="text-xs font-bold text-slate-600 dark:text-slate-300">Drag or click to upload</p>
            <p className="text-[10px] text-slate-400 mt-1">Supports PDF, JPG, PNG</p>
          </>
        )}
        
        {status === "uploading" && (
          <>
            <Loader2 className="w-10 h-10 mx-auto animate-spin text-emerald-500 mb-2" />
            <p className="text-xs font-bold font-mono text-emerald-600 dark:text-emerald-400">Processing via Chutes AI...</p>
          </>
        )}

        {status === "done" && (
          <>
            <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-500 mb-2" />
            <p className="text-xs font-bold font-mono text-emerald-600 dark:text-emerald-400">Proof Verified Successfully</p>
          </>
        )}

        {status === "error" && (
          <>
            <p className="text-xs font-bold text-red-500">Upload Failed. Check logs.</p>
          </>
        )}
      </div>
      
      {/* LOG CONSOLE INTERFACE */}
      <div className="bg-slate-950 border border-slate-800 rounded-lg p-4 font-mono text-[11px] text-emerald-400 space-y-1 h-32 overflow-y-auto">
        <div className="flex items-center gap-2 mb-2 text-slate-500 border-b border-slate-800 pb-1">
          <Terminal className="w-3 h-3" /> <span>PROCESS_LOG_STREAM</span>
        </div>
        {logs.map((log, i) => (
          <p key={i} className={log.includes("ERROR") ? "text-red-400" : ""}>{log}</p>
        ))}
      </div>
    </div>
  );
}