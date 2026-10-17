# Private sales intelligence

Implementation date: October 17, 2026. Source code, installed runtime and live
data acquisition are separate states. Read the desktop `docs/CURRENT_STATE.md`
for installation hashes and dated operating evidence.

## What it does

The collapsible Sales intelligence workspace on `/selling` adds comparison,
opportunity ranking, coverage, source management, imports and learning beside
the existing discovery, independent sales model and original improvement brief.
Opening a screen spends no provider credits. Unknown sales remain unknown.

The archive preserves original permitted import contents and mappings, typed
observations, corrections, metadata history, durable jobs and quota reservations,
panels, frozen datasets, model artifacts, predictions, an integration outbox and
audit events. Artifacts live in the private SQLite database rather than empty
`raw/` or `models/` directories. No private reference data enters public snapshots.

The registry contains all 24 researched leads. A registry entry or advertised
free quota does not establish an operational feed. At implementation time no
external estimate provider has a verified automated export/API configuration.
No genuine third-party estimate has been collected by this feature. Source
relationships (including SellFinch/EtsiMator) cap duplicate influence; conservative
method groups are not proven independence.

## Paths and access

Default archive: the existing validation ledger's sibling directory
`sales-intelligence/intelligence.sqlite`. An isolated environment may override
`SALES_INTELLIGENCE_ROOT`. Installed data inherits the protected runtime directory.
Schema version 3 has transactional additive migrations, a newer-version refusal,
WAL/full-sync transactions and indexed latest metadata. Back up SQLite through
the existing snapshot API, including its WAL, rather than copying an open file.

The operator-only `/api/sales-intelligence` routes reuse existing authentication,
origin restrictions, response no-store rules and a 2 MB / 2,000-row import limit.
No browser control writes credentials or grants source rights.

`access.json` in the protected archive binds each source ID to `reference`,
`account_ref`, timezone-aware `issued_at` and `expires_at`, `free_only: true`, and
separate `storage`, `comparison`, `training`, `export`, `automated` capabilities.
Expiry may be an explicitly documented operator review date. Preserve actual
supporting evidence privately; never use test-fixture grants in the installation.
Rights are checked again at import, dispatch, dataset construction and inference.

The supported generic network contract is `canonical_json_v1`: an exact documented
HTTPS endpoint on the provider's registered host, with protected `endpoint` and
`endpoint_reference`, returns a canonical observation array (or `observations`
array) for `listing_id`. No researched provider is claimed to support this contract
without verification. This is an adapter extension point, not a collection of
fabricated provider connectors. Credentials, when needed, remain in protected
`credentials.json` as source-scoped authentication headers. Redirects, proxies,
cookie scraping, private-address hosts and hidden HTTP retries are disabled.

## Imports and semantics

Preview canonical JSON or explicitly map CSV. Known headers include Listing ID,
Product ID, Monthly Sales, Weekly Sales, Total Sales, Shop ID and listing URLs.
Choose the exact value column, unit and reporting basis; a weekly/monthly header
does not invent exact boundaries. Duplicate normalized headers, ragged rows,
buyer/credential columns and conflicting source IDs are rejected. Preview hashes
guard commit, the whole batch is atomic and duplicate observations are idempotent.
The original payload remains private. Exports neutralize spreadsheet formulas and
require export eligibility.

Each observation has a numeric Etsy listing ID, source, metric, value or explicit
missing state, sales unit, basis, capture/availability times, original label and
source reference. Exact periods are half-open and completed. Unknown provider
monthly periods, lifetime totals and lifetime averages remain distinct. Revenue
requires currency. `100+` is a lower bound, excluded from point consensus. Booleans,
negative/nonfinite counts, naive/future dates and invented zeroes are rejected.
Corrections name a prior same-cohort observation and preserve as-of history.
Reimporting a correction does not invalidate models again.

The optional protected `imports/inbox/*.json` accepts the same import envelope
(`source_id`, `format`, `content`, explicit mappings). Backend intake validates
stable bounded files, prevents symlink escape and records processed hashes while
preserving originals. Failed exports remain visible as failures. Automated intake
does not automate obtaining an export from a provider.

Actual seller outcomes use a separate two-step JSON import: `listing_id`, display
`shop`, numeric canonical `shop_id`, `period_start`, exclusive `period_end`,
`available_at`, strict integer `actual`, `unit` (`purchases` or `units`),
`source_ref`, and an attestation describing authorized aggregate seller records.
No buyer details. Same-unit windows cannot overlap; distinct units remain separate.
Provider estimates never enter actual-outcome training or existing calibration.

## Scheduling and free limits

The EtGen backend owns the worker. It defaults off on unrelated/hosted instances;
the installed app inherits `APP_KEYWORD_FEED_ENABLED=1` unless explicitly overridden
by `APP_SALES_INTELLIGENCE_ENABLED`. One OS lease allows one pass per minute,
at most five durable jobs per pass, with a 15-minute recovery lease and at most
three interrupted attempts. Local SQLite transient failures have bounded backoff.
Disk below 512 MB stops dispatch. Global and per-source pause are rechecked.

Catalog tail and historical backfill read native observations and bounded saved
gzip API responses without changing that database or making HTTP requests.
Tail/backfill cursors survive restart. Reviews/images cannot become blank listing
metadata. Native request availability uses its recorded completion time.

A reference panel selects up to 30 saved IDs (operator maximum 500), stable ID
hash within the first 10,000 saved IDs and at most three per shop. This is a bounded
catalog sample, not random market coverage. Provider jobs refresh no faster than
24 hours, plan at most two requests per source/pass, and share conservative brand
quota groups. Daily, monthly and one-time allowances retain their actual reset
timezone and expiry. Reservations happen durably before dispatch; unknown failures
remain spent. Restart cannot reset free credits. Sources without a finite verified
free allowance cannot dispatch. The planner never creates paid fallback access.

HTTP 429 Retry-After persists a 15-minute to 24-hour cooldown; access errors wait
24 hours, network uncertainty at least 15 minutes. Failed requests are not blindly
replayed under the same reservation. Health shows successful output, failure and
retry time. External request accounting conservatively counts reservations,
including uncertain dispatch, rather than claiming a completed network request.

Default weekly checks consider separate 30-day purchase student/outcome models;
other 7/30-day units/purchase targets can be queued explicitly. Active-model
catalog prediction refreshes run daily in bounded 100-listing jobs. All work stays
inside the app; no new Windows collection timer or Codex automation is used.

The native supervisor gives due supported Etsy API discovery a bounded turn before
starting another long native cycle. A busy/paused worker retry spends zero requests
and retries after one minute; successful source passes retain the 15-minute gate.
This prevents back-to-back long native runs from starving supplemental discovery.

## Consensus and features

Only eligible point readings with compatible unit/basis/exact windows vote.
One current reading per provider/cohort, one total weight per method group.
The group-weighted median is the center; simple mean, median and min/max remain
visible. Provider update/capture older than seven days is stale. A single group
is labeled single source. Spread describes source disagreement, not a confidence
interval or actual-sales accuracy. Historical charts compare one reporting cohort
by availability time; refreshes are not added sales. The list is the data equivalent.

Feature version `reference-features-v2` freezes only metadata available by the
declared period end: counters and their own dated rates, missing flags, listing
age/type, bounded category/currency buckets and seasonality. Counters older than
seven days become missing. Price/stock changes are not sales-rate counters.
Teacher estimates and outcomes never enter predictors. A shop name alone cannot
enter a shop-held-out dataset; canonical Etsy shop IDs are required. Missing
categories/creation dates are retained as missing, not inferred from titles.

## Model lanes, gates and limitations

The existing independent model and its calibration stay in the opportunity
workspace. Comparison reads saved eligible historical evidence without creating
an empty ledger; conflicting assumptions remain visible rather than averaged.

The consensus student uses log1p regularized ridge over frozen compatible 7/30-day
purchase/unit labels from at least two eligible method groups. Its software guard
is 100 nonoverlapping windows / 20 canonical shops, with at least 40 earlier train,
15 intermediate validation and 15 later test cases on disjoint shops and target
intervals. It must beat the training-median baseline on validation and test MAE.
Metrics include MAE, log MAE, median error, bias and zero coverage. This objective
measures teacher agreement, not actual purchase accuracy.

The separate actual-outcome model fits only attested seller counts. Its guard is
200 windows / 25 canonical shops; at least 80 train, 30 validation and 30 test cases,
with at least five validation/test shops. It also needs at least ten zero cases
in each held-out set, zero mean prediction at most one, absolute bias at most
max(1, 20% of held-out mean actual count), and category slices of at least ten
cases with MAE no worse than max(1, 110% of median-baseline MAE). Gates are fixed
before fitting. These minimums are operational checks, not a claim of general
accuracy. Sparse or mixed results stay unpromoted.

Each lane owns its activation/previous pointer. Automatic replacement compares
the same frozen test IDs and better MAE; unrelated test sets cannot justify an
automatic upgrade. Candidate coefficients are fitted on training only. Failed
training retains active artifacts. Rollback cannot reactivate a stale/ineligible
artifact. Policy/correction/feature changes invalidate affected students; actual
models have a separate outcome epoch. Predictions refuse future cutoffs, models
unavailable at that cutoff, stale metadata and unseen categories/types. No fitted
model or insufficient data returns an explicit unknown. Predictions have no
invented confidence range.

A separate later-outcome audit excludes train/validation shops, requires later
matching-unit windows and verifies canonical shop IDs. Audit results do not turn
a consensus student into an outcome-trained model. Artifacts and results remain
private, versioned and independently inspectable.

## Opportunities and original improvements

The provisional reference ranking compares only recent exact 30-day purchase
windows in the most recent 100 acquired-reference listings. Formula:
`log1p(center) × min(1, method_groups/3) × 1/(1+relative_spread) × freshness`.
Freshness decreases to zero seven days after the window ends. Factors remain
visible. This measures a demand hypothesis, not verified sales, profit, quality
of differentiation, market share or expected commercial success. Other windows,
unknown units and unsupported evidence are excluded rather than forced to rank.

Investigate opens the existing current discovery listing, preserving original
buyer keywords and notes. A historical ID outside that index needs an explicit
buyer keyword in the opportunity workflow. Eligible evidence uses a durable,
idempotent promotion outbox. The older ledger uses inclusive dates: only exact UTC
day-boundary periods convert; unsupported windows remain in the archive and the
outbox reports incompatibility. Provider observation IDs, consensus fingerprint
and active model versions accompany delivered research. Expanded evidence
fingerprints make authored briefs stale when appropriate. No artwork is copied,
listing published or existing keyword-gap qualification changed.

## Verification and operating truth

Focused tests cover semantics, original-artifact retention, correction replay,
canonical holdouts, actual/student lane separation, quota reset/DST/shared brands,
HTTP cooldowns, outbox replay, native read-only bridges, private routes and model
activation guards. Browser tests use an isolated synthetic archive and test grants,
never the installed ledger or real provider credentials. They exercise import,
comparison, history, ranking, investigation, source controls and responsive widths.
`scripts/benchmark-sales-intelligence.py` builds an isolated 100,000-listing /
1,000,000-observation workload and records p95 timings; its data is synthetic.

The full automatic acquisition milestone still requires at least two genuinely
working compatible free provider feeds over repeated scheduled passes. No such
feeds are manufactured by the generic adapter or imports. Demonstrated model
improvement additionally requires real retained outcomes. Keep those milestones
open until live evidence supports them.
