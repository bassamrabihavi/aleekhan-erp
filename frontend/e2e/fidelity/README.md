# DEC-061 UI fidelity harness (PHASE_02 pages 1, 2, 4, 29, 33)

DEC-061 is the employer's rule of 2026-11-17. A page is accepted only when this test shows **at least 95 %**
match with its design-catalogue mockup at **every** width: 1440, 1180, 768 and 390. The threshold is
`THRESHOLD` in `config.ts`, and that is the only place it is set.

This harness only measures the pages. It never changes a page layout. On the built pages it adds `data-fid="<region id>"`
attributes. Each attribute marks a region that already exists.

## Rerun (one command)

```bash
cd frontend && npm run fidelity
```

This command needs the same environment as `npm run e2e`:
- the libpq variables of the test database (`set -a; . <pg-test.env>; set +a`)
- `PG_BIN`
- `E2E_DB=test_…`
- `E2E_BROWSER_CHANNEL=msedge` on the work machine

`scripts/fidelity.sh` runs `scripts/e2e.sh` with `E2E_FIDELITY=1`. That script:
1. creates and migrates a throw-away database;
2. starts Django and Vite;
3. runs only the `@fidelity` tests (`playwright.config.ts` skips them in a normal e2e run);
4. drops the database.

The run writes these files to `reports/phase-02/step-8/fidelity/` (`FIDELITY_OUT` overrides the folder):
- `baseline.json`
- `BASELINE.md`
- `shots/page-XX-<width>.jpg`: side-by-side mockup | built screenshots, at 1440 and 390.

Options:
- `FIDELITY_EXTRACT=1` re-extracts `specs/page-04|29|33.json` from the HTML mockups. Without it, the stored specs
  are used, and the sha256 of every mockup file must still match. If a mockup changed, the test fails until the
  spec is re-extracted.
- `FIDELITY_ENFORCE=1` makes the run fail unless every page reaches the threshold at every width. Use it as the
  gate after the restyle (REV-0295).
- Mockup-only run (no backend, no database), to extract or verify the specs:
  `FIDELITY_EXTRACT=1 E2E_BROWSER_CHANNEL=msedge npx playwright test -c e2e/fidelity/extract.config.ts`

## Targets (specs)

| Page | Mockup | Spec |
|---|---|---|
| 4 | `04_product_style/product_style_360.html` (+ desktop/laptop/tablet/mobile.png) | extracted |
| 29 | `29_36_commercial_planning_admin/index.html?page=29` (+ previews/page29_*.png) | extracted |
| 33 | `29_36_commercial_planning_admin/index.html?page=33` (+ previews/page33_*.png) | extracted |
| 1, 2 | only the concept PNGs in `01_02_concepts/` | **hand-authored** |

**How a spec is extracted.** `config.ts` names each region (id, Persian label, kind) and gives the CSS selector
of that region in the mockup. It also lists which child labels the region requires. Regions include the header,
action buttons, KPI cards, filter bar, main panels, tables, side panels, events, charts, side menu and top bar
(search, date, user).

`fidelity.spec.ts` opens the mockup read-only from `handoff/` with Playwright, using the same browser channel as
the e2e suite. It renders the mockup at each width and records the following into `specs/page-XX.json`:
- each region's box, normalised to the content area (`<main>`; see Layout below);
- the texts of the required children (headings, column headers, field labels, button labels, KPI titles);
- item counts (KPI cards, nav links);
- the radius, border and shadow, and the heading size;
- the content padding;
- the sha256 of every mockup file used.

If a region is not visible at a width in the mockup (for example the side menu at 390, which is a drawer there),
that region is not required at that width. Parts that are deliberately not regions are listed in the spec under
`excluded`, for example the catalogue's page chips between pages 29 and 36 and the demo captions.

**Pages 1 and 2 (hand-authored).** No HTML mockup exists for these pages. Their boxes were read off the concept
PNGs by eye:
- The desktop concept (tab «خلاصه») gives the boxes for 1440 and 1180.
- The mobile concept gives the boxes for 390. It is also used for the page body at 768, which is an assumption:
  there is no tablet concept.
- **Shell at 768 (DEC-061 amendment, 2026-11-18).** At 768 the shell regions (`side-menu`, `topbar`,
  `topbar-search`, `topbar-date`, `topbar-user`, `menu-toggle`) are not the scaled phone concept. Their 768 targets
  are copied unchanged from the catalogue's shared shell in `specs/page-29.json` at 768 (the same targets as page 33;
  page 33 differs only in `topbar-search`, by less than 0.01 of the width). The body regions at 768 stay the phone
  concept scaled. `source_note` of both specs says this.
- The concepts do not show page 2's «سفارش» tab. Its frame is the same picture. The tab body sits where the summary
  cards and the events are in the picture, and its sections follow the DEC-027 structure.

Each of these specs says this in `source_note`. Its style references are estimates. The extractor never
overwrites a hand spec.

## Score

Score per width = **0.5 × presence + 0.3 × layout + 0.2 × style**. The weights are in `config.ts`.

- **Presence.** The score is the mean over the regions required at that width. A region scores
  `(visible + required child labels found + min(items/required, 1)) / (1 + children + 1 if items)`.
  - A region that is missing or not visible scores 0.
  - A label counts as found when at least 60 % of its words (2+ letters) occur in the region's visible text. Text is
    normalised first: ZWNJ is removed, Arabic ي/ك become ی/ک, digits become Latin and punctuation is dropped.
  - Only labels are required, never values. **Mock numbers in a mockup are never required.**
  - A region whose data belongs to a later phase (`later_phase` in the spec) counts as fully present when it is in
    place with an honest «در دست ساخت» placeholder (DEC-027 / DEC-061).
- **Layout.** This is the share of required regions whose built box has IoU ≥ 0.5 with the mockup box.
  - Content regions are normalised to the content area (`<main>`): x and width are divided by the content width;
    y (from the content top) and height are also divided by the content **width**, so the aspect ratio is kept.
  - Viewport regions (side menu, top bar) are normalised to the page width.
  - Note: at 768 the page-4 mockup itself overflows its content area (negative x in `page-04.json`). The spec
    records what the mockup renders.
  - **Extra sections (DEC-061 amendment, 2026-11-18).** The layout part also carries a penalty for sections that
    the mockup does not have but that sit above or between its regions (see "Extra sections" below).
- **Style.** This is the mean of the checks that apply:
  1. the side menu is visible with ≥ 3 icons (where the mockup hides it, a menu toggle is required instead);
  2. the median radius of cards and panels is within ±4 px of the mockup's;
  3. built panels have a border or a shadow;
  4. the font family is Vazirmatn;
  5. the page-header heading size is within ±25 % of the mockup's;
  6. the content padding is within ±8 px of the mockup's;
  7. the brand colours are right: the page background is `--color-bg` and the primary button is `--color-primary`.

**Colours and font come from the approved brand, not from the mockup.** The employer approved the brand in 00.6
(docs/ui/DESIGN_TOKENS.md, frontend/src/styles/tokens.css: logo green `--color-primary`, Vazirmatn). It takes
precedence over the mockup's colours and its Tahoma/Noto fonts. So the colour check compares the built page with
the tokens read at runtime from `:root`, and never with the mockup's hex values.

## Extra sections (DEC-061 amendment, 2026-11-18)

The employer allows a section that the work needs but the mockup lacks (for example page 4's style detail, code
issue and revisions) only **below all mockup content**, or in a separate tab or dialog. The scorer enforces this:

1. **Scan** (`measure.ts`, built page only). Starting at `<main>`, each element child is classified:
   - it carries the `data-fid` of a spec region of this page: skipped (its inside belongs to that region);
   - it only *contains* spec regions (page container, grid, tab panel): it is a wrapper and is scanned the same way;
   - otherwise, when it is visible and is, or contains, a section / panel (`EXTRA_SECTION_SELECTOR` in `config.ts`:
     `section, aside, article, form, table, .panel, .card, [role=region], [role=tabpanel]`): it is one **extra
     section**. Small elements that are not sections (a notice line, the page tabs `nav`) are not counted.
   - Dialogs, their backdrops and fixed overlays (`EXTRA_IGNORE_SELECTOR`, `position: fixed`) are never counted. A tab
     that is not the default view is not rendered or not visible at measurement time, so it is not counted either.
2. **Rule** (`score.ts`, `extraAbove`). The reference line is the bottom edge of the lowest **content** region of the
   spec that is required at that width and visible on the built page (built position). An extra section whose top
   edge lies above that line (above or between mockup regions, or overlapping the last one) is an offence. A section
   whose top is at or below the line is free. With no content region present there is no line and no offence.
3. **Penalty.** Each offence removes `EXTRA_PENALTY` = **0.05 of the total score**, taken from the layout part
   (`layout = max(0, in-place share − n × 0.05 / 0.3)`). The cap is therefore the whole layout weight (0.30). One
   offence alone takes a page that is otherwise at 100 % down to 95.0 %; any other loss then fails the page.
4. **Report.** Per width: `layout` (after the penalty), `in place` (before it), `extra_above` (count) and the labels
   of the offending sections (`tag.class[testid] «heading»`) in `BASELINE.md` / `baseline.json`. The free extra
   sections (below all mockup regions) are listed too (`extra_free`), so that a reader can see the scan found them.

## Built-page markers

The scorer finds a built region by `data-fid="<region id>"`, using the first visible match. Repeated items are
counted by `data-fid-item`, or by the direct children of the region when no item is marked.

A marker is added only where the matching region already exists on the page, and it changes nothing else. A
region that has no marker is reported as MISSING. That missing region is on the restyle to-do list in
`BASELINE.md`.

## Files

- `config.ts`: threshold, weights, widths and the mockup region map.
- `measure.ts`: the browser-side measurement, used for both the mockup and the built page (plus the extra-section
  scan on the built page).
- `score.ts`: the pure scoring and the Markdown report. Its unit tests are in `score.vitest.ts` (vitest).
- `fidelity.spec.ts`: the seed (synthetic data: one viewer, one product with one style, seven confirmed orders of that
  style - seven serials, the sample size of the page-4 mockup - and one HOLD change request; REV-0295), extraction or
  verification, the scoring run, and the
  screenshots.
- `extract.config.ts`: the mockup-only Playwright config.
- `specs/page-XX.json`: the targets.
