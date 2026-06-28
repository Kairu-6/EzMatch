# test_files — uploadable demo documents

These are the **file half** of the demo dataset: documents that are NOT pre-seeded
in the database. Upload them through the app to exercise the real parse pipeline,
then run reconciliation. The pre-seeded half (live reconcile/verify/anomaly demo +
a historical reconciled job per tenant) is loaded by `apps/backend/seed_demo.py`.

Regenerate everything: run `seed_demo.py` (DB) then `seed_files.py` (these files).

`sme_infos` (JSON) is the authoritative manifest: per-tenant logins, bank accounts,
what is pre-seeded vs file-only, and each upload's expected reconciliation.

Demo password (all four logins): `TreasuryFlow#2026`

## Tenants

- **WZB Group Sdn Bhd** (`MYR`) — finance@wzbgroup.my — folder `wzb_group/`
- **Nusantara Logistics Sdn Bhd** (`MYR`) — ops@nusantara-logistics.my — folder `nusantara_logistics/`
- **Selangor Textiles Bhd** (`MYR`) — finance@selangortextiles.my — folder `selangor_textiles/`
- **Pearl Delta Trading Pte Ltd** (`SGD`) — accounts@pearldelta.sg — folder `pearl_delta/`

Totals: 12 statements · 20 invoices · 20 proofs across 4 tenants.
