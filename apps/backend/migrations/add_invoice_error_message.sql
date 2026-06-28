-- Adds an error_message column to `invoice`, mirroring `payment_proof`, so a
-- failed AI parse is recorded instead of leaving the row looking like it's
-- still "Processing…". Run once in the Supabase SQL editor.
--
-- Safe/idempotent. The backend (invoice_parser.py) already writes to this
-- column on failure, with a fallback for DBs where it doesn't exist yet — so
-- nothing breaks before or after this migration; failures just start showing
-- as "Failed" in the UI once it's applied.

ALTER TABLE invoice ADD COLUMN IF NOT EXISTS error_message text;
