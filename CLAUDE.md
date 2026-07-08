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
- **LHDN MyInvois** (`myinvois.hasil.gov.my` / `preprod.…` sandbox) — pull VALIDATED
  e-Invoices as a second invoice source (augments OCR, doesn't replace it). See the
  MyInvois section below.
- **Chutes** — FORMER OCR/vision provider, now UNUSED (account hit $0 balance);
  env vars kept but dead. Do not reintroduce without funding.

## LHDN MyInvois e-Invoice integration (2026-07-07)
Pull validated e-Invoices from MyInvois so they land in `invoice` and flow through
reconciliation like OCR'd invoices — **MyInvois is just another invoice source**.
- **Client:** `apps/backend/myinvois_client.py` — OAuth2 `client_credentials`
  (`/connect/token`, scope `InvoicingAPI`, in-proc token cache), `get_recent_documents`
  (Sent/Received, last 31 days, Valid only), `get_document_raw` (raw UBL 2.1 JSON —
  the recent/details endpoints report **MYR only, no currency**, so we read
  `DocumentCurrencyCode` + `PayableAmount` from the raw doc), and `map_document`
  (UBL→invoice row). **Mock mode** (environment=`mock`) returns 5 static UBL fixtures
  so it's demoable with no real creds; flip environment to `preprod`/`production` to hit
  the real API (no code change). Self-check: `test_myinvois_map.py`.
- **Endpoint:** `POST /api/myinvois/sync` (server.py, JWT→sme_id) pulls both directions,
  dedups on `myinvois_uuid`, upserts invoices `on_conflict="sme_id,myinvois_uuid"`.
- **Auth model:** taxpayer (per-tenant client_id/secret). Intermediary path is stubbed
  behind `creds.model=='intermediary'` (adds `onbehalfof` header), not exercised.
- **The IRB UUID is NOT a recon join key** (bank txns carry no UUID) — it's an ingestion
  dedup/idempotency key + trust badge. Matcher stays LLM-semantic, unchanged.
- **DB (migration `add_myinvois`):** `invoice` gained `myinvois_uuid`, `direction`,
  `source` (default `upload`) + a unique index on `(sme_id, myinvois_uuid)` (not
  partial — PostgREST upsert can't infer a partial index; NULL uuids stay unconstrained).
  New `myinvois_credential` table (PK `sme_id`, RLS via `current_sme_id()`).
  `# ponytail: client_secret stored plaintext under RLS — prototype-grade, same trust
  level as bank_account data; not production.`
- **Frontend:** `/settings` page (creds form, env Mock/Sandbox/Production, read/write
  `myinvois_credential` via anon client) linked from the AppShell profile menu;
  "Sync from MyInvois" button + `e-Invoice` badge on the Uploads → Invoices tab.
- **Follow-ups (not built):** submission/Peppol (MDEC accreditation); matcher
  direction-awareness (Received/payables invoices go into a sign-agnostic matcher today).

## Finverse bank-feed (open banking) integration (2026-07-08)
Pull bank transactions directly via **Finverse** (the real Plaid-for-Malaysia — Brankas does
NOT cover MY; Finverse covers Maybank/CIMB/Public/OCBC etc.) so SMEs stop uploading a CSV
every week. A bank feed is **just another statement source**: it lands rows through the
existing `statement_parser.upload_parsed_statement` seam, then reconciles unchanged.
- **NOT credential-shaped like MyInvois.** App creds are **GLOBAL** (`.env`, one developer app);
  the per-tenant artifact is a **consent (`login_identity`)** obtained via a **three-legged
  browser redirect** (Finverse Link). Flow: `POST /api/bankfeed/link` (JWT→state) → user
  authorizes their bank in Finverse's hosted UI → `GET /api/bankfeed/callback` (PUBLIC, no JWT)
  → `POST /api/bankfeed/sync`.
- **Client:** `apps/backend/bank_feed_client.py` — `_customer_token` (`POST /auth/customer/token`,
  in-proc cache), `create_link_session` (`POST /link/token` → hosted `link_url`), `exchange_code`
  (`POST /auth/token` form-urlencoded → login-identity token, then poll `GET /login_identity`),
  `get_transactions` (`GET /transactions`, paginated → parser blob). Endpoints verified from the
  official SDK (`github.com/finversetech/sdk-typescript`). **Mock mode** (`FINVERSE_ENV=mock`,
  default) returns static fixtures AND a `link_url` that loops straight back to our own callback,
  so the whole consent→sync→recon path is demoable offline; set `FINVERSE_ENV=sandbox`/`prod` for
  the real API (no code change). Self-check: run `bank_feed_client.py` / `bankfeed_state.py` directly.
- **ONE API host for test AND live: `https://api.prod.finverse.net`** — there is NO `api.sandbox`
  host (it fails DNS). "sandbox vs prod" is decided by which CREDENTIALS you use, not the host, so
  `FINVERSE_ENV` is effectively mock-vs-real. **Verified live (2026-07-08):** customer-token mint
  ✅ and `/link/token` param validation ✅ against prod with the real creds; `state` is capped at
  100 chars by Finverse (we send a compact `sme_id.epoch.sig` ~80-char HMAC token).
- **State/tenant routing:** `apps/backend/bankfeed_state.py` — HMAC-signed, 10-min `state` carries
  the sme_id across the JWT-less redirect (also CSRF). The callback writes with service_role using
  the sme_id decoded from the verified state, never a client value.
- **Dedup:** feed rows seed `transaction_id` from Finverse's stable ULID (not the content hash), so
  re-syncs dedup exactly via the existing account-scoped upsert. `# ponytail: an account that is
  BOTH CSV-uploaded and feed-synced can double-count (uploads carry no stable id).`
- **DB (migration `add_bankfeed`):** new `bank_feed_link` table (consent + tokens, PK `link_id`,
  unique `(sme_id, finverse_login_id)`, RLS via `current_sme_id()`); `bank_statement` gained
  `source` (default `upload`, set `bankfeed` on sync) and its `file_type` CHECK now allows `feed`.
  No per-tenant credential table. `# ponytail: login-identity token plaintext under RLS —
  prototype-grade, same ceiling as myinvois_credential.` `upload_parsed_statement` gained a
  `file_type` param (default `csv`, so uploads are unchanged).
- **Frontend:** `/settings` **BankFeedCard** (Connect button + linked-bank list + Disconnect; NO
  creds fields) — "Connect" opens the returned `link_url`. `/uploads` statements tab: **"Sync bank
  feed"** button + a `?linked=1` return toast. AppShell/AuthContext unchanged (callback is the
  backend, which 302s back to the already-protected `/uploads`).
- **⚠️ Prod creds were shared in chat once — ROTATE the client secret in `dashboard.finverse.com`
  before any real pull.** `customer_app_id` is response-only, not an auth input.
- **To go live (dashboard steps, not code):** rotate secret → set `FINVERSE_CLIENT_ID/SECRET` +
  `FINVERSE_ENV=sandbox|prod` + `FINVERSE_REDIRECT_URI` (HTTPS, tunnel the backend) → register that
  redirect_uri in the Finverse dashboard → restart. First smoke test: curl `POST /auth/customer/token`.
- **Follow-ups (not built):** webhooks/auto-refresh (`/login_identity/refresh`, `/auth/token/refresh`),
  consent-expiry relink, per-account split (one login → first account today), statements/PDF pull,
  pgcrypto token encryption. Real MY-bank product entitlements + redirect_uri whitelist are only
  confirmable against the live API.

## Backend `.env` keys
`SUPABASE_URL`, `SUPABASE_API_KEY` (service_role), `MORPHEUS_URL`,
`MORPHEUS_API_KEY`, `MORPHEUS_PARSE_MODEL` (=`llama-3.3-70b`),
`RECON_LOOKBACK_DAYS` (=365), `TESSERACT_CMD`
(=`C:\Program Files\Tesseract-OCR\tesseract.exe`), `MORPHEUS_AGENT_TOOLS` (=`native`).
- **Removed (2026-06-28 cleanup):** `DEFAULT_SME_ID` (auth always supplies the tenant now),
  `CHUTES_*` (dead provider), and `USE_AGENT` is no longer needed in `.env`.
- **`USE_AGENT` now defaults to `true` in code** (agent is the default engine; set
  `USE_AGENT=false` to force the legacy pipeline). `MORPHEUS_MODEL` (legacy matching)
  defaults to `qwen3-5-9b`, `MORPHEUS_AGENT_MODEL` to `minimax-m2.5`, both in code.
  Tuning knobs (`GATE_*`, `VERIFY_*`, `ANOMALY_*`, `LEARNED_*`, `AGENT_*`) all have code defaults.
- **Finverse bank feed (2026-07-08):** `FINVERSE_ENV` (=`mock`, or `sandbox`/`prod`),
  `FINVERSE_CLIENT_ID`, `FINVERSE_CLIENT_SECRET` (SECRET, `fv-c-…`), `FINVERSE_REDIRECT_URI`,
  `FRONTEND_URL`, `BANKFEED_STATE_SECRET` (HMAC signing key). Mock needs no creds. See the
  Finverse section above.

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
- **Demo logins (4 tenants, all password `TreasuryFlow#2026`, email pre-confirmed):**
  `finance@wzbgroup.my` (WZB, sme `111e4567-…`), `ops@nusantara-logistics.my` (sme `2222…`),
  `finance@selangortextiles.my` (sme `3333…`), `accounts@pearldelta.sg` (sme `4444…`, SGD base).
  Provisioned by `seed_demo.py`; re-running rotates the password back to this.
- `test_files/sme_infos` (JSON) is the manifest/ledger of who owns what + the logins; new SMEs
  also self-onboard via signup.

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
- (Historical note) earlier ad-hoc tenants (Kaikaruu + junk signups) were removed by the
  2026-06-28 multi-tenant reseed; the DB now holds exactly the 4 demo tenants above.

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

## Seed / reset (multi-tenant, idempotent — 2026-06-28)
Three modules in `apps/backend/`, all-deterministic ids (uuid5) so re-runs replace in place:
- **`seed_data.py`** — single source of truth: 4 SMEs, 3 accounts each (mixed
  MYR/USD/EUR/SGD), a historical reconciled job per tenant (B.1 `manual` exemplars +
  B.3 outlier baselines), a pre-seeded "current" set (pending invoices + matching/noise
  transactions + proofs), and a parallel FILE set. Every document tagged `db` vs `file`.
- **`seed_demo.py`** — the reseed. **Destructive + idempotent:** wipes ALL tenant data
  (FK-safe order), prunes stray Supabase Auth users, provisions exactly 4 loginable demo
  users (service-role admin API, email pre-confirmed), inserts accounts/FX/history/current.
  Run: `PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe seed_demo.py`. Upserts (never wipes)
  `exchange_rate`.
- **`seed_files.py`** — (re)generates the "file half" under `test_files/` + `sme_infos` +
  `README.md`. Run after `seed_demo.py`.
- Seeds ~132 transactions, 56 invoices, 12 proofs, 20 historical matches across 4 tenants.
  Edge cases: clean multi-currency auto-match, FX, over-paid→escalate, unmatched, B.2
  high-value-no-proof + weak-link (downgrade on run), B.3 duplicate-invoice /
  beneficiary-mismatch / bank-detail-change / amount-outlier, failed invoice & proof parse,
  statement format coverage (ISO+signed CSV / dd-mm-yyyy CSV / debit-credit XLSX).
- `test_files/` is now per-tenant: `test_files/<slug>/{bank_statements,invoices,payment_proofs}/`
  (12 statements + 20 invoices + 20 proofs). NOT pre-seeded — uploading them tests the parse
  pipeline (PDF→PyMuPDF→Morpheus, PNG→Tesseract→Morpheus). `test_files/sme_infos` (JSON) is the
  manifest: per-tenant logins, accounts, pre-seeded-vs-file docs, expected reconciliation.
  (Old scratchpad `gen_test_files.py` retired; old single-tenant 9-file layout replaced.)

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
