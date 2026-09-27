# Automated keyword validation

EtGen collects bulk keyword evidence without browser automation or model calls.

## Scheduled cycle

1. Up to 500 library seeds are sent to the official Google Ads Keyword Planner API in groups of 20.
2. The cycle keeps at most 50,000 unique, non-IP-risk keyword ideas.
3. Historical metrics are requested in batches of up to 10,000 keywords.
4. Exact monthly searches, 12-month series, competition index, CPC, and bid ranges are stored in the evidence database.
5. Existing Etsy Open API listing counts and samples are joined at scoring time without changing their provenance.
6. A deterministic report shortlists 200 keywords, 25 niche clusters, and 5 finalists.

The scheduler checks every six hours. Google Ads metrics and idea expansion refresh every 30 days because the provider updates historical metrics monthly. A CLI/cron run is also available:

```powershell
python backend/scripts/run_keyword_validation.py
```

Use `--force` only for testing because Google enforces a 1-request-per-second planning-service limit and account-level daily quotas.

## Score

- Demand: 35%
- Etsy marketplace competition proxy: 25%
- Twelve-month search trend: 20%
- Google commercial intent: 10%
- Exact product contribution margin: 10%

The report includes a normalized screening score when some inputs are missing. It only emits a complete score when all five components exist, and only marks a keyword validated when at least ten Etsy listing samples are also stored.

## Provider limits

- Historical metrics: 10,000 keywords per request.
- Keyword ideas: 20 seeds and at most 10,000 results per page.
- Planning services: 1 request per second per customer.
- Daily operations: determined by the Google Ads developer-token access level.
- Etsy: app-specific QPS/QPD returned by provider headers; EtGen retains a 20% daily reserve by default.

Marketplace Insights is not scraped. Google Ads uses the supported API, and Etsy data uses the approved Open API.

## Controlled candidates before volume is connected

`test-candidates.json` is generated from the same atomic keyword snapshot as the
dashboard. The `etgen-test-portfolio-v1.0.0` model uses exact Etsy listing
counts, observed prices, sample depth, source strength, keyword specificity,
and explicit safety rules to decide which controlled experiment should run
first.

These are test-priority scores, not opportunity or profitability scores:

- Marketplace-only candidates are capped at **65/100** and labeled
  `provisional_marketplace`.
- A cluster becomes `demand_screened` only after it contains at least 10 related
  keywords, 1,500 combined monthly searches, five keywords with at least 100
  searches/month, and no more than 10,000 median Etsy listings.
- Obvious protected properties, retailer-navigation queries, regulated terms,
  volatile daily-trend names, and non-product intent are excluded before
  ranking.
- Every candidate contains exactly six product experiments and a 30-day test
  plan. It advances only after at least 1,000 impressions, 1.5% click-through,
  three orders, and positive contribution profit are recorded.

The Store Generator falls back to this portfolio when no fully validated store
ideas exist. Etsy Shop Stats exports and exact listing outcomes are recorded in
Evidence Operations. Missing search volume, economics, or outcomes remain
visible blockers; the application never fills them with estimates.
