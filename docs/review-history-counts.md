# Backend historical review-count acquisition

The existing backend discovery source owner can run one opt-in, finite historical
review-count plan. Its minute worker and the existing before-native hook share
the same discovery refresh lease and source-pass gate. It uses the same native
worker lease, approved Etsy Client, 40-call bound and global quota ledger.
The keyword collector's batch size and schedule stay unchanged. A requestful
count pass consumes that product-research turn. Active research reserves its
exact next eligible time; disabled, complete or halted plans preserve normal
selling discovery when the shared source gate permits it.

This is a one-off acquisition for an offline comparison, not an external
estimator feed or a trained sales model. It records API-reported exact-listing
review counts over declared historical bounds. Review counts do not establish
purchases or universal lifetime coverage. Eligibility and activation stay false.

## Protected operator setup

Configuration belongs below the existing private archive:
`sales-intelligence/review-history-counts/config.json`. No HTTP write endpoint,
environment-secret change, external scheduler or operator-code import is added.
The application must already own collection. Stage the original plan as bytes;
do not rewrite it, because its raw SHA256 binds the export contract.

```json
{
  "enabled": true,
  "plan_file": "plan.json",
  "plan_sha256": "<exact lowercase SHA256 of copied plan bytes>",
  "output_directory": "run-v1",
  "not_before_utc": "<last manual requestful completion plus 900 seconds>"
}
```

`not_before_utc` may be omitted when the prior manual gate has elapsed. Disable
manual acquisition before enabling backend ownership. The plan and output must
be relative basenames within this protected directory; symlink escapes fail
closed. Use a new output name for a different plan. Missing or disabled config
makes no count calls and preserves normal discovery.

The prepared 250-reference plan embeds three exact reuse proofs, so copying
that unchanged plan is sufficient. It does not execute or read private operation
paths recorded as archival provenance. New plans are limited to 250 references
and 250 documented `GET /listings/{id}/reviews` requests, each with `limit=1`,
zero offset and fixed historical bounds. Targets, predictions, rank and provider
metrics cannot be acquisition inputs.

## Durable execution and limits

The same 900-second requestful completion gate is rechecked after acquiring the
native lease. The discovery source owner copies that exact completion gate into
its shared source-pass control, preventing its other callers from starting a
normal pass while research is waiting. A busy or paused source retries through
the existing minute worker; no new timer is created.
Both native and sales pause controls are checked before acquisition
and before every request. Approval and quota remain the existing Client's own
per-request checks. A turn already busy or paused at preflight does not rewrite
collector state or consume a slot. Existing lower Client limits are preserved.

The collector marks each dispatch before calling the Client. Uncertain dispatch,
denial or contradictory data halts acquisition with an unknown value; it cannot
silently retry that call or substitute zero sales. A valid reported zero review
count requires an empty response and a known-zero recent review subset. Positive
counts require a matching listing/shop sample with valid timestamp and rating.
Raw review text and buyer identifiers never persist.

Count results and exports retain the original collector contract. Backend gate
and sanitized pass metadata are separate files. Requestful state and the gate
are finalized while the native lease is held; collector pass history provides
a fallback if a later backend metadata write fails. Closing the Client and
native collection continue through classified acquisition failures.

Completion writes immutable `counts-by-reference.jsonl`, `terminal-state.json`
and `counts-completion.json` with their hashes. The eight-field count rows remain
compatible with the frozen offline experiment. No fitting or activation occurs
in the backend. Whole research files and earlier immutable outputs are retained.

The app health snapshot contains only sanitized count status, request count,
progress and retry time. It does not expose plan paths, source rows, account
identities or provider bodies. Source tests cover the full 250-reference fake
acquisition, restart gates, pause and lease races, uncertainty, exceptions,
bounded quotas, file boundaries and ordering before the normal native cycle.
Actual installation and live verification belong in the desktop handoff.
