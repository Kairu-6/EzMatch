-- MyInvois e-Invoice integration (applied 2026-07-07 via supabase apply_migration).
-- Provenance columns on invoice + per-tenant credentials.

ALTER TABLE invoice ADD COLUMN IF NOT EXISTS myinvois_uuid text;
ALTER TABLE invoice ADD COLUMN IF NOT EXISTS direction text;
ALTER TABLE invoice ADD COLUMN IF NOT EXISTS source text DEFAULT 'upload';

-- Idempotent sync: one invoice row per (tenant, IRB uuid). NOT partial — PostgREST
-- upsert ON CONFLICT can't infer a partial index; plain unique still allows unlimited
-- NULL myinvois_uuid rows (NULLs are distinct), so OCR invoices are unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS invoice_sme_myinvois_uuid
  ON invoice (sme_id, myinvois_uuid);

CREATE TABLE IF NOT EXISTS myinvois_credential (
  sme_id       uuid PRIMARY KEY REFERENCES sme(sme_id) ON DELETE CASCADE,
  model        text DEFAULT 'taxpayer',      -- taxpayer | intermediary
  environment  text DEFAULT 'mock',          -- mock | preprod | production
  client_id    text,
  client_secret text,                        -- ponytail: plaintext under RLS, prototype-grade (see CLAUDE.md)
  tin          text,
  updated_at   timestamptz DEFAULT now()
);

ALTER TABLE myinvois_credential ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS myinvois_credential_tenant ON myinvois_credential;
CREATE POLICY myinvois_credential_tenant ON myinvois_credential
  FOR ALL
  USING (sme_id = (SELECT current_sme_id()))
  WITH CHECK (sme_id = (SELECT current_sme_id()));
