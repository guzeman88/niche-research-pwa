# Account service incidents

November 25, 2026: the configured provider returned HTTP 402 with
`exceed_db_size_quota` for Auth and REST. This blocks authentication and private
data even while signed-out session routes and the installed research API respond.
The desktop canonical handoff records measured sizes and encrypted account backup
locations. The existing local Auth instance has zero users and is not a failover.

The account function returns HTTP 503 and an explicit `account_service_restricted`
code/reason for a provider quota restriction. Transient provider errors also
remain service failures. They do not clear a valid session cookie or become an
invalid-password response. Actual invalid credentials, inactive accounts,
revocations, workspace conflicts, MFA and recovery checks retain their controls.
This error handling does not lift the provider restriction or migrate accounts.

An incident-only GitHub deployment option can reuse all eight public snapshots
from an immutable, previously verified Netlify deployment. Set
`reuse_verified_snapshot=true`, `snapshot_url` to its immutable
`https://<24-hex-id>--etgen.netlify.app` address, and `snapshot_commit` to its exact
40-character source commit. The build checks the manifest identity, every file's
SHA-256 and keyword/statistic consistency before preserving the original bytes.
It records `snapshot_mode=last_verified_release`, provenance and the original
data timestamp. It never mixes partial live responses with an old snapshot.
This allows an account-function hotfix while the data provider is unavailable.
Default and scheduled deployments still require live data; recovery is explicit.
The release verifier checks the actual deployed bytes against the new manifest.

These public snapshots contain research exports, not private account/workspace
rows. Restoring hosted account availability remains a separate provider-capacity
or tested migration task. Preserve the account archive and bulk research before
any data cleanup or cutover; the restriction is not permission to reset a database.
