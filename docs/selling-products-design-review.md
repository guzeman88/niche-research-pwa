# Selling products design review

Reviewed October 15, 2026 against the incumbent EtGen interface. This is an
ordinary Operate extension, not a new visual identity. The review authority was
the extension brief, both repositories' `PRODUCT.md`, and the existing component
system; no approved comp, direction contract, or qualitybar card was supplied.

## Incumbent system preserved

- Palette: existing slate surfaces and blue primary actions; semantic amber
  accompanies written warnings. No new palette or token definitions.
- Type: existing `Inter, system-ui, sans-serif` declaration; 12/14/16/18/20/24 px
  roles, with weight and contrast distinguishing headings from supporting copy.
- Rhythm: existing 8/12/16/20/24/32 px spacing steps; bounded supporting text and
  grouped, labeled fields retain the established operating density.
- Controls: shared primary/secondary buttons and inputs retain their shapes,
  focus treatments, disabled states and visual priority. Method and section
  controls expose selection with `aria-pressed` as well as color.
- Layout: single-column watchlist/detail below the large breakpoint, then a
  280 px watchlist with a flexible detail region. Actions wrap; evidence tables
  have local horizontal overflow when needed.

## Evidence checked

Source inspection covered `src/index.css`, `src/pages/SellingProducts.tsx`,
`SellingAnalysis`, `SellingOpportunity`, `SellingBrief`, `SellingImport`, and the
selling-brief additions to `ProductionSpecForm` and `ProductionQueue`.

The populated Product patterns state was visually inspected in
`work/ui-selling/320.png`, `768.png`, `1024.png`, and `1440.png`. Its page,
watchlist, opportunity, method selection and comparison hierarchy remain readable
at all four widths. Narrow layouts wrap controls and stack the watchlist without
obscuring the selected evidence. This visual evidence covers that state only.

The implementation handoff reports browser integration passing for all five
analysis methods, CSV/JSON preview errors and idempotent imports, authored brief
and evidence export, and actual production of an original PDF. These are
functional results supplied to this review, not separate visual verification of
every workflow state. The supplied static detector result for changed targets
was `[]`; it is not a comprehensive accessibility certification.

## Product boundaries retained

Analysis distinguishes provider estimates, seller reports, reviews, observed
keywords and operator-recorded product attributes. Source/date context and
limitations remain visible; absent evidence stays unknown. Product rarity,
keyword occurrences, favorites and shop totals do not establish listing sales,
demand or profit. The workflow uses preserved research and permitted imports
under the free-only constraint. Keyword rights flags remain simple advisory
signals rather than legal clearance.

The improvement brief asks for an authored product direction and specific buyer
improvements. Production intake carries that direction for review; original
customer contents and actual costs/delivery facts still require input.
Competitor artwork, wording, prices and tags are not promoted into customer
files. A brief does not itself render, publish or validate a product.

## Disposition and existing drift

The supplied finish reviewer disposition was **ship**, with no material fixes
across its five review sections. This source-and-screenshot pass found no
material system divergence requiring a new visual specification.

Pre-existing global CSS retains gradients, shadows, and 10/11 px utility labels
despite the product documents' preference for restraint and avoidance of
decorative gradients. Those incumbent choices were left intact; they are not
newly canonized by this extension. No `DESIGN.md`, sidecar, shared tokens, or
application code was changed by this documentation pass. Runtime installation
and public deployment are separate from this local source review.
