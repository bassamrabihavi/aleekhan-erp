# Mock / UI binding — how the DRAFT catalog maps to real APIs (PHASE_00 / 00.1)

Status: DRAFT rules. Sources: `handoff/08_UI_AND_UX/UI_HANDOFF_INSTRUCTIONS_FA.md`, `DESIGN_CATALOG_52/README_FIRST_FA.md`, `UI_PAGE_PHASE_MAP.csv`, catalog `API_CONTRACT.md` / `DATA_MODEL.md` / `QA_TESTS.md` per group, `00_START_HERE/DECISION_AND_PRECEDENCE.md` (level 5 = DRAFT prototypes), `PHASE_00.md` (forbidden: mock as ERP reality).

## 1. Status of the catalog
- 52 pages, all `DRAFT`, `approved=False` (UI_PAGE_PHASE_MAP.csv). Pages 1–2 have no HTML (DEC-027). Page 41 has no phase (CONFLICTS C-18).
- HTML/JS, sample numbers, KPI values, buttons and catalog API paths are **references for layout and flow only**, not approved behaviour, not data, not API contracts (precedence level 5).
- PHASE_00 binds **no** catalog page. Step 00.5 is a smoke shell only (CONFLICTS C-16).

## 2. Binding rules (normative for every UI step xx.5)
1. **No mock presented as real.** A screen element shows a value only if it comes from a real backend endpoint of the same commit. No hard-coded numbers, no fixture JSON in production bundles, no MSW/mock service worker outside unit tests.
2. **Unbound = visibly unavailable.** A widget whose endpoint does not exist yet is not rendered, or is rendered as a labelled placeholder `در دست ساخت — به داده واقعی متصل نیست` with no numbers. Placeholders are excluded from acceptance screenshots or explicitly labelled in the report.
3. **Blocked rules surface the decision.** If the API returns `409 RULE_NOT_APPROVED` with `decision_id`, the UI shows `این قاعده هنوز تصویب نشده است (DEC-xxx)` and disables the action; it never computes the rule client-side.
4. **Server is authority.** Buttons are shown/enabled from a server-side permission response (access gate), but hiding is cosmetic: every action is re-checked on the backend (SECURITY_BASELINE §1).
5. **Freshness is explicit.** Any imported/snapshot value (stock, Rahkaran code, tracker) displays `as_of`/source and a stale badge; never labelled real-time (SOURCE_MAPPING §7).
6. **Synthetic data is labelled.** Dev/test/staging seed data is synthetic, marked in-UI with an environment banner (`محیط آزمایشی — داده ساختگی`); production has none.
7. **Port, don't paste.** Catalog HTML/JS is not imported into the app; pages are rebuilt as React components on design-system tokens (RTL, 1440/1180/768/390, mobile cards, loading/empty/error/stale/forbidden/offline states).
8. **Every bound page has a binding sheet** (below) in its phase's xx.1, reviewed with the page owner before xx.5.

## 3. Binding sheet template (one per page, filled in that page's phase)
| Field | Content |
|---|---|
| Page / title / phase | e.g. 46 امنیت و کاربران / PHASE_01 |
| Owner (business) | role that signs UAT |
| Catalog reference | prototype path (read-only reference) |
| Entities | from DATA_TABLE.md |
| Element → endpoint | each table/card/field → `GET /api/v1/...` + JSON pointer |
| Action → endpoint | each button → `POST /api/v1/.../{action}` + permission id + idempotency + If-Match |
| States | loading / empty / error / stale / forbidden / offline text (fa) |
| Blocked elements | element → DEC-xxx |
| Catalog items rejected | elements of the prototype not adopted, with reason |
| Tests | Playwright spec names + 4 viewport screenshots + role allow/deny |

## 4. Catalog-to-module mapping (DRAFT paths → canonical module, CONFLICTS C-09/C-10)
| Catalog group (DRAFT) | Pages | Canonical module prefix (proposal) | Phase |
|---|---|---|---|
| 29_36 `/core/product-codes`, `/core/serials`, `/commercial/order-drafts` | 1,2,4,29,33 | `/identity/...`, `/commercial/...` | 02 |
| 07_08, 09_10, 11_12, 13_20 dies/cliches/jigs/skiving/package | 7–14,17 | `/engineering/...` | 03 |
| 05_06 `/serials/{id}/production-sheet`, `cut-list`; 13_20 BOM/OPC | 5,6,15,16 | `/engineering/bom-revisions`, `/engineering/opc-revisions`, production-sheet under `/engineering` or `/production` (decide in 04.1) | 04 |
| 29_36 planning, 51 | 3,30–33,51 | `/planning/...` | 05 |
| 13_20 warehouse/GAP, 43/44/49, 05_06 `/integrations/wh/imports`, `/erp/materials` | 18–20,24,43,44,49 | `/warehouse/...`, `/imports/...` | 06 |
| 21_28 `/cutting/...`, `/production/...` command style | 21–23,28,48 | `/production/...` (resource + action) | 07 |
| 21_28 `/qa/...`, `/qc/...`, 50 | 24,25,50 | `/quality/...` | 08 |
| 21_28 `/finished-goods/...`, `/dispatch/...` | 26,27 | `/fg/...`, `/dispatch/...` | 09 |
| 29_36 `/costing/...`, `/analytics/...`; 37_38 | 34,35,37,38 | `/costing/...`, `/reports/...` (no free query, C-12) | 10 |
| 29_36 `/admin/health`, `/admin/jobs`; 39,40,42,46 | 36,39,40,42,46 | `/admin/...`, `/platform/...` | 01 (+11) |
| 45_52 AI/rules | 45,47 | `/ai/...` read-only, `/admin/rules` | 11 |
| 52 pilot | 52 | to define (DEC-038) | 13/14 |

## 5. PHASE_00 binding
| UI element (00.5 smoke shell) | Endpoint (docs/api/openapi-draft.yaml) |
|---|---|
| system status chip | `GET /api/v1/health/ready` |
| footer build/version | `GET /api/v1/version` |
| "no access" state demo | `GET /api/v1/access-gate/check` → 401 / DENY |
