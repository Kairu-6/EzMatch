"use client";
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Landmark, Loader2, ArrowRight } from "lucide-react";

export default function SignUpPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSignUp = (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    
    // Simulate setup delay
    setTimeout(() => {
      sessionStorage.setItem("isSignedUp", "true");
      setSuccess(true);
      
      // Delay navigation slightly so user sees the success message
      setTimeout(() => {
        router.push("/");
      }, 1500);
    }, 1500);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 p-4 font-sans">
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl">
        <div className="text-center mb-6">
          <div className="inline-flex bg-emerald-500 p-3 rounded-xl mb-4">
            <Landmark className="w-6 h-6 text-slate-950" />
          </div>
          <h2 className="text-xl font-black text-white uppercase">Initialize Node</h2>
        </div>

        {success ? (
          <div className="text-center py-4 text-emerald-500 font-bold animate-pulse">
            SYSTEM INITIALIZED SUCCESSFULLY!
          </div>
        ) : (
          <form onSubmit={handleSignUp} className="space-y-4 text-xs font-mono">
            <input required placeholder="Company Name" className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-white focus:border-emerald-500 outline-none" />
            <input required placeholder="Registration Number" className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-white focus:border-emerald-500 outline-none" />
            <input type="email" required placeholder="Corporate Email" className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-white focus:border-emerald-500 outline-none" />
            <button className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3 rounded-lg font-bold flex items-center justify-center gap-2">
              {isLoading ? <Loader2 className="animate-spin" /> : <>INITIALIZE SYSTEM <ArrowRight className="w-4 h-4" /></>}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}