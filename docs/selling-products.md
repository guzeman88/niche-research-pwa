# Selling-product opportunities

Implemented October 15, 2026. Operational installation hashes and backup proofs
belong in the root repository's `docs/CURRENT_STATE.md`.

## Use

Open the private `/selling` workspace from Product validation or the administrator
navigation. Connect the same backend used by `/validation`. Create an opportunity
with a buyer keyword and product family, then add comparable listings in Evidence.
The watchlist ranks saved opportunities by evidence type and distinct shops with
recent positive listing-sales figures. It is a research ordering, not a profit or
conversion prediction. Search and watching/shortlisted/archived filters preserve
all saved records. Opportunity notes, keyword and family can be edited.

Use **Find in saved research** for the exact buyer phrase, manually record a
listing/observation/review/design inspection, or preview an authorized JSON/CSV
file. CSV templates are downloadable in the interface. Map provider column names
and reporting scope explicitly; an arbitrary provider export is not automatically
understood. Listing ID/Product ID and Shop/Shop Name aliases are supported.

Review the added/corrected/duplicate counts and parsed records, then import. The
whole packet is validated before writing in one SQLite transaction. Identical
imports are idempotent; corrections preserve revisions. An outdated preview
returns a conflict rather than overwriting another edit. A newer unknown
measurement does not revive an older known value.

## Five methods

| Method | Implemented behavior | Limits |
| --- | --- | --- |
| Sales evidence | Listing-specific period estimates and seller-reported figures, source attribution, current/historical separation, conflicting same-source values surfaced | Recent requires a capture and reporting-window start within 30 days. Lifetime averages are historical. Providers are alternatives, never summed; seller reports remain unverified. |
| Momentum | Same listing, source, metric and basis on different observation dates; equal-length period comparison; overlap and counter decreases disclosed | Reviews/favorites are interest, shop totals are shop scope. Unequal windows/currencies remain incomparable. Repeated imports over time supply the series; no new collection timer. |
| Buyer feedback | Transparent English theme matching with positive/concern counts, review references and repeated-listing/shop counts | Suggestions require operator review. Delivery concerns are distinguished from product/design issues. Review dates can lag purchases. |
| Keywords | Distinct-listing/shop overlap from observed tags and title phrases; matched demand measurements with source, geography and dates | Keyword presence never proves which search generated an order. Google demand supports research, not Etsy sales. |
| Product patterns | Manually inspected typography/layout/palette/features/readability matrix and observed feature counts | No automated vision judgments, competitor image downloading or artwork regeneration. Unrecorded traits remain unknown; rare traits do not prove demand. |

The methods are inspired by the product-research and tracking workflows documented
by [EverBee](https://www.everbee.io/product-analytics),
[Alura](https://www.alura.io/features/product-research), and
[eRank](https://help.erank.com/). These are workflow references, not integrations,
endorsements or proof of proprietary estimate accuracy. Provider source labels
record imported provenance; they do not imply account connections or authenticity.

## Access and costs

This extension makes **zero external marketplace requests**. It reads existing
saved research and operator-supplied records; it adds no scraping, paid plan,
credential purchase, subscription, provider API integration or new schedule.

Etsy's [API terms, section 5](https://www.etsy.com/legal/api/), checked October 15,
2026, expressly address automated analysis and analytics collection in clauses
24–25. Expanded written authorization has not been established in this workspace.
A successful API key request is not that proof. Existing collection is a separate
installed process and was not expanded by this feature. Imports also require the
operator to have permission to use their source; the software cannot establish
that permission or the source's truthfulness. Do not describe this release as an
automated, verified competitor-orders feed.

Saved listing observations are read-only from the trusted native installation
database, falling back to the existing research connection. No browser-supplied
database paths are accepted. Exact-match lookup reads at most 200 snapshots.
Invalid/incomplete records are skipped with a count, and absent evidence stays
unknown. It does not initialize or reset research databases or infer sales from
review counts, favorites, stock changes or shop totals.

## Original development and existing workflows

Write a product name, buyer/task, specific improvements and an original design
direction in Improvement brief. Suggestions are hypotheses, not automatic product
facts. The brief stores the exact evidence fingerprint; changes mark it stale.
Export the private JSON package with checksum for integrity checking. Its checksum
does not verify source authenticity. Only current evidence is exported; historical
correction revisions remain in the authoritative ledger and encrypted backups.

Review in production opens an editable specification. Authored buyer/task and the
saved direction are visible, while customer content, artwork, tags, price, cost,
delivery, taxonomy and rights facts still need actual operator inputs. It neither
copies competitor assets nor starts a render automatically. Submitting rechecks
the authoritative current brief; later product revisions retain their research
origin. The existing renderer and file-review workflow remain responsible for
actual output. Unsupported `other` families can export their brief for manual work.

Link to product validation creates an idempotent concept link. It does not invent
demand, relevance, economics or outcomes. Competitor estimates never receive
qualification credit or add to the supported-keyword target. The existing keyword
gap system remains separate. Existing keyword rights flags are advisory only;
this extension adds no rights approval gate.

## Data, API and verification

Private API prefix: `/api/selling-products`. Routes include overview, saved research,
opportunity create/update/detail, import preview/commit, brief, export, production
intake and validation link. They use existing operator authentication and private
`no-store` responses. Packet version 1 accepts `listings`, `observations`, `reviews`
and `patterns`; limits are 2 MB per request, 2,000 total records, at most 500
listings/patterns and 1,000 observations/reviews per packet. CSV has at most 1,000
rows. Unknown fields, duplicate normalized headings, invalid references/scopes,
non-finite values, booleans as numbers and future evidence are rejected.

Storage uses the existing revisioned private validation ledger with new
`selling_*` record kinds, existing retryable mirror and backup mechanisms. No
destructive migration, research reset or production-engine wheel change is needed.
Records remain locally authoritative if the private mirror is unavailable.

Run backend `python -m pytest tests -q`, `npm test`, `npm run lint`,
`SNAPSHOT_SOURCE=bundled npm run build`, and `npm run test:ui`. Set
`VALIDATION_QA_PYTHON` when the engine-equipped Python is not on PATH. The browser
regression uses a temporary backend/ledger and tests all five methods, malformed
preview recovery, duplicate preservation, authored brief, private export and an
actual original PDF handoff, with 320/768/1024/1440 layout checks. These fixture
checks are not live sales, source-authenticity or commercial performance proof.
