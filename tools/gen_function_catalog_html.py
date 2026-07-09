"""
Builds catalog.html from backend_functions.json + frontend_functions.json.
stdlib-only. ponytail: plain string templating, no Jinja — this runs once,
a templating engine would be a dependency for a one-shot report.
"""
import html
import json
import os

SCRATCH = os.path.dirname(__file__)
DATE = "2026-07-09"  # hardcoded per spec, do not call datetime.now()

backend = json.load(open(os.path.join(SCRATCH, "backend_functions.json"), encoding="utf-8"))
frontend = json.load(open(os.path.join(SCRATCH, "frontend_functions.json"), encoding="utf-8"))

by_module = {}
for e in backend:
    by_module.setdefault(e["module"], []).append(e)
for m in by_module:
    by_module[m].sort(key=lambda x: x["lineno"])

fe_by_file = {}
for e in frontend["entries"]:
    fe_by_file.setdefault(e["file"], []).append(e)


def esc(s):
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def qual_short(qual):
    """'agent/memory.py::AgentMemory.persist' -> 'agent/memory.AgentMemory.persist'"""
    return qual.replace(".py::", ".")


def backend_depends(e):
    parts = list(e.get("depends_ext", []))
    for t in e.get("tables_read", []):
        parts.append(f"reads: {t}")
    for q in e.get("depends_intra", []):
        parts.append(qual_short(q))
    return parts


def backend_affects(e):
    parts = []
    for t in e.get("tables_write", []):
        parts.append(f"writes: {t}")
    for q in e.get("called_by", []):
        parts.append(f"called by {qual_short(q)}")
    if not parts:
        parts.append("—")
    return parts


def sig_html(e):
    sig = e["signature"]
    if e.get("class"):
        # drop the leading "def "/"async def " so it reads "ClassName.method(...)" not "ClassName.def method(...)"
        sig = sig.replace("async def ", "async ", 1) if sig.startswith("async def ") else sig.replace("def ", "", 1)
        sig = f"{e['class']}.{sig}"
    return esc(sig)


def tag_html(e):
    tags = list(e.get("tags", []))
    if e.get("endpoint"):
        tags = [t for t in tags if t != "endpoint"]
        return " ".join([f'<span class="tag tag-endpoint">{esc(e["endpoint"])}</span>'] +
                         [f'<span class="tag">{esc(t)}</span>' for t in tags])
    return " ".join(f'<span class="tag">{esc(t)}</span>' for t in tags) or "&mdash;"


def row_html(e):
    dep = "<br>".join(esc(d) for d in backend_depends(e)) or "&mdash;"
    aff = "<br>".join(esc(a) for a in backend_affects(e))
    return f"""<tr>
      <td class="mono">{sig_html(e)}</td>
      <td>{esc(e['description'])}</td>
      <td class="muted">{dep}</td>
      <td class="muted">{aff}</td>
      <td class="tagcell">{tag_html(e)}</td>
    </tr>"""


def table_html(entries):
    rows = "\n".join(row_html(e) for e in entries)
    return f"""<table class="fntable">
      <colgroup><col style="width:24%"><col style="width:24%"><col style="width:19%"><col style="width:19%"><col style="width:14%"></colgroup>
      <thead><tr><th>Function (signature)</th><th>Description</th><th>Depends on</th><th>Affects</th><th>Tags</th></tr></thead>
      <tbody>
      {rows}
      </tbody>
    </table>"""


def file_block(module_path, role, entries, heading_override=None):
    if not entries:
        body = '<p class="empty-note">No top-level functions extracted (file has no module-level def).</p>'
    else:
        body = table_html(entries)
    heading = heading_override or module_path
    return f"""<div class="filecard">
      <h3>{esc(heading)} <span class="filerole">— {esc(role)}</span></h3>
      {body}
    </div>"""


def fe_row_html(e):
    dep = "<br>".join(esc(d) for d in e.get("depends_on", [])) or "&mdash;"
    aff = "<br>".join(esc(a) for a in e.get("affects", [])) or "&mdash;"
    sig = f"{e['name']} {e.get('signature_note','')}".strip()
    return f"""<tr>
      <td class="mono">{esc(sig)}</td>
      <td>{esc(e['description'])}</td>
      <td class="muted">{dep}</td>
      <td class="muted">{aff}</td>
      <td class="tagcell"><span class="tag">{esc(e.get('kind',''))}</span></td>
    </tr>"""


def fe_table_html(entries):
    rows = "\n".join(fe_row_html(e) for e in entries)
    return f"""<table class="fntable">
      <colgroup><col style="width:22%"><col style="width:27%"><col style="width:19%"><col style="width:19%"><col style="width:13%"></colgroup>
      <thead><tr><th>Function (signature)</th><th>Description</th><th>Depends on</th><th>Affects</th><th>Kind</th></tr></thead>
      <tbody>
      {rows}
      </tbody>
    </table>"""


def fe_file_block(file_path, role):
    entries = fe_by_file.get(file_path, [])
    body = fe_table_html(entries) if entries else '<p class="empty-note">No entries.</p>'
    return f"""<div class="filecard">
      <h3>{esc(file_path)} <span class="filerole">— {esc(role)}</span></h3>
      {body}
    </div>"""


# ---------- Sections ----------

def section(num, title, body, page_break=True):
    cls = "layer-section" + (" pagebreak" if page_break else "")
    return f'<section class="{cls}"><h2>{num}. {esc(title)}</h2>{body}</section>'


BACKEND_ROLES = {
    "main.py": "FastAPI app entrypoint — health, /api/reconcile, /api/job-status; picks agent vs legacy engine.",
    "server.py": "Upload endpoints (statement/invoice/payment proof) + MyInvois/accounting/bank-feed sync routes.",
    "auth.py": "JWT auth dependency — resolves sme_id from the Supabase session for every protected route.",
    "orchestrator.py": "Core recon primitives (fetch/write/log) shared by both engines, plus the legacy linear pipeline.",
    "forex_api.py": "FX rate resolution — cache-first against `exchange_rate`, Frankfurter fallback.",
    "data_contracts.py": "Pydantic v2 schemas validating parsed invoice/statement/proof data before it's trusted.",
    "agent/runner.py": "Agentic reconciliation loop — the default engine (USE_AGENT=true): tool calls, verify, finalize.",
    "agent/tools.py": "Tool surface exposed to the LLM (list_invoices/list_transactions/propose_match/etc.) + tool-schema builders.",
    "agent/llm.py": "Model-agnostic chat step wrapper around Morpheus (OpenAI-compatible) for the agent loop.",
    "agent/memory.py": "Per-job conversation memory + cross-job learned memory (accepted/rejected patterns).",
    "agent/gate.py": "Confidence-gate decision: auto-accept vs pending_review threshold.",
    "agent/verifier.py": "Post-hoc pass catching invoices the agent missed / verifying proposed matches.",
    "agent/anomaly.py": "Heuristic anomaly scans: duplicate invoices, beneficiary mismatch, bank-detail change, amount outliers.",
    "agent/prompts.py": "System prompt builder for the agent loop.",
    "agent/__init__.py": "Package marker — no functions.",
    "statement_parser.py": "CSV/XLSX bank statement parsing into `bank_transaction` rows (account-scoped dedup).",
    "invoice_parser.py": "PDF/image invoice parsing via PyMuPDF/Tesseract + Morpheus structuring into `invoice`.",
    "proof_parser.py": "PDF/image payment-proof parsing into `payment_proof`.",
    "parser_llm.py": "Shared Morpheus text->JSON structuring call used by invoice/proof parsers.",
    "myinvois_client.py": "LHDN MyInvois OAuth2 client + UBL document mapping into `invoice` rows.",
    "accounting_client.py": "Mock AutoCount/SQL Account connector — fixture invoices mapped to `invoice` rows.",
    "bank_feed_client.py": "Finverse open-banking client — Link session, token exchange, transaction pull.",
    "bankfeed_state.py": "HMAC-signed `state` token carrying sme_id across the JWT-less OAuth redirect.",
    "seed_data.py": "Deterministic (uuid5) demo-data builder — 4 tenants, accounts, history, current docs.",
    "seed_demo.py": "Destructive+idempotent reseed: wipes tenant data, provisions the 4 demo Supabase Auth logins.",
    "seed_files.py": "Regenerates the `test_files/` upload fixtures + `sme_infos` manifest.",
    "test_reference_match.py": "Self-check for the DuitNow/FPX exact-reference recon pre-pass.",
    "test_myinvois_map.py": "Self-check script for MyInvois UBL->invoice mapping (no top-level functions — runs inline).",
    "test_accounting_map.py": "Self-check script for accounting-connector mapping (no top-level functions — runs inline).",
}

FE_ROLES = frontend["file_roles"]

html_parts = []

# ---- Cover ----
layer_defs_backend = [
    ("1", "API layer", ["main.py", "server.py", "auth.py"]),
    ("2", "Reconciliation engine", ["orchestrator.py", "forex_api.py", "data_contracts.py"]),
    ("3", "Agent engine", ["agent/runner.py", "agent/tools.py", "agent/llm.py", "agent/memory.py",
                            "agent/gate.py", "agent/verifier.py", "agent/anomaly.py", "agent/prompts.py",
                            "agent/__init__.py"]),
    ("4", "Parsers", ["statement_parser.py", "invoice_parser.py", "proof_parser.py", "parser_llm.py"]),
    ("5", "Integrations", ["myinvois_client.py", "accounting_client.py", "bank_feed_client.py", "bankfeed_state.py"]),
    ("6", "Seeds & tests", ["seed_data.py", "seed_demo.py", "seed_files.py", "test_reference_match.py",
                             "test_myinvois_map.py", "test_accounting_map.py"]),
]
layer_defs_frontend = [
    ("7", "Pages", ["page.tsx", "layout.tsx", "login/page.tsx", "signup/layout.tsx", "signup/page.tsx",
                     "uploads/page.tsx", "audit/page.tsx", "history/page.tsx", "settings/page.tsx"]),
    ("8", "Components", ["components/DashboardPage.tsx", "components/AppShell.tsx",
                          "components/LandingPage.tsx", "components/MeshBackground.tsx"]),
    ("9", "UI kit", sorted(f for f in FE_ROLES if f.startswith("components/ui/"))),
    ("10", "lib & contexts", ["lib/AuthContext.tsx", "lib/matchActions.ts", "lib/supabaseClient.ts", "ThemeContext.tsx"]),
]

summary_rows = []
total_backend = 0
total_frontend = 0
for num, title, files in layer_defs_backend:
    for f in files:
        n = len(by_module.get(f, []))
        total_backend += n
        summary_rows.append((f"{num}. {title}", f, n))
for num, title, files in layer_defs_frontend:
    for f in files:
        n = len(fe_by_file.get(f, []))
        total_frontend += n
        summary_rows.append((f"{num}. {title}", f, n))

summary_html = "\n".join(
    f'<tr><td>{esc(layer)}</td><td class="mono">{esc(f)}</td><td class="num">{n}</td></tr>'
    for layer, f, n in summary_rows
)

cover = f"""
<section class="cover">
  <div class="cover-inner">
    <p class="eyebrow">TreasuryFlow AI &mdash; internal reference</p>
    <h1>Function Catalog</h1>
    <p class="cover-date">Generated {DATE}</p>
    <p class="cover-sub">A one-page-per-file index of every function in the codebase: what it is,
    what it depends on, and what it affects. Not deep documentation &mdash; a map.</p>
    <div class="cover-stats">
      <div class="stat"><div class="stat-num">{total_backend}</div><div class="stat-label">backend functions</div></div>
      <div class="stat"><div class="stat-num">{total_frontend}</div><div class="stat-label">frontend entries</div></div>
      <div class="stat"><div class="stat-num">{len(by_module)+len(FE_ROLES)}</div><div class="stat-label">files covered</div></div>
    </div>
  </div>

  <table class="summary-table">
    <thead><tr><th>Layer</th><th>File</th><th class="num">Count</th></tr></thead>
    <tbody>{summary_html}</tbody>
  </table>

  <div class="legend">
    <h3>Legend</h3>
    <dl>
      <dt>Signature</dt><dd>Reconstructed from source: name, parameters (with defaults/annotations where present), return type. Monospace.</dd>
      <dt>Description</dt><dd>First line of the docstring; if none, a short name-based hint in parentheses &mdash; not invented behavior.</dd>
      <dt>Depends on</dt><dd>What this function calls (intra-repo functions, external services/libs) and DB tables/endpoints it reads.</dd>
      <dt>Affects</dt><dd>Who calls this function, and DB tables/endpoints/UI state it writes or drives.</dd>
      <dt>Tags</dt><dd><code>endpoint</code> = FastAPI route (method + path shown). <code>legacy</code> = superseded by the agent engine but still present. <code>mock-only</code> = the real (non-fixture) code path raises <code>NotImplementedError</code>.</dd>
    </dl>
  </div>
</section>
"""
html_parts.append(cover)

# ---- Backend sections ----
def orch_split():
    entries = by_module.get("orchestrator.py", [])
    real = [e for e in entries if "legacy" not in e.get("tags", [])]
    legacy = [e for e in entries if "legacy" in e.get("tags", [])]
    body = file_block("orchestrator.py", BACKEND_ROLES["orchestrator.py"] + " (real/shared functions)", real,
                       heading_override="orchestrator.py — real / shared")
    body += file_block("orchestrator.py", "Superseded by the agent engine (agent/runner.py) but kept for USE_AGENT=false fallback.", legacy,
                        heading_override="orchestrator.py — legacy (linear pipeline)")
    return body

section_bodies = {
    "1": "".join(file_block(f, BACKEND_ROLES.get(f, ""), by_module.get(f, [])) for f in layer_defs_backend[0][2]),
    "2": orch_split() + file_block("forex_api.py", BACKEND_ROLES["forex_api.py"], by_module.get("forex_api.py", []))
         + file_block("data_contracts.py", BACKEND_ROLES["data_contracts.py"], by_module.get("data_contracts.py", [])),
    "3": "".join(file_block(f, BACKEND_ROLES.get(f, ""), by_module.get(f, [])) for f in layer_defs_backend[2][2]),
    "4": "".join(file_block(f, BACKEND_ROLES.get(f, ""), by_module.get(f, [])) for f in layer_defs_backend[3][2]),
    "5": "".join(file_block(f, BACKEND_ROLES.get(f, ""), by_module.get(f, [])) for f in layer_defs_backend[4][2]),
    "6": "".join(file_block(f, BACKEND_ROLES.get(f, ""), by_module.get(f, [])) for f in layer_defs_backend[5][2]),
}

titles = {
    "1": "API layer", "2": "Reconciliation engine", "3": "Agent engine",
    "4": "Parsers", "5": "Integrations", "6": "Seeds & tests",
}
for num in ["1", "2", "3", "4", "5", "6"]:
    html_parts.append(section(num, titles[num], section_bodies[num]))

# ---- Frontend sections ----
fe_section_bodies = {
    "7": "".join(fe_file_block(f, FE_ROLES.get(f, "")) for f in layer_defs_frontend[0][2]),
    "8": "".join(fe_file_block(f, FE_ROLES.get(f, "")) for f in layer_defs_frontend[1][2]),
    "9": "".join(fe_file_block(f, FE_ROLES.get(f, "")) for f in layer_defs_frontend[2][2]),
    "10": "".join(fe_file_block(f, FE_ROLES.get(f, "")) for f in layer_defs_frontend[3][2]),
}
fe_titles = {"7": "Pages", "8": "Components", "9": "UI kit", "10": "lib & contexts"}
for num in ["7", "8", "9", "10"]:
    html_parts.append(section(num, fe_titles[num], fe_section_bodies[num]))

BODY = "\n".join(html_parts)

CSS = """
:root{
  --ink:#1a1d23; --muted:#5b6270; --line:#d9dce1; --accent:#2f5d8a; --accent-bg:#eef3f8;
  --tag-bg:#e7ebf0; --tag-endpoint-bg:#e5f0e9; --tag-endpoint-ink:#20613f;
  --legacy-bg:#f6efe3; --legacy-ink:#8a5a1c;
}
*{box-sizing:border-box;}
body{
  font-family:"Segoe UI","Helvetica Neue",Arial,sans-serif; font-size:10px; line-height:1.45;
  color:var(--ink); background:#fff; margin:0;
}
h1,h2,h3{font-family:inherit; color:var(--ink); margin:0;}
code{font-family:"Consolas","SFMono-Regular",Menlo,monospace; background:var(--tag-bg); padding:1px 4px; border-radius:3px;}

/* ---- Cover ---- */
.cover{padding:0 0 8mm 0;}
.cover-inner{padding-bottom:6mm; border-bottom:2px solid var(--accent);}
.eyebrow{color:var(--accent); font-weight:600; letter-spacing:.04em; text-transform:uppercase; font-size:9px; margin:0 0 4px 0;}
.cover h1{font-size:28px; font-weight:700; margin-bottom:4px;}
.cover-date{color:var(--muted); font-size:11px; margin:2px 0 8px 0;}
.cover-sub{color:var(--muted); max-width:70%; font-size:10.5px;}
.cover-stats{display:flex; gap:10mm; margin-top:6mm;}
.stat-num{font-size:22px; font-weight:700; color:var(--accent);}
.stat-label{color:var(--muted); font-size:9px; text-transform:uppercase; letter-spacing:.03em;}

.summary-table{width:100%; border-collapse:collapse; margin:6mm 0; font-size:9.5px; table-layout:fixed;}
.summary-table th{text-align:left; border-bottom:1.5px solid var(--ink); padding:3px 6px; font-size:9px; text-transform:uppercase; letter-spacing:.02em; color:var(--muted);}
.summary-table td{border-bottom:1px solid var(--line); padding:2.5px 6px;}
.summary-table .num{text-align:right; font-weight:600;}

.legend{margin-top:6mm; page-break-inside:avoid;}
.legend h3{font-size:12px; margin-bottom:3mm; color:var(--accent);}
.legend dl{display:grid; grid-template-columns:110px 1fr; gap:3px 10px; margin:0; font-size:9.5px;}
.legend dt{font-weight:700;}
.legend dd{margin:0; color:var(--muted);}

/* ---- Layer sections ---- */
.layer-section{margin-top:4mm;}
.layer-section.pagebreak{page-break-before:always;}
.layer-section h2{
  font-size:15px; color:#fff; background:var(--accent); padding:3mm 4mm; margin-bottom:5mm;
  page-break-after:avoid;
}
.filecard{margin-bottom:6mm; page-break-inside:auto;}
.filecard h3{
  font-size:11.5px; font-family:"Consolas",monospace; border-bottom:1.5px solid var(--ink);
  padding-bottom:2px; margin-bottom:2mm; page-break-after:avoid;
}
.filerole{font-family:"Segoe UI",Arial,sans-serif; font-weight:400; color:var(--muted); font-size:9.5px;}
.empty-note{color:var(--muted); font-style:italic; font-size:9.5px; margin:0 0 4mm 0;}

/* ---- Function tables ---- */
table.fntable{width:100%; table-layout:fixed; border-collapse:collapse; margin-bottom:2mm;}
table.fntable th{
  text-align:left; font-size:8.5px; text-transform:uppercase; letter-spacing:.02em; color:var(--muted);
  border-bottom:1.3px solid var(--ink); padding:2.5px 4px; background:var(--accent-bg);
}
table.fntable td{
  border-bottom:1px solid var(--line); padding:3px 4px; vertical-align:top; word-break:break-word; font-size:9.5px;
}
table.fntable tr,table.fntable td{page-break-inside:avoid;}
td.mono{font-family:"Consolas","SFMono-Regular",Menlo,monospace; font-size:8.8px;}
td.muted{color:var(--muted); font-size:8.5px;}
td.tagcell{font-size:8px;}
td.num,th.num{text-align:right;}

.tag{
  display:inline-block; background:var(--tag-bg); color:var(--ink); border-radius:3px;
  padding:1px 4px; margin:0 2px 2px 0; font-size:7.8px; white-space:normal; word-break:break-word;
  max-width:100%;
}
.tag-endpoint{background:var(--tag-endpoint-bg); color:var(--tag-endpoint-ink); font-family:"Consolas",monospace; font-size:7.3px;}

@page{size:A4; margin:14mm;}
@media print{
  .layer-section.pagebreak{page-break-before:always;}
}
"""

full_html = f"""<!doctype html>
<meta charset="utf-8">
<title>TreasuryFlow AI — Function Catalog</title>
<style>{CSS}</style>
{BODY}
"""

out_path = os.path.join(SCRATCH, "catalog.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(full_html)
print(f"Wrote {out_path} ({len(full_html)} bytes)")
print(f"Backend total in tables: {total_backend}, Frontend total in tables: {total_frontend}")
