# Deploying TreasuryFlow AI (demo)

Three pieces; you deploy two of them:

| Piece | Host | Notes |
|---|---|---|
| **Supabase** (DB + Auth + Storage) | already hosted | nothing to deploy — just keep it awake |
| **Backend** (FastAPI) | **Render** (Docker) | container can install the Tesseract binary |
| **Frontend** (Next.js) | **Vercel** | native Next.js host |

> Why Render (not Vercel) for the backend: image OCR needs the **Tesseract system binary**, which can't be `pip`-installed. The [`apps/backend/Dockerfile`](apps/backend/Dockerfile) `apt install`s it. Serverless hosts can't ship it.

Deploy order: **backend first** (you need its URL), then frontend.

---

## 0. Prerequisites

1. Push the repo to **GitHub** (Render + Vercel deploy from a git repo).
2. Have these secret values ready (Supabase dashboard → Project Settings → API):
   - `SUPABASE_URL` — e.g. `https://yipmoeioxawqrsbtmkqb.supabase.co`
   - **service_role** key (backend secret) → `SUPABASE_API_KEY`
   - **anon** key (frontend public) → `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - Morpheus key → `MORPHEUS_API_KEY`
3. **Wake Supabase** (free tier auto-pauses after ~7 days idle): open the project dashboard; if paused, click *Resume*. API traffic alone won't wake it.
4. Confirm the storage buckets **`invoices`** and **`proofs`** exist (Supabase → Storage). Uploads write there via the service_role key.
5. Make sure the database is seeded (run locally against the hosted Supabase — see §6). It already is if you've been developing against this project.

---

## 1. Deploy the backend → Render (Docker)

1. [dashboard.render.com](https://dashboard.render.com) → **New → Web Service** → connect your GitHub repo.
2. Settings:
   - **Root Directory:** `apps/backend`  ← important (monorepo)
   - **Runtime / Environment:** Docker (Render auto-detects the Dockerfile)
   - **Instance type:** Free is fine for a demo
   - **Health Check Path:** `/health`
3. **Environment variables** (Advanced → Add from `apps/backend/.env.example`):
   ```
   SUPABASE_URL          = https://<project>.supabase.co
   SUPABASE_API_KEY      = <service_role key>      # secret
   MORPHEUS_URL          = https://api.mor.org/api/v1
   MORPHEUS_API_KEY      = <morpheus key>          # secret
   MORPHEUS_PARSE_MODEL  = llama-3.3-70b
   MORPHEUS_AGENT_TOOLS  = native
   RECON_LOOKBACK_DAYS   = 365
   ```
   Do **NOT** set `TESSERACT_CMD` (the binary is on `PATH` in the container).
   `USE_AGENT` is optional (defaults `true`).
   `$PORT` is injected by Render — the Dockerfile already binds it.
4. **Create Web Service.** First build takes a few minutes (installs Tesseract + Python deps).
5. When live, copy the URL, e.g. `https://treasuryflow-api.onrender.com`.
6. Verify: open `https://<your-backend>/health` → should return `{"status":"ok"}`.

> **Railway alternative:** New Project → Deploy from repo → set **Root Directory** `apps/backend` (it reads the Dockerfile) → add the same env vars → Railway auto-assigns a domain.

---

## 2. Deploy the frontend → Vercel

1. [vercel.com/new](https://vercel.com/new) → import the GitHub repo.
2. Settings:
   - **Root Directory:** `apps/frontend`
   - **Framework Preset:** Next.js (auto-detected); leave build/output defaults.
3. **Environment Variables** (from `apps/frontend/.env.example`):
   ```
   NEXT_PUBLIC_SUPABASE_URL       = https://<project>.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY  = <anon key>
   NEXT_PUBLIC_API_URL            = https://<your-backend-from-step-1>   # no trailing slash
   ```
   These are **public, build-time** values (baked into the bundle). Only the anon key here — never the service_role key.
4. **Deploy.** You get `https://<project>.vercel.app`.

> `NEXT_PUBLIC_API_URL` is read at **build time**. If you change the backend URL later, update the var and **redeploy the frontend**.

---

## 3. Supabase post-deploy config

1. **Auth → URL Configuration:** set **Site URL** to your Vercel URL; add it to **Redirect URLs**. (Password login works without this, but it's good hygiene.)
2. **Auth → Providers → Email:** turn **Confirm email OFF** so *new* signups get an instant session. (The 4 seeded demo logins are already email-confirmed.)
3. CORS: the backend already allows all origins (`server.py`), so no extra config.

---

## 4. Smoke test the live demo

1. Hit `https://<backend>/health` once to **warm the backend** (free Render instances cold-start ~30–60s after idle).
2. Open the Vercel URL → **Log in** as a demo tenant:
   - `finance@wzbgroup.my` / `TreasuryFlow#2026` (or any of the 4 — see `test_files/sme_infos`)
3. Dashboard should show pre-seeded historical matches + funds reconciled.
4. Click **Run reconciliation** → the activity terminal streams curated status lines; matches/anomalies appear.
5. **Uploads:** go to `/uploads`, upload a file from `test_files/<tenant>/...` (e.g. a PDF invoice) → it should parse. Try a PNG to exercise Tesseract.
6. Check `/audit` → resolve a `pending_review` exception.

---

## 5. Demo-day notes (free-tier behavior)

- **Render free** spins down after ~15 min idle. The first request cold-starts (~30–60s). **Warm it right before demoing** by hitting `/health`. A long reconcile started just as the instance sleeps could be interrupted — keep it warm, or use a paid instance for a critical demo.
- **Supabase free** auto-pauses after ~7 days idle — resume beforehand.
- Reconciliation runs as a background task and the dashboard polls `/api/job-status`; both work cross-origin over HTTPS.

---

## 6. (Re)seeding the hosted database

Seeding runs **locally** against the hosted Supabase (same project the backend points at). From `apps/backend` with the venv:

```bash
PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe seed_demo.py    # DB: 4 tenants, accounts, history, current set
PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe seed_files.py   # regenerates test_files/ + sme_infos
```

`seed_demo.py` is **destructive + idempotent** — it wipes all tenant data and recreates exactly the 4 demo SMEs + their 4 loginable users (password `TreasuryFlow#2026`). It needs `SUPABASE_URL` + `SUPABASE_API_KEY` in `apps/backend/.env`.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Frontend can't reach backend | `NEXT_PUBLIC_API_URL` wrong or stale → fix the Vercel env var and **redeploy** (build-time). |
| Backend 500 on image upload | Tesseract missing → confirm the Docker build ran `apt install tesseract-ocr`; ensure `TESSERACT_CMD` is **unset**. |
| First request hangs ~1 min | Render free cold start — warm with `/health` first. |
| `/rest/v1/...` returns 521 / errors | Supabase project paused → resume from the dashboard. |
| Login fails for a new signup | Email confirmation still ON → turn it off (§3.2). Seeded demo users are unaffected. |
| Build fails on `pandas`/`pymupdf` | Wheel availability — the Dockerfile pins `python:3.12-slim` for this reason; don't bump to 3.14. |
