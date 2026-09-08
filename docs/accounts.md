# Account service

`netlify/functions/account.mjs` hosts same-origin `/api/account/*`. Supabase Auth
handles passwords, verified email and TOTP; service-only database sessions provide
opaque HttpOnly cookies, encryption, idle expiry and immediate revocation.

Required function runtime variables are `SUPABASE_URL`, `SUPABASE_ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY`, `AUTH_COOKIE_SECRET` (32 random bytes in base64), and
`APP_ORIGIN` (exact HTTPS origin). `ACCOUNT_EMAIL_READY=1` enables signup/recovery
only after custom SMTP and the confirmation templates are tested. An optional
`PRIVATE_BACKEND_URL` enables administrator research operations. Never expose
service keys through Vite variables.

Account migrations and the owner invitation/configuration script live in the
[desktop repository](https://github.com/guzeman88/etsy-pipeline/tree/codex/accounts-and-profiles).
Its `docs/ACCOUNTS.md` describes setup, RLS, data preservation and the release gate.
The initial owner must choose their own password and verify their email. Production
rollout stays pending until email delivery and owner access work.

Web stores, products, listings and imports are private account data. Shared research
snapshots under `/data` remain public. Earlier browser work is preserved and requires
an explicit import. Desktop local pipeline files have a separate lifecycle.

## Checks

- `npm test`: encryption, CSRF, cookies, interrupted edits and existing release tests.
- `npm run lint`, `npx tsc -b`, `npm run build`: code and snapshot/build validation.
- `node scripts/test-account-integration.mjs --live`: opt-in Supabase security tests.
- `node scripts/auth-dev-server.mjs` plus `npm run dev -- --host 127.0.0.1`, then
  `node scripts/test-account-ui.mjs --live`: responsive browser checks.

Live tests create isolated synthetic users, send no email, and clean up only the
exact users/invitations they created. They use private `.env.local` configuration;
do not run them against arbitrary customer accounts.
