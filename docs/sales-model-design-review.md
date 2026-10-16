# Sales model design review

Reviewed October 16, 2026 against the incumbent private EtGen `/selling`
interface. This is an ordinary Operate extension. The direction authority is
[the sales model surface contract](sales-model-design.md), `PRODUCT.md`, the
user's Refactoring UI principles and the existing implementation. No new visual
identity, approved comparison comp or qualitybar card was supplied.

This review reflects local source on `codex/sales-model` above committed base
`f57076f0116b476254266af71e645bd72548b6dd`, including uncommitted feature work.
It is not a claim about an installed immutable runtime or public deployment.

## Incumbent system and direction fidelity

The extension keeps the established watchlist, opportunity detail, wrapping
section controls and border-separated research reading path. Sales model is an
additional opportunity section; Analysis, Evidence and Improvement brief remain.
It does not introduce a new shell, dashboard metric-card grid or palette.

The observed visual vocabulary remains:

- Dark neutral grounds: surface-950 (`#202631`) and surface-900
  (`#252d3a`); surface-800 (`#303948`) supports existing controls.
  Primary text uses surface-50 (`#f3f6fb`), supporting copy surface-200
  (`#bcc9d8`), metadata surface-300 (`#9fb3ce`) and separators
  surface-600 (`#465365`).
- Existing restrained blue primary (`#6f96c8`); written amber feedback
  (`#f0cf89`) accompanies failure information. Color is paired with text
  and, for period selection, `aria-pressed`.
- Existing `Inter, system-ui, sans-serif` declaration. The model uses
  12 px metadata, 14 px supporting text and labels, 16 px listing/rating
  headings, 18 px section heading and 20 px estimate. The existing page title
  remains 24 px. Weight and contrast create hierarchy; estimates use tabular
  numerals. Actual font availability is not established by the CSS declaration.
- Existing 8/12/16/24/32 px grouping rhythm and shared input/button padding.
  Supporting introductions and expanded explanations use bounded reading width.
  Closely related label/input pairs retain 8 px separation.
- Shared rounded controls, borders, focus treatments, hover and disabled
  behavior. Model sections use flat dividers rather than adding card shadows;
  primary controls inherit the existing subtle shadow.

The model heading, provisional explanation and timestamp precede the incomplete
opportunity rating within the selected section. Listing-by-listing estimates,
scenario ranges, coverage text, original purchase wording, units, date and source
remain together. Assumptions, calibration and explanation use labeled native
disclosures, preserving the default reading path. At narrow widths the incumbent
watchlist precedes the selected detail, so model content begins below the
workspace context rather than replacing the page's first viewport.

Unknown evidence is explicit: the source renders Incomplete, Needs evidence,
Insufficient evidence and Unknown where applicable. The empty-listing state points
operators back to Evidence. Assumption fields may remain blank; calibration
requirements, held-out comparison and stale/inactive status remain visible when
their associated states are available. The Evidence extension adds seller outcome
records and a matching CSV template using existing field/form patterns.

## Evidence inspected

Source inspection covered `src/index.css`, `src/pages/SellingProducts.tsx`,
`SellingAnalysis.tsx`, `SellingModel.tsx`, `SellingModelSettings.tsx` and
the local diffs for `SellingForms.tsx`, `SellingImport.tsx` and
`SellingOpportunity.tsx`. The unchanged stylesheet and incumbent research
components supplied the comparison authority.

Fresh isolated-fixture captures at `work/ui-sales-model/320.png`, `768.png`,
`1024.png` and `1440.png` were visually inspected. They show the populated
30-day model, incomplete rating, original purchase message, collapsed settings
and calibration requirement feedback. Controls wrap at 320 px; listing metrics
and rating rows stack below the existing small breakpoint. At 1024/1440 px
the established 280 px watchlist sits beside flexible detail. The captures show
no obscured model controls or page-width clipping in that state.

The implementation handoff reports that the browser workflow passed all four
widths, keyboard period selection, rejected and accepted purchase-message forms,
explicit assumption saving, the calibration minimum-case guard, five existing
research methods, evidence export and the original production PDF handoff.
The inspected browser script contains these checks; its fresh
`work/ui-selling/verification.json` records isolated fixtures, all four widths,
five methods and `original_pdf: true`. These functional results are supplied
evidence, not an independent rerun by this documentation pass.
The full workflow passed again after the final hover correction, and all four
captures were refreshed; this rerun is reported by the implementation handoff.

## Finish disposition

The finish review initially required two changes: sufficient contrast on the
active period control and coverage wording that distinguishes supported days,
assumption-supplied estimates and days without an estimate. The current source
and refreshed captures include both fixes. The active period uses existing
surface-950 text on incumbent primary-400 blue, with a local
`hover:bg-primary-400!` override keeping the selected blue on hover. The supplied
measured default contrast is approximately 4.97:1. The inspected browser check
measures computed foreground/background colors in default and hover states after
the shared 150 ms transition settles; the supplied execution passed the 4.5:1
threshold in both states. This local treatment does not redefine the shared
primary button.

Coverage now says how many equivalent days are supported by evidence or a fitted
model, explicitly identifies assumption-supplied estimates, and separately names
days with no daily estimate. The supplied follow-up finish disposition was
**ship for both scored fixes**, including source review of the final hover
override with browser execution evidence supplied. The single supplied detector run returned
`[]`; this is not a comprehensive accessibility certification.

This source-and-screenshot documentation pass finds the completed extension
faithful to the incumbent direction within the reviewed scope.

## Limitations and pre-existing drift

The four screenshots cover one fixture state, not every open disclosure, empty
state, long source reference, successful fitted model, screen-reader interaction,
zoom level or reduced-motion preference. Functional coverage and a targeted
contrast measurement do not certify complete WCAG 2.2 AA compliance.

Root `DESIGN.md` was already missing. That is pre-existing design-documentation
drift, reported here without creating a replacement system or sidecar.
The brief's boilerplate FINISH line names `DESIGN.md`; the explicit scope for
this ordinary extension restricts documentation to this review. Global CSS also
retains inherited gradients, shadows and 10/11 px utility labels despite the
product preference for restraint. Those choices are existing context, not new
standards introduced by this feature.

No UI, token, shared stylesheet, `DESIGN.md`, sidecar, runtime or deployment
change was made by this documentation pass. Fixture estimates and screenshots
do not establish real competitor orders, calibrated commercial accuracy, Etsy
demand, profit or production quality. Original purchase messages preserve their
units; modeled conversions and ranges remain provisional.
