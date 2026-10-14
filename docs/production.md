# Private product production

The `/validation` Production Queue uses the shared, Git-built EtGen production
wheel verified by `backend/production-engine.json`. Read the canonical root
`docs/production-operations.md` and `docs/CURRENT_STATE.md` for installed revisions,
preservation, model/provider setup and verification limits.

The backend supervises persistent jobs only when `APP_PRODUCTION_ENABLED=1`.
APIs and artifact downloads under `/api/production` require operator access.
Customer PDFs/ZIPs/print files are generated locally, checks inspect actual files,
and approvals bind the exact spec/artifact revisions. Marketplace delivery is
draft-only and explicit. No provider order or automatic activation is implemented.

Local models and reviewed image workflows remain capability/benchmark gated.
Missing providers, costs, rights, taxonomy and manufacturing proof stay unknown.
Training requires approved source data and compatible local hardware; merely
having a training adapter is not a successful trained model. Fixtures remain
isolated from production research, jobs and outcomes.

Existing browser concepts can be preserved as review intakes. Old records and
designs are untouched; the production spec requires actual contents and facts.
Generic production project/job revisions use the existing private validation
mirror. Customer files and operation receipts remain in protected host backups.
