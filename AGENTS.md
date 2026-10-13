# Continuing this repository

Read [docs/current-state.md](docs/current-state.md) first, then the desktop
repository's linked continuity handoff. Refresh live state before mutations.

- Keep the user's free-only constraint. Preserve data, configuration, artwork,
  browser workspaces and ignored outputs. No resets/volume deletion as repair.
- Secrets, actual account identities and financial details stay in protected local
  files; do not put them in Git, browser bundles or workspace exports.
- Etsy's developer account and intended seller shop are separate. Check the
  verified private map before seller-specific work. Seller onboarding is complete;
  EtGen owner access and public cutover are separate pending gates.
- SQLite is the authoritative validation writer; Supabase is its retryable private
  mirror. Public snapshots must not include private validation/account records.
- Unknown/error/stale evidence remains unknown. Readiness is not a profit forecast;
  Google advertiser competition is not Etsy seller competition.
- Inspect each Git checkout before edits. Fetch, fast-forward only if clean,
  preserve dirty work, and stage explicit task paths. A source merge does not
  install the local app or deploy production.
- For UI changes follow the user's Refactoring UI principles: start with the
  useful feature, consistent scales and clear hierarchy; preserve workflows and
  verify keyboard access/mobile layouts.
- Update the linked handoff after operational changes. Keep this page a pointer
  rather than maintaining conflicting copies of private identities/current counts.
