# Dated API-reported shop-review inputs

Updated October 30, 2026. Collection retains numeric fields already
returned by the approved Etsy listing/shop requests. It does not add requests,
change schedules, activate a prediction model or establish product-sales accuracy.

The public shop cache now retains validated `review_count`, `review_average` and
the shop creation timestamp. Account identifiers, contact details and other shop
content remain excluded. Missing or malformed values are omitted; a returned
numeric zero remains zero.

New estimator evidence names these attributes explicitly:

- `shop_review_count_reported`, `shop_reviews_basis='api_reported_period_unverified'` and the shop response's
  `shop_reviews_observed_at` timestamp;
- `shop_review_average_reported`, when valid, with the same basis and timestamp
  even when only the average was returned;
- `shop_created_at`, when a valid creation timestamp was returned.

[Etsy's official OpenAPI schema](https://www.etsy.com/openapi/generated/oas/3.0.0.json)
describes `Shop.review_count` as past-year reviews. A bounded October 30 count-only
probe returned 95,811 available reviews through a fixed cutoff: 6,094 in the
explicit recent 365-day slice plus 89,717 older reviews. Omitting the minimum date
with the same maximum returned the same 95,811. The earlier raw Shop counter was
95,805, observed about 16.5 hours before that probe. This is evidence of a
documentation/runtime basis disagreement for that shop, not proof that every
shop's reported count or rating has a lifetime basis. The review collection count
is independent of page size according to Etsy's
[pagination contract](https://developers.etsy.com/documentation/essentials/urlsyntax/).

The collector therefore does not assign an annual or lifetime period. The shop
sold counter is cumulative with unverified order/unit semantics; its ratio with
these reported fields is not established lifetime review propensity. No new
count probe runs automatically, and these attributes do not replace the existing
review scenarios or activate a model.

Raw cache keys remain `review_count` and `review_average`. Existing caches and
historical evidence are preserved. October 29 captures and frozen model inputs
retain the legacy `shop_reviews_past_year`, `shop_review_average_past_year` and
`past_year` names with unchanged numeric values; their period interpretation is
disputed, not retroactively relabeled. New captures omit those annual-named
attributes; no current consumer requires a compatibility alias. Old records missing these
attributes remain unknown until normal permitted refreshes capture new values.
No cache reset or historical backfill is performed. The batch/cache integration
test verifies that three products still require only two requests, then none on
cache replay, including zero, missing count and average-only cases. A preservation
test keeps a legacy capture when neutral attributes arrive at the same timestamp.
No `shop_reviews` lifetime observation or private seller/reviewer data is created.

Installation state, exact revisions, backup/restore receipts and operational
verification belong in the desktop repository's canonical `docs/CURRENT_STATE.md`.
