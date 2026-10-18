# Sales intelligence design review

Reviewed October 17, 2026 against local source on `codex/sales-intelligence`,
above base `dd56041d4e22ef3e5ef8f868b057bdf9aaa11d56`, including uncommitted
feature work. This record covers the private `/selling` software interface;
it does not describe an installed runtime or public deployment.

## Direction and preservation

This is an ordinary **Operate** extension of the incumbent research workspace.
Authority comes from `PRODUCT.md`, the user's Refactoring UI principles and the
existing implementation. No new visual world, comparison comp, seed or QUALITY
BAR card applies. The extension retains dark neutral surfaces, restrained blue
actions, the existing `Inter, system-ui, sans-serif` declaration, fixed type and
spacing scales, shared rounded controls and flat border-separated rows. The CSS
declaration does not establish which font is available on every device.

Sales intelligence opens within the existing page. Wrapping section buttons
separate comparison, opportunities, coverage, sources, learning and import.
Labels sit with their fields; native selects and disclosures preserve familiar
interaction. Supporting explanations have bounded reading widths. Smaller
screens stack forms and wrap actions, while source comparisons retain their
table semantics within a horizontal overflow container. The page's discovery,
watchlist, five-method research, independent Sales model and improvement-brief
workflows remain available. Investigate returns the selected product to that
opportunity workspace.

Hierarchy follows evidence rather than decorative metrics: dated compatible
references precede provisional model results; source disagreement is explicitly
separate from a confidence interval. Unknown sales and absent models remain
written states. Coverage distinguishes catalog listings, retained readings and
actual outcomes. Sources distinguish a free offer from working acquisition and
model-use permission. Learning distinguishes provider agreement from actual
purchase accuracy. History plots one reporting cohort by availability time and
provides the corresponding source/value list; refreshes are not additional sales.

## Evidence and disposition

This documentation pass inspected `SalesIntelligence.tsx`,
`IntelligenceCoverage.tsx`, `ReferenceHistory.tsx`, their integration in
`src/pages/SellingProducts.tsx`, the shared stylesheet, `PRODUCT.md`,
`docs/sales-intelligence.md` and the isolated browser-check script. It visually
inspected the desktop and narrow comparison/history captures at
`.impeccable/review/intelligence-1440.png` and `intelligence-320.png`.

The supplied independent finish reviewer inspected source and all ten captures:
comparison at 1440, 1024, 768, 651 and 320 px, plus `intelligence-sources.png`,
`intelligence-coverage.png`, `intelligence-learning.png`,
`intelligence-opportunities.png` and `intelligence-import.png`, all under
`.impeccable/review/`. Its disposition is **ship at the software UX/craft scope**,
with no material fixes requested. The inspected captures preserve the incumbent
visual language and show the comparison/history path alongside existing research.

The implementation handoff reports passing isolated synthetic browser checks
for accepted/rejected imports, compatible comparison and unknowns, chart/list
history, ranking and investigation, source controls, training requests, keyboard
focus and all five widths without page overflow. The inspected script contains
these assertions, uses a temporary archive and synthetic permissions, and checks
for browser errors and provider requests. These are supplied execution results,
not a functional rerun by this documentation pass. The single supplied mechanical
detector run returned `[]`.

## Limits and documentation drift

Captures and targeted checks do not certify complete WCAG 2.2 AA compliance,
every data/error state, screen-reader behavior or all zoom preferences. Synthetic
reference estimates and test permissions establish no external acquisition,
provider authorization, real sales accuracy, commercial performance, installed
runtime state or completion of the full sales-intelligence plan. Working free
feeds and demonstrated improvement on real outcomes remain separate milestones.

Root `DESIGN.md` was already absent: pre-existing documentation drift, not a
greenfield visual brief. This bounded review records the extension without
repairing that drift or promoting task-specific choices into global rules. This
documentation pass changes only this file; it creates no `DESIGN.md` or design
sidecar and changes no UI, operational documentation, runtime or deployment.
