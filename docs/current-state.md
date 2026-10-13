# Continuation entry point

Updated October 12, 2026. The canonical cross-repository operational handoff is
[etsy-pipeline/docs/CURRENT_STATE.md](https://github.com/guzeman88/etsy-pipeline/blob/main/docs/CURRENT_STATE.md).
Read it before using historical setup instructions. It records verification date,
source/runtime/deployment mapping, provider access, private evidence locations,
backup/recovery boundaries and remaining work. In the shared Windows workspace,
the file is also at `../../docs/CURRENT_STATE.md` relative to this checkout root.

The local app at http://127.0.0.1:5175/validation is installed from web revision
`1cd92bebae941d77c1e7018b5f157d6585cde20d`. Its exact code/control/data/Python
paths live in `%USERPROFILE%/EtGen/product-validation/installation.json`. Merging
this documentation does not reinstall the bundle. The private API is loopback
http://127.0.0.1:18020/api/product-validation; broad research scheduling is disabled
there. Original bulk collection is a separate workflow/writer.

Three focused concepts have actual Etsy samples, supporting Google data and Etsy
Marketplace Insights demand, with raw/error reports retained. Exact cost scenarios,
first live listing and own sales outcomes remain pending. Financial/security setup
on the correct **EtgenStudios** seller shop is complete. The unfinished singular
**EtGenStudio** belongs to a different developer identity; do not restart seller
onboarding based on that account. Consult the private map in the canonical handoff;
never copy account emails/passwords or banking screenshots into this repository.

Local Supabase is a reconstructed, isolated host and a private validation mirror.
Cloud-only Auth/workspaces/Storage remain unrecovered from the old hosted project;
support was contacted October 10. New EtGen owner/email, stable authenticated HTTPS
endpoint, off-machine backup and public cutover are still pending. The public site
continues to serve the October 1 release. Bank verification does not resolve those
separate infrastructure gates.

Windows startup/backup tasks and the weekly Codex focused-evidence heartbeat are
installed. They depend on the PC/user/app being available; do not interpret old
bulk schedule descriptions as confirmed current collection. The manual GitHub
`Google Validation Evidence` workflow uses existing keyless identity; due imports
and Etsy samples are orchestrated by the verified root collection runner. Inspect
the visible free Marketplace Insights allowance before further buyer-demand queries.

Read [product-validation.md](product-validation.md) for the private evidence
contract and [launch-lab.md](launch-lab.md) for the separate decision contract.
They have different review gates; neither guarantees profit. Retry backup sync is
mirror replay, not encrypted/off-machine disaster recovery.

When changing installed/runtime/provider state, update the canonical handoff and
the relevant contract/runbook. Reverify versions/counts rather than duplicating
the dated inventory here. Keep production changes Git-backed and verify the live
release fingerprint after an authorized cutover.
