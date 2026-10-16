# EtGen sales model v1

Implemented October 16, 2026. Open /selling, select an opportunity, then Sales
model. Existing research, improvement briefs and production handoffs remain.
This is a private model over permitted evidence. It adds no paid dependency,
marketplace collector, external requests or collection schedule.

## Outputs and units

Each listing has rolling 7/30-day estimated purchases, provisional scenario ranges,
supported/extrapolated days and contributing evidence families. Original purchase
messages and shop-counter changes remain alongside estimates. Buyers, units and
purchase events are different. Source attribution is not independent verification.

The English parser recognizes N[+] [people] bought [this] in the past/last H hours.
It never parses carts, favorites or bestseller badges as purchases. Validation
checks count, bound, unit and window against the raw message. Buyer conversion
requires an explicit purchases-per-buyer assumption; there is no default. Lower
bounds remain evidence and never become exact anchors. Outcomes are attested
listing purchase counts with source references and no buyer PII, not unit counts
or another tool's estimates.

## Versioned calculation

1. Collapse equal readings by metric, scope and timestamp. Conflicts, missing
   values and lower-bound counters become unknown. Counter decreases are disclosed.
2. Select newest nonoverlapping purchase windows. Allocate convertible counts
   proportionally across daily bins; within-window timing is a modeling assumption.
3. Calculate review-counter increments. Use an explicit review probability or a
   recent same-timestamp shop-reviews/shop-sales lifetime proxy between 0 and 1.
   Spread inferred purchases backwards using a uniform assumed lag distribution.
   Defaults 0–180 days are provisional, not Etsy's eligibility rule or a fitted
   delivery distribution. Selected review excerpts are not a complete review feed.
4. Convert view increments only with an explicit conversion assumption. Lifetime
   views never directly become recent sales. An optional comparable daily baseline
   defaults to unknown; twelve seasonal multipliers default to neutral 1.
5. When fitted, the multivariate model jointly uses views, favorites, reviews,
   shop growth, carts, stock level/drop, price/currency, purchase messages by unit,
   category, product type, age, month and keyword demand. Missing indicators retain
   unknowns. Categories are regularized. Historical listing metadata must reflect
   the calibration window; its authenticity is operator-attested.
6. Collapse each evidence family once per bin. Exact convertible messages anchor
   their fraction of the bin; the median available family rate fills the remainder.
   Otherwise use that median. Repeated imports/providers add no family votes.
   Provider estimates stay separate benchmarks in the existing research methods.
7. Require daily estimates for at least 3/7 or 14/30 days before extrapolating
   missing bins using the mean supported rate. Disclose missing days. Explicit
   baseline-only scenarios retain zero evidence coverage.
   Clip the modeled history to the declared creation date (UTC midnight); partial
   days contribute proportionally. Never extrapolate into pre-listing history.
8. Scenario error is the maximum of 1 purchase, uncovered equivalent days, and
   total × [0.25 + 0.5 × missing-coverage fraction] + family disagreement scaled
   to the window. A fitted model's held-out residual envelope can widen it. These
   are heuristic sensitivity ranges, **not confidence intervals**. Thresholds and
   constants are provisional design choices; no accuracy percentage is claimed.
9. Compare estimates against shop-counter changes on matching fully covered
   intervals only. Excesses surface as scope/cancellation conflicts. Never force
   equality or allocate the entire shop total to its sampled products.

## Opportunity rating

Score = 100 × demand × persistence × improvement × accessibility. Missing factors
leave it incomplete. Demand uses log-scaled monthly estimates with a 300-purchase
reference. Persistence uses distinct positive purchase-message days with a 14-day
reference. Improvement uses repeated product/offer concerns with a three-theme
reference; fulfillment themes are excluded. Accessibility is 1−HHI across at least
three named shops with weekly modeled activity. These are v1 sample-ranking
heuristics, not a marketplace census or probability of success. Patterns remain
inspectable in the existing design method and briefs. Google metrics and keyword
overlap do not receive sale-attribution credit. Rights flags remain advisory.

## Calibration, evaluation and preservation

Use Seller outcome or calibration CSV/JSON to record at least 32 completed cases
across eight identified shops. Listing outcome windows cannot overlap. Choose a
deterministic eligible time split near a 25% test share: at least sixteen earlier
training cases, eight later test cases and two test shops absent from training.
This is a single held-out evaluation, not cross-validation or proven generalization.

Fit log1p(daily purchases) with ridge regression: intercept penalty 0.01, other
coefficients 2. No outcome counts, seller-reported sales or vendor estimates enter
predictors; observations after a case's period end cannot enter that case's
features. At most twenty categories per calibration. Report held-out daily MAE
and training-median baseline MAE, including zeros. Activate only when strictly
better than baseline. Synthetic tests establish behavior, not live accuracy.

Revisioned selling_model_config/artifact records retain assumptions, coefficients,
version, training fingerprint, split and per-case test results. Listing, observation
or outcome changes make the fitted model stale/inactive until refitted. Model
changes invalidate brief freshness via the existing evidence fingerprint.
Imports are bounded, atomic and idempotent; corrections retain revisions. Private
exports retain model outputs/artifacts, source records and a checksum. A checksum
verifies integrity, not source authenticity. Reimport restores evidence; assumptions
and trained artifacts must be reviewed separately, not silently activated.

## API and operation

- POST /api/selling-products/parse-purchase-message: {message}.
- POST /api/selling-products/opportunities/{id}/model-config: {expected_fingerprint, config}.
- POST /api/selling-products/opportunities/{id}/calibrate: {expected_fingerprint}.
- Existing preview/import supports calibration cases and expanded observations.
- Detail/export includes analysis.sales_model; overview includes model status/score.

Existing operator authentication and private/no-store handling apply. Analysis is
recomputed on private reads; fitting is explicit. The model does not expand Etsy
analytics authorization or acquire unobserved fields. Source acquisition and live
calibration remain operational requirements separate from model implementation.

Verification: tests/test_sales_model.py, the full backend suite and
scripts/test-selling-products-ui.mjs cover numerical windows, unit preservation,
lag, missing/conflicting data, stale models, held-out leakage, imports/authentication,
keyboard operation and 320/768/1024/1440 layouts plus original PDF handoff.
