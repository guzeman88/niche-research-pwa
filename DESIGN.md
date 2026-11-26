---
name: EtGen Pipeline
description: A restrained research and product-review workspace grounded in actual evidence.
colors:
  bg: "hsl(220 14% 13%)"
  paper: "hsl(220 14% 17%)"
  ink: "hsl(216 18% 94%)"
  muted: "hsl(216 10% 70%)"
  line: "hsl(220 9% 30%)"
  soft: "hsl(220 12% 18%)"
  accent: "hsl(215 67% 78%)"
  on-accent: "hsl(220 30% 13%)"
  nav: "hsl(220 16% 10%)"
  nav-muted: "hsl(216 11% 71%)"
  nav-line: "hsl(220 12% 21%)"
  nav-active: "hsl(220 13% 23%)"
  nav-active-ink: "white"
  status-bg: "hsl(32 27% 22%)"
  status-ink: "hsl(34 53% 79%)"
  selected: "hsl(218 22% 24%)"
typography:
  headline: {fontFamily: "Archivo, sans-serif", fontSize: "24px", fontWeight: 600, lineHeight: 1.25, letterSpacing: "-0.025em"}
  title: {fontFamily: "Archivo, sans-serif", fontSize: "15px", fontWeight: 600, lineHeight: 1.4, letterSpacing: "-0.01em"}
  body: {fontFamily: "Archivo, sans-serif", fontSize: "14px", fontWeight: 400, lineHeight: 1.45}
  field: {fontFamily: "Archivo, sans-serif", fontSize: "13px", fontWeight: 400, lineHeight: 1.45}
  control: {fontFamily: "Archivo, sans-serif", fontSize: "12px", fontWeight: 500, lineHeight: 1.35}
  label: {fontFamily: "Archivo, sans-serif", fontSize: "11px", fontWeight: 500, lineHeight: 1.4}
rounded:
  thumbnail: "3px"
  pill: "4px"
  control: "5px"
  preview: "6px"
  stage: "7px"
  menu: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  compact: "12px"
  md: "16px"
  group: "20px"
  lg: "24px"
  section: "32px"
  canvas: "40px"
components:
  button-primary: {backgroundColor: "{colors.accent}", textColor: "{colors.on-accent}", rounded: "{rounded.control}", padding: "7px 12px", typography: "{typography.control}"}
  button-secondary: {backgroundColor: "{colors.paper}", textColor: "{colors.ink}", rounded: "{rounded.control}", padding: "7px 12px", typography: "{typography.control}"}
  field: {backgroundColor: "{colors.paper}", textColor: "{colors.ink}", rounded: "{rounded.control}", padding: "9px 10px", typography: "{typography.field}"}
  stage: {backgroundColor: "{colors.paper}", textColor: "{colors.ink}", rounded: "{rounded.stage}", padding: "20px"}
  pill-warning: {backgroundColor: "{colors.status-bg}", textColor: "{colors.status-ink}", rounded: "{rounded.pill}", padding: "3px 7px", typography: "{typography.label}"}
---

# Design System: EtGen Pipeline

## Overview

**Creative North Star: "Pipeline"**

The approved Pipeline reference supplies the visual identity: charcoal work surfaces, pale-blue actions, compact Archivo typography and quiet separators. Screens start with useful records, review stages or forms; information gains emphasis through placement, weight and spacing.

This record describes the implemented frontend source, not an installed or deployed runtime. Authority: [surface contract](docs/pipeline-design/SURFACE.md), [reference hashes](docs/pipeline-design/reference.json), `src/pipeline/reference.css`, `src/pipeline/production.css` and their React consumers.

**Key Characteristics:**
- Compact tables, clear section spacing and restrained primary actions.
- Real evidence, explicit unknowns and separate research/account contexts.
- Existing specialist workflows remain reachable through named tools.

## Colors

### Primary
Pale-blue `accent` identifies primary actions, selected tab rules and focus. Dark `on-accent` keeps button text readable. Warm `status-bg` / `status-ink` accompanies explicit review or warning text.

### Neutral
Charcoal `bg`, darker `nav`, raised-tonally `paper` and `soft` define the workspace. `ink` carries content, `muted` supports it, and `line` / `nav-line` divide groups. `nav-active` and `selected` identify current or selected items; active navigation uses white text.

**The Evidence Rule.** Missing, failed or stale data stays explicitly unknown or unavailable; supply samples and supporting demand never become verified sales or profit.

## Typography

Archivo is self-hosted at `/fonts/archivo-latin.woff2`, with the approved font bytes recorded in the reference manifest. Use its variable weights with a sans-serif fallback, rather than introducing another family.

Page headings use `headline`; mobile headings step to (22px). Sections use `title`; ordinary content uses `body`, dense tables and actions use (12px), field values and navigation use (13px or the implemented 12px link treatment), and metadata/pills use `label`. Primary buttons carry weight (600). Functional explanatory paragraphs use (12px), line-height (1.6) and at most (75ch); drawer paragraphs narrow to (65ch). Numerical evidence uses tabular figures.

**The Direct Start Rule.** Primary views begin with a title and useful content, without opening number strips or default secondary paragraph copy. Keep necessary labels, evidence limits and errors adjacent to their relevant controls.

## Layout

The desktop shell uses a (216px) sidebar and flexible content. The effective sidebar becomes (192px) at (1150px) and below; at (700px) the shell stacks and navigation moves to **All pages**. The capture header is (56px), becoming (44px) on mobile. Main content caps at (1480px), uses (40px) horizontal padding and (32px) top padding; intermediate padding is (32px), mobile padding (24px 20px).

Dashboard stages use columns (1.12fr 1.3fr .9fr), with (20px) gaps and (440px) minimum height. At (1200px) gaps become (16px); at (1000px) stages stack with natural height. Two-column workspaces also stack at (1000px). Section spacing follows the frontmatter scale rather than an equal-weight card grid.

Tables fill their container with horizontal scrolling inside a keyboard-focusable region. Cells use (16px 14px), header vertical padding (12px), and quiet bottom borders. Mobile tables retain a (580px) minimum width, with (14px 12px) cells; drawer tables may narrow to (440px). Pagination follows actual API totals and pages, never frozen prototype limits.

## Elevation & Depth

Work surfaces are flat, separated by tonal changes and single-pixel borders. Stages, legacy panels and buttons have no decorative shadow or blur. Overlay menus use `0 8px 32px hsl(220 15% 10% / .18)`; the detail drawer uses `-8px 0 32px hsl(220 16% 12% / .17)`. No ornamental motion is required; reduced-motion preference disables transitions, animations and smooth scrolling.

## Shapes

Use the named frontmatter radii: small thumbnails, compact pills, controls, file previews, stages and menus each retain their existing corner treatment. Dashboard stages have a single-pixel border and `paper` fill. Forms use outlined fields, not elevated cards; named specialist tools retain the same controls and type treatment. Account and backup workspace sections are flat and unboxed.

## Components

- **Buttons and fields:** primary fill for the key action, outlined paper for secondary actions, warm text-backed danger/review states. Buttons have a (34px) minimum height; table buttons shrink to (30px). Primary hover uses brightness (.92); secondary hover uses `soft`. Fields use a (2px) accent focus outline with (2px) offset; ordinary links/buttons use the reference (3px) outline and offset. Disabled states remain visibly dimmed.
- **Navigation:** restrained links, muted inactive text and tonal current-page fill. Mobile **All pages** is a native disclosure with scrollable links; route changes close it. SVG stroke icons support text labels. Workspace context exposes developer/user mode only where authorized; role and local-operator access govern visible actions.
- **Detail drawer:** (600px) wide, (560px) below (1000px), full viewport at (700px), with (32px) padding or (28px) on mobile. Mobile uses dialog modality, an inert background and wrapped Tab focus. Escape/close restores the initiating control; navigation removes the panel and clears inert state.
- **Tables, pills and previews:** status text supplies meaning alongside color; product files are contained without cropping. Review remains tied to exact protected product artifacts and existing owner/cost/export approval gates. Research/native data stays separate from account records. Named workspace tools preserve existing specialist forms and actions.
- **Product viewer:** files lead the view. File and worksheet selectors share one toolbar; page count and zoom use compact native controls with accessible names. Repeated visual labels/page captions are suppressed, while screen-reader labels remain. Actual page images retain their natural proportions, with no inherited thumbnail padding/height; the reading column caps at (880px) at fit width. Cell contents remain available in one compact scrollable formula line. Downloads stay collapsed. Full-screen, keyboard focus, all worksheets/rows and exact-package approval gates remain intact.
- **Record controls:** Keywords keeps search, category, evidence and keyword/listing-count/average-price sorting above the table; research filtering and sorting run across the library before API paging. Its page-heading export explicitly exports visible rows. Keywords average prices and Store Generator median prices use US/USD currency formatting in both rows and drawers; missing or non-finite prices stay `Unknown`.

## Do's and Don'ts

### Do:
- **Do** reuse the approved Archivo, HSL roles, spacing and compact control geometry.
- **Do** preserve keyboard access, responsive scrolling, named tools and explicit evidence states.
- **Do** retain exact-product review and authorization gates while simplifying presentation.
- **Do** show currency for known USD prices in rows and details, and keep unavailable prices unknown.

### Don't:
- **Don't** add opening number strips or default secondary paragraphs to primary views.
- **Don't** turn missing evidence into zero, sales, profit or approval.
- **Don't** mix account records with native research or impose snapshot caps on live pagination.
