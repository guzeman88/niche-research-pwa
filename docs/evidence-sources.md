# Evidence source operations

EtGen records source-native observations and leaves unknown values null. A
configured connector is not evidence until a dated provider response has been
stored.

## Automatic collection

| Source | Activation | Stored evidence | Refresh behavior |
| --- | --- | --- | --- |
| Google Shopping Suggest | No credential | Exact query, suggestion, returned position, geography, timestamp | Runs in the primary queue; identical phrases returned by several query prefixes are stored once |
| Google Trends | No credential; unofficial `pytrends` client | Complete dated relative-interest series, related queries, and collection context | Independent worker; up to five due keywords share one request and do not delay Etsy collection |
| Google Daily Search Trends | No credential; official public RSS feed | Dated trending query, provider-displayed approximate traffic floor, rank, and linked news records | Independent source cadence; unchanged feed items are recognized rather than stored as new evidence |
| Etsy Open API | Etsy approval plus API credentials | Listing count when returned, up to 100 sampled listings per request, prices, shops, favorites, tags/materials where available | Primary queue paced from live per-second quota and the requests remaining before the UTC daily reset |
| Pinterest Trends | Approved Pinterest business app and token | Ranked current trends, WoW/MoM/YoY growth, one-year weekly relative-interest series | Independent source schedule derived from its configured cache duration, plus exact-keyword queue matches |
| Reddit Data API | Reddit commercial-use approval plus credentials | Exact-query post counts and engagement aggregates with source records | Keyword queue only after explicit approval flag |

The GitHub `Evidence Collector Heartbeat` runs every ten minutes, wakes the
backend, and idempotently starts its continuous queue. It uses a short-lived
GitHub OIDC identity restricted to this repository, the heartbeat workflow,
and the `main` branch; no shared scheduler secret is stored in GitHub.
Completed collection runs sync their raw rows and durable per-keyword collection
state to Supabase when the service-role configuration is present. On restart,
the collector hydrates its queue and last-collection timestamps from Supabase,
so a new deployment does not forget completed work or begin again at the start
of the seed list. After every available keyword has evidence, collection
continues with the oldest-collected keyword rather than stopping.

Every provider attempt also records an operational event and updates a current
provider-state row. These records distinguish successful evidence, valid
no-data responses, unavailable connectors, rate limits, and failures; they also
retain observed yield, request duration, and quota fields when the provider
actually reports them. Provider state never fabricates a missing metric.

`GET /api/evidence/quality` reports the rolling collection rate for each source.
The target band is 80–100%. Etsy is measured against its provider-reported
daily request capacity; keyword sources are measured as completed eligible
keywords divided by scheduled eligible keywords; discovery feeds are measured
as valid feed rows covered divided by rows returned. Useful-yield is reported
separately, so a valid no-data response can complete scheduled work without
being misrepresented as market evidence. Import-only and approval-gated sources
remain `null`/TBD until they have a real schedule or usable access.

## Structured imports

The Evidence Operations page accepts unedited CSV or tab-separated exports for:

- Etsy Marketplace Insights
- Etsy Shop Stats
- eRank
- Marmalead
- Google Keyword Planner
- Google Trends

Marketplace Insights, Shop Stats, and Keyword Planner require explicit
reporting dates. Keyword Planner and Google Trends also require geography.
Currency-dependent values are omitted unless a currency code is supplied.

## Provider limitations

- eRank and Marmalead do not document generally available public APIs. EtGen
  uses imports unless the provider grants a private HTTPS endpoint and key.
- Pinterest Trends access is limited and requires provider approval; an access
  token alone does not establish eligibility.
- Reddit requires a separate agreement for commercial Data API use. The
  connector remains disabled until `REDDIT_DATA_API_APPROVED=1` is deliberately
  set after approval.
- Google Trends is relative and normalized, not absolute search volume.
- Google Daily Search Trends traffic is an approximate lower bound (for example, `20K+`), not exact or monthly search volume; it is retained as discovery evidence and does not create an opportunity score.
- None of these sources proves profitability. Exact product economics and
  observed shop outcomes remain separate required evidence.
