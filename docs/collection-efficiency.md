# Collection efficiency — October 25, 2026

The user's free-only maximization request improves evidence per counted request,
coverage and source quality. It does not establish actual-sales accuracy, connect
seller orders or activate an outside provider. The existing 2%/10%/30% review-rate
assumptions remain explicitly uncalibrated. Source, installed app, native
collector and public deployment are distinct; see the desktop CURRENT_STATE for
the installed commits and dated live results.

## Quota and schedule

Both the app adapter and matching immutable native collector use the same
`feed_etsy_requests` ledger. All attempted calls, including failures and uncertain
dispatches, count before contacting Etsy. The rolling ceiling remains the smaller
of 4,000 requests and 80% of the observed provider allowance. At a 4,000 ceiling,
2,000 requests are reserved for product/review research, 1,500 for keyword work,
and 500 are shared headroom. A lane can borrow shared headroom but cannot consume
the other's unused guarantee. Guarantees scale down with a smaller provider
limit. Existing requests are classified from their original batch IDs; no ledger
or reserve is reset. During the first rolling day, earlier keyword usage can
temporarily prevent new keyword calls until those attempts age out. Google
discovery, watchlists, keyword data and existing retry/attention states remain.

The backend retains the 15-minute source gate and native OS worker lease.
Supplemental collection receives a turn before a long native cycle starts.
Each source pass selects at most 20 direct products, with a maximum of 40 counted
requests at one request/second or a slower observed provider limit. Pages, batch
fallbacks and errors consume the same allowance. This is a ceiling, not a
throughput guarantee. Deferred work resumes through the existing backend worker;
no Codex automation or Windows collection timer is added.

## More evidence per response

The documented `/listings/batch` endpoint retrieves up to 25 due IDs per request,
with `Images` and, when permitted, `Shop` associations. The API supports 100 IDs;
the local bound leaves room for safe response-size validation. Exact requested
identities are checked. A counted 400/404 batch failure permits bounded individual
fallback; a 400 disables further batch attempts for six hours. 403/429 responses
never trigger an alternate route or hidden retry. All authorization, body-size,
backoff and daily gates remain in force.

Listing responses are cached for one hour and public shop fields for six hours.
Cached observations retain their actual capture times. Cached/batched image and
shop associations avoid repeated separate lookups. Batched listing features are
also retained in the existing allowlisted request-history bridge, without extra
HTTP calls. Price, stock and shop sales remain observations, not listing orders.

When a verified shop ID is available, one shop review window supplies each exact
listing ID within it. This avoids repeating an empty listing-review request for
every product. Up to 20 newly reviewed IDs can join the panel per response;
already tracked products also receive their matching evidence. No parent product's
price, views or review count is assigned to another listing.

## Complete, resumable review windows

Review jobs fix a 30-day cutoff and persist successful pages. They process at most
four pages per shop turn, resuming at the next normal pass. Complete and invalid
windows are cached six hours; an unfinished window can resume for up to seven
days without moving its cutoff. Busy date intervals split into non-overlapping
segments before API offset ceilings. A job is locally bounded at 10,000 reviews;
exceeding that bound remains unknown rather than asserting completeness.

Counts, identities, shop IDs, dated ratings, page consistency and event hashes
must agree. Duplicates, inconsistent counts, malformed rows, truncated work and
unsupported responses cannot produce a complete-window purchase scenario.
No raw buyer IDs or transaction IDs persist in the cache or estimator. Public
review text remains protected research evidence; transaction identifiers can
contribute only to an irreversible local deduplication hash. Complete refers to
the bounded API response, not proof that every purchase receives a review.

## Coverage and quality

The working panel targets 200 products, with a hard cap of 600 including pins and
review-led discoveries. Up to 20 diverse catalog candidates join per source
pass. Selection mixes popular candidates with a stable daily sample and a
keyset walk through older saved catalog pages; it does not scan all packets.
Ordinary candidate selection limits concentration per known shop. Existing pins
remain; a user pin can replace an unpinned member when the panel is full.

After seven days, up to 20 older unpinned members rotate, prioritizing quiet/lower
scenario products. Retired memberships are archived; no historical evidence,
estimates, authored opportunity or research record is deleted. Ordinary catalog
selection avoids recently retired IDs for 30 days. Recent review evidence can
identify a product again. This panel is not a representative market sample.

Products with recent reviews become eligible after six hours, quiet products
after 24 hours, pending pagination after 15 minutes, and known inactive products
after seven days. Collection errors retain a 24-hour cooldown. Listing state,
materials, personalization, description and update timestamp are retained when
returned. Known inactive/sold-out/removed/expired/draft listings have no current
sales estimate; their historical review scenarios remain inspectable. Unknown
listing state is not invented.

## Storage, inspection and verification

The existing intelligence schema remains version 5. A separate
`selling-discovery/collection.sqlite` stores cache, resumable jobs, queue control
and retired memberships. Older runtimes can ignore this file; rollback does not
require overwriting the research archive. Preserve it alongside estimator state
for a complete continuation of pagination and panel rotation.

`GET /api/sales-intelligence/estimates` exposes panel limits, source cadence and
`collection_metrics`: review-job states, retired memberships and the last
successful pass's counted calls, completed direct checks, cache/association hits
and quota allocation. These are operational measurements, not accuracy scores.

Isolated adapter tests verify three products in two requests, zero-request cache
reuse, matching-ID review evidence, privacy allowlists, resumable 550-review
pagination, split date ranges, duplicate/mismatched/inconsistent rejection,
reserved lane budgets, inactive-listing suppression and preserved panel history.
The existing estimator, source, browser and keyword regressions still apply.

Official contracts: [Etsy API reference](https://developer.etsy.com/documentation/reference/),
[rate limits](https://developer.etsy.com/documentation/essentials/rate-limits/),
[pagination](https://developer.etsy.com/documentation/essentials/urlsyntax/).
