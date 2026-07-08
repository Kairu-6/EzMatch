-- Finverse bank-feed connector (open-banking transaction pull).
-- Unlike the invoice connectors there is NO per-tenant credential table — the app has
-- ONE set of global developer creds (env). The per-tenant artifact is a CONSENT
-- (login_identity) obtained via the three-legged Finverse Link redirect, stored here.

CREATE TABLE IF NOT EXISTS bank_feed_link (
  link_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sme_id            uuid NOT NULL REFERENCES sme(sme_id) ON DELETE CASCADE,
  account_id        uuid REFERENCES bank_account(account_id) ON DELETE SET NULL,
  finverse_login_id text NOT NULL,
  institution       text,
  access_token      text,   -- ponytail: plaintext under RLS, prototype-grade (== myinvois client_secret ceiling)
  refresh_token     text,
  token_expires_at  timestamptz,
  status            text DEFAULT 'active',   -- active | revoked
  created_at        timestamptz DEFAULT now()
);

-- Idempotent relink: one consent row per (tenant, Finverse login). NOT partial —
-- PostgREST upsert ON CONFLICT can't infer a partial index.
CREATE UNIQUE INDEX IF NOT EXISTS bank_feed_link_sme_login
  ON bank_feed_link (sme_id, finverse_login_id);

ALTER TABLE bank_feed_link ENABLE ROW LEVEL SECURITY;

-- RLS guards the frontend anon reads (Settings linked-list + Disconnect). The backend
-- uses service_role (bypasses RLS); the JWT-less callback writes with sme_id decoded
-- from the HMAC-verified state, never a client value.
DROP POLICY IF EXISTS bank_feed_link_tenant ON bank_feed_link;
CREATE POLICY bank_feed_link_tenant ON bank_feed_link
  FOR ALL
  USING (sme_id = (SELECT current_sme_id()))
  WITH CHECK (sme_id = (SELECT current_sme_id()));

-- Provenance tag so a synced statement reads as 'bankfeed' rather than an upload.
-- (upload_parsed_statement writes it; default keeps every existing upload as 'upload'.)
ALTER TABLE bank_statement ADD COLUMN IF NOT EXISTS source text DEFAULT 'upload';
