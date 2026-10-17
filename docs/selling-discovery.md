# Automated selling-product discovery

October 16, 2026. Local private feature; source access and commercial accuracy
remain separate from software validation.

**October 17 update:** the documented developer mailbox now contains a response
permitting the proposed documented listing/image/review/shop API research within
existing quotas and denying automated unsupported listing-page purchase-message
collection. Protected authorization records only API scopes; `listing_pages`
stays absent. The proof's January 15, 2027 date is an internal operator review
date, not a provider-stated expiry. Receipt is protected outside Git under the
sales-intelligence operation. A successful source pass must still be observed;
an approval file is not evidence that live collection has succeeded. The access
investigation paragraphs below describe the October 16 starting state.

The backend incrementally reads the installed native catalog in SQLite read-only
mode. Its cursor and deduplicated working index live beside the validation ledger
in `selling-discovery/discovery.sqlite`. The first pass starts at the latest
10,000 observations; batches are at most 5,000. Further passes run every minute
inside the backend, and follow new observations. This is a recent working index,
not an assertion that the entire historical catalog has been indexed.

`GET /api/selling-products/discovery` supports literal search, evidence filter,
and 20-row pagination. Records include original capture times, source references,
prices and missing-value disclosures. Search ranks fresh purchase reports first,
then dated review activity, then latest catalog observations and favorites.
Favorites are a supporting signal, never a sales count or validated demand.

`POST /discovery/refresh` queues a bounded backend pass. A process-level OS lease
prevents overlapping passes. Restart marks unfinished runs interrupted. Local
catalog ingestion makes no marketplace requests and never changes the source DB.

`POST /discovery/{listing_id}/investigate` uses an evidence fingerprint and a
deterministic opportunity ID. Repeat selections do not create duplicate research.
It copies dated evidence into the existing private revisioned ledger and opens
the five-method research, sales model, original brief and production handoff.
Future feed changes append/update source evidence. Existing authored briefs
become stale through their original evidence-fingerprint check. The collector
never authors a derivative artwork or publishes a product.

## External source access

Etsy's [API terms section 5](https://www.etsy.com/legal/api/) address automated
analytics and collection authorization; its [general terms section 6C](https://www.etsy.com/legal/terms-of-use/)
also address crawling. A functioning API credential is not written authorization
for the new use case. No such approval was located in the current project records.
The Etsy browser session checked October 16 belonged to the separate seller identity;
its developer dashboard showed no registered application. The known developer
app belongs to another identity. This check does not prove that no approval exists.

The protected proof file is `selling-discovery/etsy-authorization.json`, outside
Git and outside any public endpoint. Only an operator with actual written Etsy
approval should create it, with the approval's real scopes and expiry:

```json
{
  "issuer": "Etsy",
  "reference": "Actual written authorization reference, not an API key",
  "issued_at": "ISO-8601 timezone-aware issue time",
  "expires_at": "ISO-8601 timezone-aware review/expiry time",
  "scopes": ["listing_api", "listing_pages", "shop_api", "listing_reviews"]
}
```

No proof is generated automatically or accepted from the browser. Missing,
malformed, future-issued or expired proof leaves external collection off and is
shown in the UI. The request in `docs/etsy-analytics-authorization-request.md` was
sent October 16 from the documented developer mailbox with explicit user approval
and verified in Yahoo Sent. A written Etsy response is still pending. Sending the
request does not authorize collection or change the protected access proof.

With appropriate scopes, a source pass runs at most every 15 minutes, samples
at most three due listings and makes at most 15 combined API/page requests. It
shares the native `worker.lock`, native request ledger, rolling 4,000-request
ceiling, 20% provider reserve and persisted backoff. Existing pauses remain
effective. It never creates a Codex automation or Windows collection timer.
Selected research listings get priority; successful checks cool down six hours,
failed checks 24 hours. Scope expiry is rechecked before every HTTP call.

The API adapter supports public listing details, images, shop-wide sales counters
and up to 25 listing reviews created within 30 days, using the documented
`min_created` filter. These are samples, not a complete review archive. Shop
`review_count` is not imported as lifetime reviews because its reporting window
is not interchangeable with lifetime shop sales. Field names/endpoints were
checked against the [official reference](https://developers.etsy.com/documentation/reference/).
Only numeric listing/shop IDs and fixed Etsy HTTPS hosts
are used. Credentials go only to the API host, never public pages. Redirects are
not followed, responses are bounded, and 401/403/429 or challenges stop a batch.
No proxies, hidden APIs, captcha solving or paid services are used.

The public-page extractor accepts one canonical listing and a recognized English
purchase message inside its main cart region. Recommendations, scripts, hidden
nodes, contradictory messages and unsupported markup produce unknowns. It keeps
the original wording, count, unit, precision, time and rolling window. English
markup support is fixture-tested; a permitted live HTML capture has **not** been
verified, so future live markup repair may be needed. API integration fixtures
likewise do not establish real source access or current payload compatibility.

Reports remain fresh for the shorter of 24 hours and their stated window.
Overlapping messages are not summed. Buyer counts stay buyers; unknown units
never become orders. Review publication within 30 days is shown separately and
does not date a purchase. Shop totals remain shop-wide net counters.

The working index retains at most two observations per non-message metric/source,
30 messages per source and 50 reviews per listing. Originals in the source catalog
and evidence already promoted into private research are preserved. No cleanup
deletes original catalog, authored briefs, existing records or backups.

## Verification and remaining external work

Backend integration tests cover cursor catch-up/idempotence, original DB
preservation, malformed/future records, current-window expiry, buyer units,
review separation, promotion, stale briefs, access expiry, scoped HTML, shared
reserve, denial backoff, crash recovery, private routes and image hosts.
Browser regression tests use isolated synthetic fixtures, never the real ledger.

Before describing this feature as finding currently selling competitor products,
obtain the appropriate access, verify real payloads and visible messages, and
observe successful collection of fresh purchase reports. Even then the messages
are source-attributed activity, not access to unrelated sellers' transactions.
Exact listing orders require authorized seller records. No numerical model can
make unavailable exact transactions observable.
