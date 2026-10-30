# Dated public shop-review inputs

October 29, 2026. This additive collection change retains numeric fields already
returned by the approved Etsy listing/shop requests. It does not add requests,
change schedules, activate a prediction model or establish product-sales accuracy.

The public shop cache now retains validated `review_count`, `review_average` and
the shop creation timestamp. Account identifiers, contact details and other shop
content remain excluded. Missing or malformed values are omitted; a returned
numeric zero remains zero.

New estimator evidence names these attributes explicitly:

- `shop_reviews_past_year`, `shop_reviews_basis='past_year'` and the shop response's
  `shop_reviews_observed_at` timestamp;
- `shop_review_average_past_year`, when valid;
- `shop_created_at`, when a valid creation timestamp was returned.

The documented shop review count is a past-year counter. The shop sold counter
is a different, cumulative counter with unverified order/unit semantics. Their
ratio is not established lifetime review propensity and is not used to replace
the existing review scenarios. These fields support explicitly qualified offline
experiments and future synchronized measurements.

Existing caches and historical evidence are preserved. Old records missing these
attributes remain unknown until normal permitted refreshes capture new values.
No cache reset or historical backfill is performed. The batch/cache integration
test verifies that three products still require only two requests, then none on
cache replay; capture retains the new fields without a `shop_reviews` lifetime
observation or private seller/reviewer data.

Installation state, exact revisions, backup/restore receipts and operational
verification belong in the desktop repository's canonical `docs/CURRENT_STATE.md`.
