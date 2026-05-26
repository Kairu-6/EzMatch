import React from 'react';
import { 
  UploadCloud, 
  FileText, 
  CheckCircle2, 
  AlertTriangle,
  ArrowRightLeft,
  Search,
  Globe
} from 'lucide-react';

// MOCK DATA: Tailored to the Cross-Border Challenge
const mockMatches = [
  { 
    id: 'INV-2026-001', 
    client: 'TechFlow US', 
    billed: { amount: 10.00, currency: 'USD' }, 
    received: { amount: 42.50, currency: 'MYR' },
    rate: '4.25',
    status: 'Exact Match',
    confidence: 99
  },
  { 
    id: 'INV-2026-002', 
    client: 'SG Logistics', 
    billed: { amount: 850.00, currency: 'SGD' }, 
    received: { amount: 2950.00, currency: 'MYR' },
    rate: '3.47',
    status: 'Variance Detected',
    confidence: 65
  },
  { 
    id: 'INV-2026-003', 
    client: 'EuroParts GmbH', 
    billed: { amount: 4200.00, currency: 'EUR' }, 
    received: { amount: 21420.00, currency: 'MYR' },
    rate: '5.10',
    status: 'Exact Match',
    confidence: 95
  }
];

export default function Home() {
  return (
    <div className="min-h-screen bg-slate-50 font-sans">
      
      {/* TOP NAVIGATION */}
      <nav className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <div className="flex items-center gap-2">
              <Globe className="text-indigo-600 w-8 h-8" />
              <span className="font-bold text-xl tracking-tight text-slate-900">Global Treasury Agent</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="relative">
                <Search className="w-5 h-5 text-slate-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
                <input 
                  type="text" 
                  placeholder="Search invoices..." 
                  className="pl-10 pr-4 py-2 border border-slate-200 rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 w-64"
                />
              </div>
              <div className="w-9 h-9 bg-indigo-100 rounded-full flex items-center justify-center text-indigo-700 font-bold ml-2">
                SME
              </div>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        
        {/* HEADER */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-slate-900 mb-1">Cross-Border Reconciliation</h1>
          <p className="text-slate-500">Upload payment proofs or bank statements to initiate AI matching.</p>
        </div>

        {/* UPLOAD DROPZONE */}
        <div className="mb-8 bg-white border-2 border-dashed border-indigo-200 rounded-2xl p-10 flex flex-col items-center justify-center text-center hover:bg-indigo-50/50 transition-colors cursor-pointer group">
          <div className="w-16 h-16 bg-indigo-100 text-indigo-600 rounded-full flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
            <UploadCloud className="w-8 h-8" />
          </div>
          <h3 className="text-lg font-semibold text-slate-900 mb-1">Drag & drop your files here</h3>
          <p className="text-slate-500 text-sm max-w-md">
            Supports PDF, JPG, PNG (Payment Proofs) and Excel/CSV (Bank Statements). The AI agent will automatically extract currencies and map them.
          </p>
          <button className="mt-6 bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2.5 rounded-lg font-medium transition-colors shadow-sm">
            Browse Files
          </button>
        </div>

        {/* RECONCILIATION TABLE */}
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
          <div className="px-6 py-5 border-b border-slate-200 flex justify-between items-center bg-slate-50/50">
            <h2 className="text-lg font-semibold text-slate-900">Recent AI Matches</h2>
            <div className="flex gap-2">
              <span className="bg-white border border-slate-200 text-slate-600 text-xs font-medium px-3 py-1 rounded-md">
                Local Currency: MYR
              </span>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-white border-b border-slate-200 text-sm text-slate-500">
                  <th className="px-6 py-4 font-medium">Invoice Ref</th>
                  <th className="px-6 py-4 font-medium">Foreign Billed</th>
                  <th className="px-6 py-4 font-medium"></th>
                  <th className="px-6 py-4 font-medium">Local Received</th>
                  <th className="px-6 py-4 font-medium">Est. Rate</th>
                  <th className="px-6 py-4 font-medium">Match Status</th>
                  <th className="px-6 py-4 font-medium text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {mockMatches.map((match) => (
                  <tr key={match.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-medium text-slate-900">{match.id}</div>
                      <div className="text-xs text-slate-500">{match.client}</div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-semibold text-slate-900">{match.billed.currency} {match.billed.amount.toFixed(2)}</span>
                    </td>
                    <td className="px-2 py-4 text-slate-400">
                      <ArrowRightLeft className="w-4 h-4 mx-auto" />
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-semibold text-indigo-700">{match.received.currency} {match.received.amount.toFixed(2)}</span>
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-600">
                      {match.rate}
                    </td>
                    <td className="px-6 py-4">
                      <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                        match.status === 'Exact Match' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'
                      }`}>
                        {match.status === 'Exact Match' ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
                        {match.status}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button className="text-indigo-600 hover:text-indigo-800 text-sm font-medium">
                        {match.status === 'Exact Match' ? 'Log to Ledger' : 'Resolve'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}