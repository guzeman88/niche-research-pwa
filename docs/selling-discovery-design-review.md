# Selling discovery design review

Reviewed October 16, 2026. **Disposition: ship within the local extension scope.**
The completed discovery surface follows the incumbent private EtGen `/selling`
interface and its [direction contract](selling-discovery-design.md). This is an
ordinary Operate extension: the existing implementation, root `PRODUCT.md` and
the user's Refactoring UI principles provide visual authority. No new visual
identity or approved comparison comp was supplied.

This review covers local work on `codex/selling-discovery` above committed base
`e7567c6752a85ecafc4a22293ccf09e64072f615`, including uncommitted feature files.
It does not describe an installed immutable runtime or public deployment.

## Extension fidelity

Discovery precedes the existing opportunity watchlist and gives operators a
concrete first action: browse a collected listing and choose Investigate.
Compact, border-separated rows keep title, activity evidence, source wording and
capture time together. Search and evidence filters precede the results;
pagination bounds the catalog view. The extension preserves manual opportunity
creation, saved-opportunity selection and the existing investigation workspace
with its five research methods, sales model and original improvement brief.

The source retains the incumbent visual vocabulary:

- Dark neutral ground, surface-950 (`#202631`), and surface-900
  (`#252d3a`) inputs; surface-800 (`#303948`) secondary controls.
  Surface-50 (`#f3f6fb`) leads, surface-200 (`#bcc9d8`) supports,
  surface-300 (`#9fb3ce`) carries metadata, and surface-600/700 separate rows.
- The existing restrained primary blue (`#6f96c8`) identifies Investigate and
  Open research. Their local dark foreground and unchanged blue hover background
  preserve readable contrast. Written amber feedback accompanies errors.
  Evidence states use explicit text rather than color alone.
- The existing `Inter, system-ui, sans-serif` declaration, with 24 px page
  heading, 18 px section headings, 16 px listing titles, 14 px labels/supporting
  text and 12 px metadata. Weight and contrast establish hierarchy without a
  decorative display treatment. CSS does not establish actual font availability.
- Existing 4/8/12/16/24/32 px grouping steps, with 20 px row padding and filter
  margins and the inherited 10 px vertical control padding. Label/input pairs
  retain 8 px separation; section gaps are larger than within-row gaps.
- Shared rounded buttons/inputs, borders, focus and disabled treatments.
  Results remain flat rows rather than a new card grid. Primary actions retain
  the shared subtle shadow; no new motion or elevation system is introduced.

At 320 px the filters and row actions stack, metadata wraps, and pagination
remains reachable. At 768 px the filters share a row and result actions sit beside
the listing copy. At 1024/1440 px the incumbent 280 px watchlist remains beside
flexible detail below discovery. The inspected captures show a continuous reading
path with no clipped discovery controls. Source-provided thumbnails are optional;
the fixture captures contain no invented artwork.

Investigation selects the saved opportunity, refreshes the watchlist, scrolls to
the workspace and transfers focus there. Busy labels prevent duplicate in-flight
actions; promoted rows expose Open research. Refresh exposes pending and queued
feedback without clearing the current result list. Source inspection includes
loading, query-error/retry, empty-filter and unavailable-purchase-access branches.
Status and error messages use `status` and `alert` roles, and fields retain native
labels and controls.

Evidence wording makes the key distinction visible: Recent purchase report,
Recent review activity with purchase timing unknown, and Sales unknown.
Purchase quotations retain their captured wording and timestamp; historic reports
are labeled when no longer current. The access disclosure distinguishes saved
catalog refresh from new Etsy collection requiring verified authorization. The
footer explains that purchase reports are not independently verified orders and
that reviews/favorites do not prove current sales.

## Evidence and finish disposition

This documentation pass inspected `src/index.css`,
`src/components/selling/SellingDiscovery.tsx`, `src/pages/SellingProducts.tsx`,
the direction contract and the existing sales-model design review. It visually
inspected `.impeccable/review/desktop.png`, `.impeccable/review/mobile.png`,
`work/ui-discovery/768.png` and `work/ui-discovery/1024.png`.

The inspected `work/ui-discovery/verification.json` records an isolated fixture
run at 320/768/1024/1440 px, keyboard promotion, evidence filters, pagination,
idempotent promotion and sales-model evidence. Its measured discovery-action
contrast is approximately **4.97:1** at each width. The implementation handoff
reports no horizontal overflow at all four widths. These functional results are
supplied execution evidence, not an independent browser rerun by this pass.

The supplied detector result for the new/changed TSX is `[]`. The fresh finish
review's disposition is **ship**, with no material UX defects in the reviewed
local extension. Source and captures support fidelity to the direction contract.
Neither that disposition nor the detector is a comprehensive accessibility
certification.

The implementation handoff separately reports 13 discovery backend tests passing.
It also reports an isolated read of 5,000 real catalog observations yielding 4,378
listings, zero purchase/review reports and zero external requests. No synthetic
records were inserted into the live research ledger. These are bounded catalog
observations, not evidence of current sales or authorized live Etsy access.

## Review limits and pre-existing drift

Captures show a fixture catalog with three filtered examples, including synthetic
purchase/review evidence. They do not establish live Etsy access, real-provider
payload compatibility, commercial accuracy, demand or profitability. Source
branches and functional assertions do not substitute for visual captures of
every loading, failure, empty, long-content, thumbnail or expanded-disclosure
state. Screen-reader behavior, zoom and reduced-motion preferences were not
independently exercised by this documentation pass.

Root `DESIGN.md` was already missing. That is pre-existing documentation drift;
this ordinary extension records its inherited design here without creating a
global design system or sidecar. The incumbent global CSS also retains gradients,
shadows and 10/11 px utility labels; those are existing context rather than new
standards established by discovery. The prior sales-model review and direction
files remain intact. This pass changes only this review document.
