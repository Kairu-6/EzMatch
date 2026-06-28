# CLAUDE.md — TreasuryFlow AI

Handoff/onboarding doc for this repo. Read this first. See also `PRODUCT.md`,
`DESIGN.md`, and the per-session memory in
`.claude/projects/.../memory/` (db_state_rls.md is the most detailed).

## What this is
**TreasuryFlow AI** — automated cross-border reconciliation for a Malaysian SME.
Upload bank statements (CSV/XLSX), invoices (PDF/image), and payment proofs
(PDF/image); an AI engine matches transactions ↔ invoices across currencies
(with FX), surfacing exceptions for review. Brand/lane: institutional trust
(Mercury/Stripe), "the numbers are the hero", honest states, no theatrics.

## Monorepo layout
- `apps/frontend` — Next.js 16 (App Router, React 19, Tailwind v4, TypeScript).
- `apps/backend` — Python FastAPI (Uvicorn), Pydantic v2.
- `test_files/` — ready-made upload test files + `sme_infos` manifest.
- Root: `PRODUCT.md`, `DESIGN.md`, `README.md`, `supabaseClient.js` (stray).

## Run it
**Frontend:** `cd apps/frontend && npm run dev` → http://localhost:3000
**Backend:** `cd apps/backend && ./venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000`
(venv is Windows: `venv/Scripts/`. Always use the venv python.)

- Frontend calls the backend at `http://127.0.0.1:8000` by default; override with
  `NEXT_PUBLIC_API_URL` in `apps/frontend/.env.local` (needed behind a tunnel).
- **Windows console gotcha:** the backend prints emoji; on a cp1252 console that
  raises `UnicodeEncodeError` and fails the request. `main.py` forces UTF-8
  stdout/stderr to fix this. For ad-hoc scripts run with `PYTHONIOENCODING=utf-8`.

## Tech / external services
- **Supabase** (Postgres + storage) — project `yipmoeioxawqrsbtmkqb`. **No RLS** —
  the anon key reads/writes everything. (Free tier: auto-pauses after ~7 days
  idle; resume from the dashboard — API traffic alone won't wake it.)
- **Morpheus** (`api.mor.org/api/v1`, OpenAI-compatible) — reconciliation matching
  AND invoice/proof text→JSON structuring. Funded/working.
- **Tesseract OCR** (local binary) — image invoices/proofs are OCR'd to text, then
  Morpheus structures them. `TESSERACT_CMD` in `.env` points at the binary.
- **Frankfurter** — historical FX rates, cache-first via the `exchange_rate` table.
- **Chutes** — FORMER OCR/vision provider, now UNUSED (account hit $0 balance);
  env vars kept but dead. Do not reintroduce without funding.

## Backend `.env` keys
`SUPABASE_URL`, `SUPABASE_API_KEY` (service_role), `MORPHEUS_URL`,
`MORPHEUS_API_KEY`, `MORPHEUS_PARSE_MODEL` (=`llama-3.3-70b`),
`DEFAULT_SME_ID` (=`111e4567-e89b-12d3-a456-426614174111`),
`RECON_LOOKBACK_DAYS` (=365), `TESSERACT_CMD`
(=`C:\Program Files\Tesseract-OCR\tesseract.exe`), `CHUTES_*` (dead).
`MORPHEUS_MODEL` (matching) defaults to `qwen3-5-9b` in code.

## Multi-tenant auth + RLS (LIVE as of 2026-06-28)
- **Real Supabase Auth (email+password) + RLS on all 12 tables.** Each user owns one
  `sme` workspace via `sme.user_id → auth.users`. The mock `sessionStorage` gate is gone.
- **Frontend:** shared client `app/lib/supabaseClient.ts` (env-driven) + `app/lib/AuthContext.tsx`
  (`session, smeId, companyName, signOut, authHeaders`). `/login` + `/signup` (real `signUp`);
  AppShell redirects to `/login` when no session. No more hardcoded `SME_ID`.
- **Backend:** `auth.py` `get_current_sme_id` dependency validates the Bearer JWT and resolves
  `sme_id` server-side. Uploads stamp it; `/api/reconcile` & `/api/job-status` derive it from the
  token (no `{sme_id}` path param). Backend still uses service_role (bypasses RLS by design).
- **DB:** `current_sme_id()` helper + `handle_new_user()` trigger (claims an unclaimed sme by email,
  else inserts). Policies: direct sme_id, FK-chain EXISTS, global read-only for exchange_rate/currency.
- **WZB demo login:** `finance@wzbgroup.my` / `WzbTreasury#2026` — owns sme `111e4567-…`.
- `test_files/sme_infos` is the manual "who owns what" dependency ledger; new SMEs now self-onboard.

### Post-auth fixes (also 2026-06-28)
- **AuthContext deadlock (gotcha):** never `await` a supabase call inside `onAuthStateChange` — it
  deadlocks the auth lock and hangs ALL later queries until a full reload (symptom: pages load
  forever after navigation). The callback is now synchronous (`setSession` only); the `sme` lookup
  runs in a separate `useEffect` keyed on user id.
- **`transaction_id` is now account-scoped** in `statement_parser.upload_parsed_statement`
  (`sha256("{account_id}|{content-hash}")`). The bare content hash collided across tenants when the
  same statement was re-uploaded, silently reassigning one tenant's transactions to another.
- **Dashboard "Funds reconciled"** now sums `reconciliation_match` (converted_amount for All-accounts
  MYR; transaction_amount per account), not all bank credits.
- A 2nd tenant **Kaikaruu** (`97a5c162-…`) exists from real app signup; 3 stale cross-tenant matches
  were cleaned up.

## Frontend routes (AppShell nav = 3 items)
- `/` — Reconciliation **dashboard**: "Documents" readiness panel + "Go to uploads";
  account toggle; Funds reconciled / Matched / Unmatched; Match-accuracy ring;
  Source feed; Reconciled matches; activity drawer; "Run reconciliation".
- `/uploads` — segmented tabs **Bank statements / Invoices / Payment proofs**
  (merged from 3 former pages). Statements tab also hosts **bank account
  management**.
- `/audit` — exceptions = `reconciliation_match` rows with `match_status='pending_review'`;
  "Resolve" persists `match_status='manual'`.
- `/signup` — mock onboarding.

## Backend endpoints
- `POST /api/upload/statement` — Form: `file`, optional `account_id`. Parses in the
  account's currency, links the statement to it (`statement_parser`).
- `POST /api/upload/invoice`, `POST /api/upload/payment_proof` — stamp `sme_id`,
  upload to storage, parse via Morpheus/Tesseract.
- `POST /api/reconcile/{sme_id}` (202, background) + `GET /api/job-status/{sme_id}`.
- `GET /health`.

## Reconciliation flow (`orchestrator.py`)
Fetch unmatched invoices (status in pending/unmatched, by sme_id) + unmatched
transactions (joined sme via statement→account, within `RECON_LOOKBACK_DAYS`) +
completed proofs → resolve FX (cache→Frankfurter) → build prompt → **Morpheus**
returns match proposals w/ confidence → write `reconciliation_match`
(`auto` if confidence ≥ 0.75 else `pending_review`), flip `bank_transaction.is_matched`,
set invoice status. `_fetch_invoices` skips rows that fail schema validation
(failed/half-parsed) so they don't crash the job.

## DB schema (key tables + FK chains)
`sme` → `bank_account`(sme_id) → `bank_statement`(account_id) →
`bank_transaction`(statement_id). `invoice`(sme_id). `payment_proof`(sme_id,
invoice_id). `exchange_rate` (FX cache). `reconciliation_job`(sme_id) /
`reconciliation_match`(job_id, invoice_id, transaction_id, proof_id, rate_id) /
`reconciliation_log`(job_id) / `recommendation`(sme_id, job_id).
Full column lists in memory `db_state_rls.md`.

## Seed / reset
- `apps/backend/seed_demo.py` — wipes everything except `sme` + `bank_account`,
  reseeds a coherent demo (invoices USD/EUR/SGD/MYR, matching transactions,
  proofs, FX rates). Run: `PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe seed_demo.py`.
  **It wipes `exchange_rate`**, so after a reset re-run the test-file FX seed
  (scratchpad `gen_test_files.py`) if you use the test invoices.
- `test_files/` (9 files) are cross-consistent and reconcilable; the generator is
  in the session scratchpad (`gen_test_files.py`). The 4 PDFs parse via Morpheus;
  the 2 PNGs need Tesseract.

## Major decisions & upgrades (this session)
1. **Merged** 3 upload pages → `/uploads` with a custom `SegmentedControl`; nav
   slimmed to 3 (Reconciliation/Uploads/Audit).
2. **Security:** removed the `service_role` key from the frontend (anon works
   everywhere since no RLS).
3. **Audit page** wired to real `reconciliation_match` (`pending_review`); resolve
   persists `manual`. Mock data removed.
4. **Single-tenant fixes:** stamp `sme_id` on uploaded invoices/proofs; killed the
   30-day transaction window (now `RECON_LOOKBACK_DAYS`, default 365 — the old
   hardcoded 30 silently broke recon as data aged); statement→account resolved by
   tenant (primary), not "first row".
5. **Parsing provider swap:** Chutes ($0 balance, HTTP 402) → **Morpheus text +
   Tesseract OCR** via new `parser_llm.py`; `invoice_parser.py`/`proof_parser.py`
   rewritten (PDF→PyMuPDF text→Morpheus; image→Tesseract→Morpheus).
6. **Invoice failure visibility:** parser writes `error_message`; UI shows a red
   "Failed" pill instead of fake "Processing…". **Requires a migration (below).**
7. **Dashboard:** loads **cumulative** reconciled state (survives navigation +
   no-op re-runs); source feed shows signed +/− (credit green / debit muted,
   sign carries direction for a11y); fixed debit rows that showed RM 0.
8. **Multi-account:** accounts panel on Uploads (list, **Add**, **Make primary**,
   **Delete** w/ inline confirm + cascade + auto-promote primary); statement
   upload **account picker**; ledger **Account** column; dashboard **account
   toggle** scoping funds/transactions/source feed, currency-aware.
9. **Tunnel/hydration:** `allowedDevOrigins` includes `*.trycloudflare.com`;
   `NEXT_PUBLIC_API_URL` for the backend base; `suppressHydrationWarning` on
   `<html>`+`<body>` (hydration warnings over tunnels are usually browser
   extensions, not our code).

## ⚠️ PENDING ACTION ITEMS (do these)
1. **Auth config (Supabase dashboard, can't be done via MCP):** Auth → Providers →
   Email → turn **Confirm email OFF** so new self-signups get an instant session.
   (The signup page shows a "check inbox" fallback if it's left on.) Optional:
   rotate the anon key (then update `apps/frontend/.env.local`) + enable
   leaked-password protection. The WZB demo user is already email-confirmed.
   *(The old `add_invoice_error_message.sql` migration is already applied.)*
2. **Run the real UI e2e** once: log in as `finance@wzbgroup.my`, upload, reconcile,
   resolve an audit exception — confirms the wiring in a browser (RLS already
   verified at the DB layer).
3. For tunnel uploads/recon: tunnel the **backend (8000)** too and set
   `NEXT_PUBLIC_API_URL` to its https URL; restart `next dev`. (Reads work over
   the frontend tunnel alone; uploads/recon need the backend reachable + HTTPS.)
4. Restart the backend after any `.env` change.

## Known limitations / future work
- **Auth is real now** (see the multi-tenant section). Remaining: teammate invites
  (one user = one workspace today; a junction table would allow many users per sme),
  password reset emails, and the dashboard config items above.
- **Multi-currency reconciliation:** `orchestrator` assumes one account currency
  (`transactions[0]`); "All accounts" cross-currency dashboard totals are
  indicative (summed as MYR). Only MYR data today.
- **Image OCR quality:** Tesseract on clean generated images is great; messy phone
  photos will be worse than a vision model. Morpheus premium/multimodal models
  (Gemini/GPT/Claude) 500 with "Failed to create session" on this account, so
  vision isn't available there.
- Secrets (anon key, Morpheus/Chutes keys) live in code/`.env`; fine for this
  prototype, not production.

## Conventions
- Frontend: custom UI kit in `apps/frontend/app/components/ui/` (Button, Field,
  Panel, Table, StatusPill, Dropzone, SegmentedControl, Skeleton, EmptyState,
  RingProgress, Toast, ActivityDrawer, PageHeader). OKLCH tokens in `globals.css`;
  class-based dark mode; reuse the kit, follow `DESIGN.md` bans (no emoji status,
  no red for non-errors, status never color-only).
- Direct Supabase reads/writes from the frontend with the anon key are the norm
  (e.g. audit resolve, account CRUD) — now RLS-scoped to the logged-in tenant via
  the session JWT, so no `sme_id` filter is needed on reads.
- Inline confirm pattern (Confirm/Cancel buttons) instead of `window.confirm`.
