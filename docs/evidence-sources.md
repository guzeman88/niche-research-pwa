# Evidence source operations

EtGen records source-native observations and leaves unknown values null. A
configured connector is not evidence until a dated provider response has been
stored.

## Automatic collection

| Source | Activation | Stored evidence | Refresh behavior |
| --- | --- | --- | --- |
| Google Shopping Suggest | No credential | Exact query, suggestion, returned position, geography, timestamp | Keyword queue, every 30 days by default |
| Google Trends | No credential; unofficial `pytrends` client | Complete dated relative-interest series and collection context | Keyword queue, every 30 days by default |
| Etsy Open API | Etsy approval plus API credentials | Listing count when returned, listing sample, prices, shops, favorites, tags/materials where available | Keyword queue, every 30 days by default |
| Pinterest Trends | Approved Pinterest business app and token | Ranked current trends, WoW/MoM/YoY growth, one-year weekly relative-interest series | Daily discovery plus exact-keyword queue matches |
| Reddit Data API | Reddit commercial-use approval plus credentials | Exact-query post counts and engagement aggregates with source records | Keyword queue only after explicit approval flag |

The GitHub `Evidence Collector Heartbeat` runs every ten minutes, wakes the
backend, and idempotently starts its continuous queue. It uses a short-lived
GitHub OIDC identity restricted to this repository, the heartbeat workflow,
and the `main` branch; no shared scheduler secret is stored in GitHub.
Completed collection runs sync their raw rows to Supabase when the service-role
configuration is present.

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
- None of these sources proves profitability. Exact product economics and
  observed shop outcomes remain separate required evidence.
