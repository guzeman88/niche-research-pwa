# Automatic EtGen estimates

Implemented October 24, 2026. This closes the connection between permitted
scheduled Etsy collection and the existing `etgen-sales-v1` engine. It does not
claim measured purchase accuracy or change the actual-outcome training gates.

## Workflow

Open Selling → Sales intelligence → Estimates. A stable panel of 30 products is
selected automatically from at most 1,000 recent discovery candidates: an initial
popular subset followed by stable ID-hash selection, with at most three per known
shop. This deliberately includes quieter listings, but is not a representative
market sample. Users may add discovered IDs up to a total cap of 60. This does not
create opportunities or overwrite authored research/configuration.

The existing backend source scheduler refreshes at most three due listings per
15-minute pass, rechecking successful products after six hours and failures after
24 hours. One authored opportunity retains first priority, with remaining slots
for the persistent panel, ordered oldest-due first. The shared native quota,
reserve, lock, pauses, request ledger, authorization and HTTP backoff remain in
force. A source pass uses at most 15 requests. Increasing panel size reduces
refresh frequency when the free quota is exhausted; it never buys more quota.
The intelligence pause stops panel requests and calculations; independent saved
opportunity collection retains its own existing controls.

Documented listing reviews are requested for a bounded completed 30-day interval,
up to 100 rows. An empty listing response can fall back once to documented shop
reviews, matching each review's exact listing ID. No unrelated shop reviews are
assigned to the product. This stays within the same 15-request budget. Original
API permission is checked for each request. No HTML purchase messages are read.

A complete shop-review response can also supply exact-ID review windows for up
to three other products. The panel adds these within its
60-product cap and prioritizes their next due metadata check. Unknown products
retain empty titles/keywords until public details are obtained on the regular
API schedule; a real seller tag/title can then seed research without claiming
measured buyer demand. Related reviews never become
reviews or purchases of the original product, and primary listing prices/views
are not copied onto related products. This reuses the same response without
additional requests and helps find review activity beyond the initial panel.

## Calculation and limits

Allowlisted numeric observations and review timestamps enter a separate private
evidence table. Buyer IDs, raw transaction IDs, review text and secrets do not
enter this table. Existing public review excerpts remain in discovery/research.
Price, favorites and stock alone never become purchases. The existing engine
uses observed counter history when its necessary conversion evidence exists.
Shop `review_count` covers the past year, so it is not divided by lifetime shop
sales as if the periods matched.

When the API response is usable, the same engine also computes an **uncalibrated
review scenario**. Daily counters are reconstructed locally from the bounded
review window, including quiet days; they are not declared lifetime counters.
The scenario explicitly assumes one review per purchase, zero delay between
purchase and review, and review probabilities of 2%, 10% and 30%. These are
versioned design assumptions, not measured Etsy rates. The central result uses
10%; the low/high sensitivity results use 30%/2%. This is not a confidence
interval, nor an actual count of purchases in the displayed review period.
Digital/physical fulfillment, review delay and different review rates can make
these scenarios substantially inaccurate. No conversion from units to orders is
established by this calculation.

Completeness requires a valid response count equal to the returned row count,
fewer than 100 rows, matching listing identities, valid dated ratings and no
duplicate/out-of-window rows. It describes the bounded API response, not proof
that Etsy exposes every review or every purchase. A full page, unknown count,
wrong identity, malformed timestamps or duplicates keep the estimate unknown.
No recent reviews also leaves purchases unknown; it does not produce zero sales.
Evidence older than seven days cannot retain a current estimate. Historical
cutoffs exclude evidence captured or available later; old review windows never
advance just because the worker ran again.

Calculations run locally in the app's minute worker and require no provider
lookup, model fitting or teacher labels. Provider/student/actual-outcome models
remain separate. Results are retained in a small latest table and deduplicated
daily/source-version snapshots, with input evidence IDs, assumptions, capture
time, model version and unvalidated accuracy status. Unknown products remain in
the panel with their last collection status. Product selection returns to the
existing comparison/investigation/brief/production workflow.

## Storage and verification

Archive schema 5 adds three small estimator tables and one listing-history index.
Existing metadata, reference, outcome, model and authored-ledger rows are
preserved. Use the matched pre-upgrade backup with an older schema-4 runtime;
that runtime correctly refuses the newer schema rather than silently editing it.

`tests/test_automatic_estimates.py` covers collector-to-engine-to-private-API
behavior, numerical 7/30-day scenarios, no-reference operation, zero/missing/
truncated/duplicate/wrong-listing reviews, shop fallback identity, stale/as-of
behavior, idempotence, panel cadence, pauses and operator authentication. Browser
regressions cover estimate display, filtering, queued recalculation and mobile
overflow alongside existing comparison and investigation workflows. Synthetic
checks establish software behavior, not Etsy sales accuracy.

Official endpoint contract: [Etsy API reference](https://developer.etsy.com/documentation/reference/#tag/Review).
The purchase accuracy milestone still requires independent authorized seller
outcomes. Provider estimates may help compare models; they are not required to
run this original estimator and do not establish its accuracy.
