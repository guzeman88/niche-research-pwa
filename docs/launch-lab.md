# Launch Lab decision contract

Launch Lab is the evidence-gated path from one exact keyword to one reviewable
product and listing package. It is intentionally narrower than bulk keyword
collection: the purpose is to prove each handoff before scaling it.

## Workflow gates

1. **Keyword** — one normalized phrase and one explicit product format.
2. **Evidence** — demand and supply from the same provider, geography, and
   reporting period; market evidence no older than 180 days; at least ten
   observed marketplace listings.
3. **Economics** — exact sale price, production, shipping, marketplace fees,
   advertising allowance, and refund allowance for the selected product type.
4. **Decision** — a versioned score, complete evidence snapshot, SHA-256 input
   fingerprint, model limitations, and an operator note. Approval is invalidated
   automatically when the evidence fingerprint changes.
5. **Product** — a focused product brief derived from the approved keyword,
   product format, buyer, and decision record.
6. **Package** — an approved design, a listing quality score of at least 80, and
   a downloadable JSON package containing the decision audit and workspace.

## Decision model v1

The model identifier is `etgen-decision-v1.0.0`. It is a pre-launch decision aid,
not a revenue forecast or guarantee of profitability.

The model emits no score until the market pair, exact unit economics, freshness,
and listing-sample gates pass. When those inputs exist, the score is:

| Component | Weight | Meaning |
| --- | ---: | --- |
| Demand | 35% | Log-scaled measured searches from the matched market source |
| Market balance | 25% | Log-scaled relationship between measured searches and competing listings |
| Contribution margin | 30% | Exact contribution margin relative to the entered sale price |
| Sample depth | 10% | Number of observed listing samples, capped at 100 |

Confidence describes evidence completeness only. Trend history and own-shop
outcomes increase confidence, but missing outcomes do not masquerade as zero
sales. Scores below 50 remain on hold; 50–69 require review; 70 or above may
advance after explicit operator approval.

## Persistence and safety

Launch records live in the signed-in account workspace. The workspace autosaves,
can be backed up, and does not expose provider credentials. Market evidence and
unit economics remain in the private backend evidence record. Creating a Launch
Lab product creates a private store and product brief; it does not publish to
Etsy, create a Printify product, or spend provider credits without the existing
explicit actions in My Stores.
