# Design tokens — DRAFT (PHASE_00 / 00.5; brand colours 00.6)

Status: **DRAFT**. Derived from the DRAFT design catalog, which is *not approved page by page*
(`handoff/08_UI_AND_UX/DESIGN_CATALOG_52/manifest.json`: `"approval": "NOT approved page-by-page"`). Precedence:
catalog = level 5 reference (`handoff/00_START_HERE/DECISION_AND_PRECEDENCE.md`). Tokens can change when page
owners sign off pages in later phases; change this file first, then `frontend/src/styles/tokens.css`.

Implementation: [`frontend/src/styles/tokens.css`](../../frontend/src/styles/tokens.css) (CSS custom
properties) and [`frontend/src/styles/base.css`](../../frontend/src/styles/base.css) (components on tokens).

## 1. Sources read (read-only, no HTML/JS copied into the app — MOCK_UI_BINDING §2 rule 7)

| Ref | File |
|---|---|
| S1 | `DESIGN_CATALOG_52/29_36_commercial_planning_admin/assets/styles.css` (`:root` block, shell, `.panel`, `.btn`, `h1`, breakpoints) |
| S2 | `DESIGN_CATALOG_52/45_52_ai_security_pilot/assets/styles.css` (identical `:root` to S1 — shared catalog shell) |
| S3 | `DESIGN_CATALOG_52/03_planning/planning_control_tower.html` (`:root`: ink/sub/navy/blue/line/bg/teal/gold/amber/red; font stack) |
| S4 | `DESIGN_CATALOG_52/09_10_die_detail_supply/index.html` (`:root`: tinted status backgrounds `goldbg`, `redbg`, `lightgreen`; radii 8/9/12px; breakpoints 600/820/1199) |
| S5 | `DESIGN_CATALOG_52/04_product_style/product_style_360.html` (`:root` palette, cross-check) |
| S6 | `DESIGN_CATALOG_52/29_36_commercial_planning_admin/previews/page29_laptop.png` (visual: top bar, cards, chips, env badge "داده نمایشی") |
| S7 | `08_UI_AND_UX/UI_HANDOFF_INSTRUCTIONS_FA.md` (RTL, 1440/1180/768/390, mobile cards, loading/error/empty/forbidden/stale/offline, as-of) |

## 2. Tokens

### Colour
| Token | Value | Source | Note |
|---|---|---|---|
| `--color-bg` | `#f5f6f8` | S1 `--bg`, S3 `--bg` | page background |
| `--color-surface` | `#ffffff` | S1 `--paper` | cards |
| `--color-surface-muted` | `#f9fbfd` | S1 `.panel` alt background | table header, loading |
| `--color-ink` | `#1b293b` | S1 `--ink` | body text |
| `--color-muted` | `#5f7186` | S1 `--muted` `#697d91` **darkened** | D1 |
| `--color-line` | `#e5eaf0` | S1 `--line`, S3 `--line` | borders |
| `--color-primary` | `#01392d` | **logo sample** (§5, 00.6; was S1 `--blue` `#2164ae`) | primary buttons, links, focus, skip link, spinner |
| `--color-primary-hover` | `#0a4d3e` | derived: same hue 167°, lightness 11 % → 17 % (lighter, so the hover is visible on a near-black green) | |
| `--color-primary-tint` | `#e8f2ef` | derived: logo hue at ≈93 % lightness | |
| `--color-brand-gold` / `-bg` / `-line` | `#875d22` / `#f7f1e6` / `#e4d5bd` | S1 `.emblem` | eyebrow, env-banner border (the «ع» emblem was replaced by the logo in 00.6) |
| `--color-success` / `-tint` | `#1f7a35` / `#e9f6ec` | 00.6: moved from `#0b7a62`/`#e7f7f1` (hue 167° = the logo's hue) to leaf green hue 135° (D4) | D1, D4 |
| `--color-warning` / `-tint` | `#8a5a12` / `#fff6eb` | S1 `--amber` `#af761d` **darkened**; tint S4 `--goldbg` | D1 |
| `--color-danger` / `-tint` | `#b23c35` / `#fff0f1` | S1 `--red` `#c74d45` **darkened**; tint S4 `--redbg` | D1 |
| `--color-info` / `-tint` | `#2164ae` / `#f0f5fb` | S1 `--blue`, `--light` | |
| `--color-neutral` / `-tint` | `#4f5f72` / `#eef1f5` | derived from S1 muted | "unknown" status |

### Typography
| Token | Value | Source | Note |
|---|---|---|---|
| `--font-sans` | `"Vazirmatn", "Noto Sans Arabic UI", "Noto Sans Arabic", Tahoma, sans-serif` | S1/S3 stack + Vazirmatn | D2 |
| `--font-mono` | `ui-monospace, "Cascadia Mono", Consolas, monospace` | S1 uses `monospace` for codes | ids, commit, codes |
| `--font-size-xs/sm/md/lg/xl/2xl` | 12 / 13 / 14 / 16 / 18 / 23 px | S1 `h1` 23px (20px ≤1200, 18px ≤600) | D3: body 14px |
| `--font-weight-regular/medium/bold` | 400 / 600 / 800 | S1 (600–850 used) | |
| `--line-height-body` | 1.75 | readability of Persian script | |

### Spacing, shape, layout, motion
| Token | Value | Source |
|---|---|---|
| `--space-1..6` | 4 / 8 / 12 / 16 / 22 / 32 px | S1 paddings (13–22px rounded to a 4px scale; 22px kept: top-bar padding) |
| `--radius-sm/md/lg` | 8 / 9 / 13 px | S1 `.btn` 8px, nav 9px, `.panel` 13px; S4 8/9/12px |
| `--radius-pill` | 999px | chips (S6) |
| `--shadow-card` | `0 2px 13px rgba(30,51,72,.047)` | S1 `--shadow` |
| `--topbar-height` | 60px | S1 `.topbar` |
| `--tap-target` | 44px | WCAG 2.5.5 / mobile use (S1 `.btn` min-height 35px raised) |
| `--content-max` | 1280px | layout choice for 1440 width |
| `--duration-fast/base` | 140 / 230 ms | S1 transitions (.14s / .23s); 0 with `prefers-reduced-motion` |
| `--focus-ring` | white 3px + primary 2px (`#01392d`) | not defined in catalog — added (WCAG 2.4.7) |

### Breakpoints
`1200px` (laptop), `900px` (tablet), `600px` (mobile) from S1/S2 `@media`. CSS variables cannot be used inside
`@media`, so the numbers are repeated in `base.css`. Acceptance widths are 1440 / 1180 / 768 / 390 (S7).

## 3. Deviations from the catalog (with reason)

- **D1 — contrast (WCAG 2.1 AA 1.4.3, 4.5:1).** Catalog status colours used as text fail AA on white/tints
  (measured relative luminance): `#697d91` ≈ 4.25:1, `#0f987b` ≈ 3.6:1, `#af761d` ≈ 3.9:1, `#c74d45` on
  `#fff0f1` ≈ 4.15:1. Darkened to `#5f7186` (≈5.0:1 on white, ≈4.6:1 on `#f5f6f8`), `#0b7a62` (≈5.3:1, ≈4.8:1 on
  its tint), `#8a5a12` (≈5.9:1, ≈5.5:1 on its tint), `#b23c35` (≈5.85:1, ≈5.3:1 on its tint). Ratios computed
  with the WCAG relative-luminance formula. Hue kept. The E2E suite runs axe (wcag2a/aa,
  wcag21a/aa) on the page and fails on any violation.
- **D2 — font.** The catalog relies on system "Noto Sans Arabic"/Tahoma. The app bundles **Vazirmatn 33.0.3**
  (npm `vazirmatn`, SIL Open Font License 1.1 — redistribution allowed; licence text ships in
  `node_modules/vazirmatn/OFL.txt`). It is imported from the npm package and served from the app origin by the
  bundler — **no CDN at runtime** (E2E asserts that no request leaves the app origin). Catalog fonts remain in
  the fallback stack.
- **D4 — success vs brand green (00.6).** The logo green (hue 167°) has exactly the hue of the old success
  colour `#0b7a62`, so a green button and a green "OK" chip would read as the same signal. Success moved to hue
  135° (`#1f7a35`, lightness 30 % vs the primary's 11 %; the two colours differ 2.4:1 in luminance) **and** success
  chips show a check-mark shape instead of the round dot (`.chip--success .chip__dot`), so status never depends on
  hue alone. `--color-info` stays blue `#2164ae` on purpose: it is a status colour (not brand), and turning it green
  would collide with both primary and success.
- **D3 — base size 14px instead of 12px.** Catalog body text is 12px (S1 `html,body{font-size:12px}`); too
  small for shop-floor/tablet reading. Small meta text still uses 12–13px.

## 4. RTL and display conventions

- `<html lang="fa" dir="rtl">`; layout uses logical properties (`inline-start` = right, `block-end`), never
  hard-coded left/right.
- **Persian digits** for user-facing numbers, dates, times, HTTP status (`toFaDigits`).
- **Dates/times**: API sends RFC 3339 UTC; the UI renders Jalali (`fa-IR-u-ca-persian`) in `Asia/Tehran`
  (ADR-001). Nothing is stored in Jalali.
- **Machine identifiers stay Latin and LTR** in an isolated `<code dir="ltr">`: build commit, request id,
  error code, component technical name, (later) 14-digit codes — so they can be copied/searched exactly in
  logs and Rahkaran. This matches the catalog (S6 shows the 14-digit code in Latin digits).
- Status is never colour-only: every chip has a text label.
- Operational data shows its as-of time; stale data gets a "داده قدیمی" badge (MOCK_UI_BINDING §2 rule 5).
- Non-production environments show the banner "محیط … — داده ساختگی" driven by `GET /version.environment`
  (MOCK_UI_BINDING §2 rule 6).
- While a shown status is stale (last refresh failed, or older than the freshness window) its chips are rendered
  `neutral` with the same text (REV-0503, 00.6): the last known value is not presented as a live green "OK".

## 5. Brand colour from the logo (00.6)

Employer decision 2026-11-04 (docs/ui/brand/README.md): the logo's dark green becomes the primary colour.

**Sampling.** `python tools/sample_logo_colors.py` decodes `docs/ui/brand/aleekhan-logo.png` with the Python
standard library only (zlib + struct; no Pillow), keeps opaque pixels, drops white/grey, buckets the rest and
prints the average colour per bucket. Result (2026-11-04, sha256 `ef3fa9d1…4c64b33`): 300×298 px, 6 801 opaque
chromatic pixels; dominant bucket **`#01392d`** (6 613 px, hsl(167°, 97 %, 11 %)); second `#053c30` (188 px,
anti-aliasing edge of the same green). `--color-primary` is the dominant sample, unchanged. The app shows the logo
from `frontend/src/assets/brand/aleekhan-logo.png` (byte-identical copy, same sha256), height 44 px (38 px ≤ 600 px),
width from the 300:298 ratio, alt «لوگوی سراجی سنتی عالیخان», no recolouring.

**Contrast (WCAG 2.1 relative luminance; AA = 4.5:1 normal text, 3:1 large text / UI components).** All pairs
used by the shell and the system-status page:

| Use | Pair | Ratio | AA |
|---|---|---|---|
| text on primary button / skip link | `#ffffff` on `#01392d` | 12.93:1 | pass |
| text on primary hover | `#ffffff` on `#0a4d3e` | 9.79:1 | pass |
| primary text (secondary button, links) on surface | `#01392d` on `#ffffff` | 12.93:1 | pass |
| primary text on page background | `#01392d` on `#f5f6f8` | 11.96:1 | pass |
| primary text on primary tint | `#01392d` on `#e8f2ef` | 11.31:1 | pass |
| focus ring (UI, 3:1) vs surface / page bg | `#01392d` on `#ffffff` / `#f5f6f8` | 12.93:1 / 11.96:1 | pass |
| success chip text on success tint | `#1f7a35` on `#e9f6ec` | 4.84:1 | pass |
| success text on surface | `#1f7a35` on `#ffffff` | 5.39:1 | pass |
| ink on page bg / surface | `#1b293b` on `#f5f6f8` / `#ffffff` | 13.61:1 / 14.72:1 | pass |
| muted on surface / page bg | `#5f7186` on `#ffffff` / `#f5f6f8` | 5.01:1 / 4.63:1 | pass |
| warning on warning tint | `#8a5a12` on `#fff6eb` | 5.53:1 | pass |
| danger on danger tint | `#b23c35` on `#fff0f1` | 5.29:1 | pass |
| info on info tint | `#2164ae` on `#f0f5fb` | 5.48:1 | pass |
| neutral on neutral tint (incl. stale chips) | `#4f5f72` on `#eef1f5` | 5.77:1 | pass |
| brand-gold eyebrow on page bg | `#875d22` on `#f5f6f8` | 5.37:1 | pass |
| primary vs success (distinguishability only, not a text pair) | `#01392d` vs `#1f7a35` | 2.40:1 | — (plus hue 167° vs 135° and the check-mark shape, D4) |

Ratios computed with `tools/sample_logo_colors.contrast`; the E2E suite additionally runs axe (wcag2a/aa,
wcag21a/aa) on the ready, error and backend-down states and asserts the primary button's computed colour is
`rgb(1, 57, 45)`.
