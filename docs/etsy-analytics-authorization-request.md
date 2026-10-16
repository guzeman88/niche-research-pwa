# Draft request for the Etsy developer-account owner

Prepared October 16, 2026. **Not sent.** Intended recipient: **developers@etsy.com**,
the contact in Etsy's [official API reference](https://developers.etsy.com/documentation/reference/).
Send through the existing developer-account owner and retain the response privately. No credentials, seller
identity details, account email or financial data belong in this document.

Subject: Written authorization and permitted data sources for EtGen product research

Hello Etsy Developer Support,

We maintain the existing EtGen application and would like to confirm approval
for an additional private product-research use case before activating it.

The feature would discover public listings from keyword searches, preserve dated
listing details and images, compare public listing reviews and shop-level sales
counters over time, and rank opportunities for independently created products.
It would label estimates and missing evidence clearly. It would not reproduce
other sellers' artwork, descriptions or brands, or claim access to their orders.

Please confirm in writing whether our existing app approval permits these API
analytics under the current API Terms, or identify the review needed. The API
requests would use documented listing, listing-image, listing-review and shop
endpoints, within the app's existing quotas. No paid quota upgrade is requested.

We would also like to know whether Etsy permits automated capture of a listing's
visible "people bought this in the past 24 hours" message, when present. If so,
please specify the allowed method, scope, request rate, storage/retention rules,
and any expiry or review date. If listing-page collection is not permitted, is
there a documented or separately authorized interface for that signal?

We will not circumvent access controls, scrape hidden endpoints, rotate proxies,
solve challenges automatically or treat absent messages as zero sales. We will
keep buyer counts distinct from purchases and units and will not sum overlapping
rolling-window messages. Exact transaction records would only come from shops
that explicitly authorize access to their own data.

Please identify which of the requested activities are permitted and the applicable
conditions, so we can configure the collector to those precise permissions.

Thank you.
