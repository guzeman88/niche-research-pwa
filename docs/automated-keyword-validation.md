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

## Authentication and scheduled operation

New Google Ads integrations are authorized by the Google Cloud project that
owns the service account. Add that service-account email to the Google Ads
account with **Read only** access, which includes planning tools. EtGen accepts
one of these server-side credential forms, in priority order:

1. `GOOGLE_ADS_SERVICE_ACCOUNT_JSON` for a hosted secret store.
2. `GOOGLE_ADS_JSON_KEY_FILE_PATH` for a protected local key file.
3. Application Default Credentials from `GOOGLE_APPLICATION_CREDENTIALS`,
   including a Workload Identity Federation credential file.
4. The older client ID, client secret, and refresh-token flow.

Developer tokens were sunset on September 9, 2026. An existing token remains
an optional compatibility header but is no longer required. The GitHub Actions
collector runs the full Google validation cycle on the first day of each month
and can also be started manually. GitHub exchanges its short-lived OIDC token
through `GCP_WORKLOAD_IDENTITY_PROVIDER` and impersonates the dedicated EtGen
service account; no long-lived Google key is created or committed. The
provider resource name and customer IDs are stored as GitHub Actions secrets.

### If Google Ads returns HTTP 403

The GitHub identity and Google Cloud credential exchange can succeed while the
Google Ads API still rejects the service account. Check these separate access
layers before rerunning the full cycle:

1. In the `etgen-keyword-data` Google Cloud project, confirm that the Google Ads
   API is enabled and the Google Ads API Overview shows **Basic or Standard**
   access. Explorer access does not permit `KeywordPlanIdeaService`, even for
   a production Ads account. If Basic access was denied, check the project's
   OAuth brand verification status: Google requires an External app in
   production with its branding verified and published before approving Basic
   access. Verify ownership of the application's authorized domain in Google
   Search Console, then use **Verify Branding** and **Publish branding** in
   Google Auth Platform. Reapply for Basic access after branding is published.
   For Standard access, confirm that the project's permissible use includes
   keyword research.
2. In Google Ads **Admin > Access and security**, confirm that
   `etgen-keyword-collector@etgen-keyword-data.iam.gserviceaccount.com` has
   access to the target account. If access is through a manager account, set
   the optional GitHub Actions secret `GOOGLE_ADS_LOGIN_CUSTOMER_ID` to that
   manager's ID without hyphens; keep `GOOGLE_ADS_CUSTOMER_ID` as the target
   client account ID.
3. Run the `Evidence Collector` workflow manually and inspect its
   `google-keyword-validation` job. A successful Cloud authentication step alone
   does not prove that Keyword Planner is authorized. Only a completed Google
   collection with stored monthly-search observations closes the volume gap.

Google's [Cloud project access guide](https://developers.google.com/google-ads/api/docs/api-policy/access-levels),
[brand-verification guide](https://developers.google.com/google-ads/api/docs/api-policy/brand-verification),
[service-account setup](https://developers.google.com/google-ads/api/docs/oauth/service-accounts),
and [account-access guide](https://developers.google.com/google-ads/api/docs/account-management/listing-accounts)
describe these permissions.

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

## Scheduled collection fallback

When the hosted API is unavailable, `.github/workflows/keepalive.yml` runs an
ephemeral GitHub Actions worker instead. It restores the durable queue from
Supabase, processes up to 50 quota-paced keywords every four hours, flushes
secondary evidence in five-keyword batches, and writes each completed run back
to Supabase. This provides a hard ceiling of 300 primary keyword scans per day
without requiring a continuously running paid web process. The static PWA
imports the new evidence on its existing six-hour release schedule.
