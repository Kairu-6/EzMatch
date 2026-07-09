# test_files — uploadable demo documents

These are the **file quarter** of the demo dataset: documents that are NOT pre-seeded
in the database. Upload them through the app to exercise the real parse pipeline,
then run reconciliation. The pre-seeded bulk (live reconcile/verify/anomaly demo +
a historical reconciled job) is loaded by `apps/backend/seed_demo.py`.

Regenerate everything: run `seed_demo.py` (DB) then `seed_files.py` (these files).

`sme_infos` (JSON) is the authoritative manifest: login, bank accounts, what is
pre-seeded vs file-only, and each upload's expected reconciliation.
`expected_reconciliation.json` is the ground-truth baseline (per pre-seeded invoice)
that `eval_recon.py` scores a real reconcile run against.

Demo login: **finance@wzbgroup.my** · password `TreasuryFlow#2026`

## Tenant: WZB Group Sdn Bhd (`MYR`)

Folder `wzb_group/` — 3 statements · 18 invoices · 18 proofs.

## Invalid files (`_invalid/`) — failure-path coverage

Upload these to show honest parse-failure/validation states:

- `_invalid/corrupt.pdf` (upload as invoice or payment_proof) → parse fails → red 'Failed' pill + error_message (no readable text)
- `_invalid/empty.csv` (upload as bank statement) → parse yields zero transactions → rejected / empty statement
- `_invalid/bad_schema.csv` (upload as bank statement) → no mappable date/amount columns → parse error
- `_invalid/unsupported.txt` (upload as any) → unsupported file type → upload rejected
