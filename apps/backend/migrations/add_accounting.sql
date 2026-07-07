-- AutoCount + SQL Account invoice connector (applied 2026-07-07 via supabase apply_migration).
-- Generic provenance/dedup columns on invoice + per-tenant connector credentials.
-- Mirrors add_myinvois; `source` already exists live (that migration ran first) so the
-- ADD is a no-op there, but keeping it makes this branch self-consistent.

ALTER TABLE invoice ADD COLUMN IF NOT EXISTS source text DEFAULT 'upload';
ALTER TABLE invoice ADD COLUMN IF NOT EXISTS source_ref text;   -- vendor doc no (per source)

-- Idempotent sync: one invoice row per (tenant, source, external ref). NOT partial —
-- PostgREST upsert ON CONFLICT can't infer a partial index; plain unique still allows
-- unlimited NULL source_ref rows (NULLs distinct), so upload/myinvois invoices are unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS invoice_sme_source_ref
  ON invoice (sme_id, source, source_ref);

-- One row per (tenant, provider) so AutoCount and SQL Account are independently
-- configurable. (MyInvois keeps its own myinvois_credential table.)
CREATE TABLE IF NOT EXISTS accounting_credential (
  sme_id       uuid REFERENCES sme(sme_id) ON DELETE CASCADE,
  provider     text NOT NULL DEFAULT 'autocount',  -- autocount | sql
  environment  text DEFAULT 'mock',        -- mock only today (see accounting_client.py)
  -- Columns below are RESERVED for a future live integration once a paid SME subscription
  -- + official API docs are obtained. Unused today (both providers are mock-only).
  base_url     text,
  api_key      text,                       -- ponytail: plaintext under RLS, prototype-grade (see CLAUDE.md)
  access_token text,
  company      text,
  updated_at   timestamptz DEFAULT now(),
  PRIMARY KEY (sme_id, provider)
);

ALTER TABLE accounting_credential ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS accounting_credential_tenant ON accounting_credential;
CREATE POLICY accounting_credential_tenant ON accounting_credential
  FOR ALL
  USING (sme_id = (SELECT current_sme_id()))
  WITH CHECK (sme_id = (SELECT current_sme_id()));
