# Shop-counter anchored allocation

Implemented October 27, 2026. This experimental lane estimates the distribution
of a measured public shop-counter change across products. It is **not validated
product sales**, and it does not replace the existing review scenarios or fit
against the spent eMarketInsight test panel.

## Evidence and collection

The normal backend collection pass retains exact-ID reviews, listing metadata
and dated shop counters. New captures retain the public numeric shop ID and
`listing_active_count`. A bounded pilot adds one public active-catalog request
per normal pass, for at most twenty shops with 1–30 active listings, at most once
per shop per day. It uses the existing approval check, native lease, request
accounting, free shared rolling allowance and forty-request pass cap.

Only the documented public `/shops/{shop_id}/listings/active` endpoint is added.
No private inactive/draft inventory is requested. A valid one-page response must
contain the reported number of distinct products from the exact shop. Public
fields are allowlisted. This point-in-time snapshot is never treated as a complete
historical/custom catalog. Previously captured identities survive removal from
the active catalog; their historical evidence is retained. Catalog-only captures
do not displace tracking pins. Large/unknown catalogs remain incomplete.

The [official API reference](https://developers.etsy.com/documentation/reference/)
documents this API and the shop counter field. The field name alone does not
establish an interchangeable count of orders, buyers or item units.

## Numerical contract

`shop_allocation.allocate` is pure standard-library Python. Integration groups
products using exact numeric shop IDs or canonical source shop URLs, never a
display name alone. Conflicting identity remains unknown. Evidence must have
been available by the requested cutoff. Repeated counter readings are deduplicated
by timestamp. Conflicts, missing/invalid values and decreases break the usable
chain. The latest monotone chain must span at least 24 hours, end within seven
days, and use actual endpoints within a thirty-day history. It is not linearly
interpolated or projected into thirty-day sales.

For an observed increment D, latent product allocations and an unobserved category
are constrained to be nonnegative and sum to D. Reviews are assumed to follow a
Poisson detection model, with a fixed review probability and delay in each
scenario. Complete observed review windows determine exposure; incomplete
coverage is unknown. Delayed scenarios are right censored at the cutoff, rather
than inventing future reviews. Repeated overlapping windows do not add duplicate
events; different events sharing a timestamp retain their multiplicity.

A Dirichlet shrinkage prior prevents sparse reviews from assigning the entire
shop total to one sampled product. The constrained posterior mode is computed
with a deterministic scalar Lagrange-root solver. Default sensitivity crosses
review probabilities 2%, 10%, 30%; delays 0, 7, 14, 28 days; and unobserved prior
shares 25%, 50%, 75%. These are assumptions, not measured Etsy rates. The central
scenario uses 10%, zero days and a 50% unobserved prior. The resulting unobserved
allocation is learned conditional on that scenario, not forced to equal its prior.

Each of the 36 scenarios reconciles to the same D. Marginal minimum/maximum
endpoints need not sum to D because they can come from different scenarios.
Without independent product counts the full feasible product range remains
zero to D. With no positive product signal, product values remain unknown and
the observed change stays unassigned. A zero counter change is described in
counter units only. Stock decreases never become sales; inactive status cannot
erase historical sales. Engagement is permitted only as a small, explicitly
time-aligned prior adjustment; unaligned cumulative engagement is ignored.

Learning from group totals is an established approach in
[aggregate-observation research](https://papers.nips.cc/paper_files/paper/2020/hash/5b0fa0e4c041548bb6289e15d865a696-Abstract.html).
This implementation is an explicit probabilistic allocation model with fixed
sensitivity assumptions, not a trained reproduction of another provider or proof
that product-level sales are identifiable from public data.

## Application integration

The existing backend estimate job rebuilds the materialized report locally;
there is no new timer, background process, subscription or Codex automation.
`GET /api/sales-intelligence/anchored` returns the saved shop reports, product
allocations, real measurement intervals, unobserved allowance, issues and evidence
priorities. Existing estimates and listing comparisons include the separate lane.
Selling → Sales intelligence → Estimates → **Shop-anchored allocations** exposes
the report with its assumptions and unknown states.

The original `value` and review-scenario semantics remain intact. This model is
never presented as a calibrated purchase forecast or an activated outcome model.
Current evidence priorities can affect the order and delay of normal eligible
collection, while preserving the existing quota and scheduling safeguards.

## Validation and the pilot

First estimates are frozen immutably for each model/product/shop/exact window,
with source fingerprints and cutoffs. Independent actual-outcome evaluation
requires a separately verified counter-unit mapping, exact matching product,
shop and period, seller provenance/attestation, and label availability after the
freeze. Provider estimates and reconciled shop totals are not outcome labels.
No matching labels means accuracy remains unknown. Existing provider comparison
and actual-outcome model lanes remain separate.

Run the pilot for 30–60 days to accumulate longer intervals and changing catalog
observations; elapsed time does not establish sufficient evidence or accuracy.
Before tuning any assumptions, freeze a development/validation plan and reserve
new shops and later dates. Review propensity and lag require external calibration;
they are not freely identifiable from a handful of public reviews. Consenting
external sellers can supply redacted matching records; the app owner need not
have products. Assess count MAE, WAPE, positive-count ±5% agreement, zero cases,
coverage and abstentions separately. At low volumes ±5% may require an exact count.

Synthetic tests verify mechanics, counter reconciliation, controlled recovery,
censoring, conflicts and failure states. Archive replay tests whether the saved
evidence can support this pipeline. Neither is an actual-sales accuracy result.

## Operations

No schema upgrade is required: this additive lane uses existing evidence,
snapshots and protected control records. Source code, immutable private runtime
and public site are distinct states. The desktop `docs/CURRENT_STATE.md` records
the exact installed revision, encrypted preservation and dated live checks.
Rollback uses the retained previous runtime and manifests; it must preserve new
evidence and snapshots. Never reset a database to roll back an estimator.
