# Profitable Product Roadmap

This roadmap turns the app from niche discovery into a product pipeline that can create specific Etsy-ready products from real keyword evidence.

## Current Baseline

- Store recommendations are generated from available keyword clusters and profitability signals.
- My Stores keeps selected stores locally and exposes Store Dashboard, Product Creator, and Listing Manager.
- Product Creator now creates SKU-level product briefs from a selected keyword and product type.
- Each product brief stores exact phrase, artwork subject, composition, palette, typography, avoid list, buyer angle, mockup direction, and the source keyword set.
- Design generation is still mostly prompt-led. Free web launchers and configured APIs can be tested, but the quality gate must judge the output before a listing is treated as usable.

## Definition of a High-Quality Product

A product should not be accepted just because the keyword score is high. It should pass all of these checks:

- Primary keyword has real score data and is stored with the product.
- Supporting keywords are real keywords from the same store or cluster.
- Product type matches buyer intent for the keyword.
- Exact phrase is readable, non-generic, and not trademark risky.
- Artwork is visually specific enough to stand apart from saturated listings.
- Design prompt describes the image, words, layout, style, palette, and avoid list.
- Mockup direction matches the product type and Etsy thumbnail behavior.
- Listing draft can reuse the same keyword evidence without inventing new data.

## Phase 1: Stronger Product Briefs

Goal: make every generated product idea feel like a concrete SKU, not a category.

- Generate six specific product concepts per keyword/product type.
- Store exact phrase, artwork subject, composition, palette, typography, avoid list, buyer angle, and SEO source with each concept.
- Keep idea cards short, but expose the full brief when selected.
- Feed the same brief into design prompts, mockup prompts, and listing drafts.
- Never use random fallback metrics. Missing data should remain visibly missing.

Status: implemented in the current product creator pass.

## Phase 2: Product-Type Fit Scoring

Goal: choose the product type most likely to convert for each keyword.

- Score product type fit using keyword wording, buyer intent, average price, estimated margin, and known store product types.
- Penalize mismatches such as physical-product keywords mapped to vague digital templates.
- Track a fit reason for each product type so the UI can explain the choice without long copy.
- Sort product type tabs by fit score instead of raw store order.

Suggested fields:

- productTypeFitScore
- productTypeFitReasons
- expectedPriceBand
- expectedProductionCostBand
- expectedMarginBand

Status: implemented. Product types are scored and sorted from keyword wording, source product match, store product mix, and any available buyer intent, price, or margin evidence. Missing evidence is stored as missing instead of filled with fallback numbers.

## Phase 3: Competitive Gap Evidence

Goal: explain why a concept might win without needing Etsy API access for every listing.

- Compare the keyword against the existing local keyword dataset.
- Prefer keywords with strong intent, decent demand, high gap, and specific modifiers.
- Detect overcrowded phrase patterns and push the generator away from them.
- Store saturation notes such as overused motif, broad phrase, or weak specificity.
- Add a "gap reason" to each product brief.

Useful checks:

- modifier depth
- buyer phrase specificity
- product-type clarity
- generic phrase penalty
- repeated motif penalty
- price/margin plausibility

Status: implemented. Product ideas now store gap evidence with score, level, reasons, cautions, and missing inputs. The score uses available keyword metrics and keyword specificity only; absent marketplace metrics remain absent.

## Phase 4: Design Quality Gate

Goal: stop weak designs before they become listings.

- Require every accepted design to pass a checklist: readable text, correct exact phrase, clear subject, no extra words, no trademark risk, printable contrast, thumbnail clarity.
- Store a pass/fail result and short failure reason.
- Let the user regenerate from the same brief without losing the keyword evidence.
- Add provider performance tracking by product type: which image tools produce the best mug text, stickers, wall art, etc.

Suggested statuses:

- design_needed
- design_generated
- design_failed
- design_approved
- mockup_ready
- listing_ready

Status: implemented. Product Creator now requires a design quality checklist before approval. The saved product stores the quality checks, score, pass/fail state, and review timestamp.

## Phase 5: Listing Optimizer

Goal: convert accepted products into Etsy-ready listing drafts.

- Build listing titles from primary keyword, product type, and one or two high-strength supporting keywords.
- Generate descriptions from the actual product brief, not generic store copy.
- Keep tags limited to real keyword terms and clean derivatives.
- Add a listing quality score based on title coverage, tag diversity, phrase readability, and evidence completeness.
- Flag missing data rather than inventing estimates.

Status: implemented. Listing drafts are scored from title keyword coverage, supporting keyword coverage, tag count, product brief coverage, and stored gap evidence. Missing supporting keywords or gap evidence remain visible.

## Phase 6: Export and Publishing Workflow

Goal: move from planning to production without rewriting work by hand.

- Export product briefs, approved design prompts, mockup prompts, and listing drafts as CSV or JSON.
- Add Printify or other production-provider integration only after credentials and product templates are settled.
- Add Etsy draft publishing only after valid API access exists.
- Keep all publish actions explicit and reversible.

Status: partially implemented. JSON and CSV export are implemented for products, creative briefs, design prompts, listing drafts, quality scores, and performance data. Etsy publishing and Printify product creation are intentionally blocked until valid credentials and product templates exist.

## Phase 7: Learning Loop

Goal: improve recommendations from actual performance.

- Track which product concepts are approved, rejected, listed, favorited, clicked, and sold.
- Feed those outcomes back into keyword scoring and product-type fit scoring.
- Promote patterns that produce approved designs and sales.
- Penalize patterns that repeatedly fail design quality, listing quality, or buyer response.

Status: implemented as a local feedback loop. Listing drafts now accept manually entered views, favorites, orders, and revenue. Dashboard summaries and exports use those actual entered values. Automatic Etsy analytics import still depends on Etsy credentials.

## Immediate Next Steps

1. Connect Etsy analytics once credentials are available.
2. Connect Printify or another production provider once product templates and credentials are available.
3. Add provider-level design win-rate reporting after enough approved/rejected design outcomes exist.
4. Add automatic performance import so manual views, favorites, orders, and revenue are no longer required.
5. Add listing draft publishing only after the app can create a reversible Etsy draft safely.
