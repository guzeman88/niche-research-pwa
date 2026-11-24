# Dashboard startup

The Pipeline design and existing detail/export routes remain unchanged. Initial
dashboard rendering does not fetch the raw product-validation ledger or probe
production providers.

- `/api/startup` is an authenticated read-only projection of authoritative SQLite
  project headers and latest product revisions. It caps the preview at 50 projects
  and 24 products, includes total counts and pagination indicators, and reports
  missing sources as unavailable/null. Full lists remain available on their pages.
- The existing service-only `app_dashboard_state` holds the same small projection
  with the precomputed research summary. RLS excludes anonymous and authenticated
  database roles; only the administrator account function releases it. No raw
  evidence, customer personalization, artwork or credentials enter this packet.
- Login and `/api/account/bootstrap` return verified session, owner-filtered
  workspace and optional hosted summaries together. MFA and recovery responses
  exclude workspace/operator data. Periodic checks omit the already active
  workspace, preserving unsaved edits and revision-conflict handling.
- The browser persists only allowlisted display summaries, capped at 128 KiB and
  one day. It hydrates after verified authentication, scopes by account/role and
  clears on logout, account switch, role change or authentication rejection.
  Generated timestamps remain source timestamps, and stale/error states remain
  visible. This cache grants no write or approval permission.
- Successful product/production mutations invalidate starter data and request a
  current read-only projection instead of waiting for the publisher. Ordinary
  polls use the hosted snapshot; delayed snapshots fall back to the bounded API.
- Product review reads one current job on opening. Approval controls require a
  successful current detail read. Package-integrity checks still precede preview
  reads and exports. Dashboard/list images use bounded WebP thumbnails; full files
  remain on demand. Likely next-screen modules prefetch after login, except on
  constrained/data-saving connections. Provider probes remain in explicit tools.

The combined bootstrap reduces round trips; it does not bypass authentication,
guarantee instantaneous identity verification or claim offline evidence is live.
Reporting remains a roughly 60-second snapshot. Source database failures,
connector failures and stale reports remain explicit. Full evidence may still
take longer when deliberately opened.

Verification includes backend projection/privacy/auth/integrity tests, browser
cache/account-boundary tests, an inline-login/no-waterfall browser regression,
and the existing Pipeline and specialist workflow suites. Windows builds resolve
Vite's root through directory junctions to keep entry and output paths coherent.
