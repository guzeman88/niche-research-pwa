# Product validation

Open `/validation`, connect to your private operator backend and create focused
product concepts with up to 15 buyer keywords each. The standalone local page
works during owner account recovery; remote evidence APIs still require operator
authorization. Public pages do not expose private records.

The workflow records dated Etsy Marketplace Insights demand, comparable listing
samples, explicit cost scenarios, supporting Google demand and observed listing
results. Etsy API counts are supply only. Google advertiser competition is not
Etsy seller competition; close variants are retained as one demand group. All
unknown metrics remain unknown. Readiness is a checklist, not a profit forecast.

Use Competitors to collect from the existing Etsy API credentials or import the
CSV template. Inspect saved samples and record a relevance review. Costs require
conservative, base and optimistic assumptions; blank fields do not become zero.
Profit after setup/fixed expenses is distinct from contribution.

Use the Google Validation Evidence manual workflow on `main` with up to 15
comma-separated keywords. It uses the existing keyless Google identity without
the hosted Supabase preflight. Download its checksummed JSON artifact and import
it under Google. Live provider authorization must succeed before this is counted
as newly collected evidence. The collector does not create ads or spend money.

Order CSV columns are explicitly mapped and previewed before commit. Raw items
are preserved for reconciliation without adding their revenue to period totals
again. Reporting worksheets use verified listing IDs and non-overlapping dates.
Cross-concept attribution, conflicting duplicates and overlapping periods fail
before committing any rows. Corrections keep earlier revisions.

SQLite is the authoritative single-writer ledger. Failed Supabase mirroring stays
pending for Retry backup sync. Export evidence ledger includes all revisions.
`backend/scripts/restore_validation_ledger.py` validates checksums and restores
only to a new file, leaving the original unchanged. Back up this ledger and its
configuration in addition to the database mirror.

Installation, scheduled backup and recovery instructions live in the desktop
repository's `docs/product-validation.md`. No public deployment or shop publishing
is performed by the evidence workflow. Seller reports and sales tests depend on
completion of the existing shop's payment/billing onboarding.
