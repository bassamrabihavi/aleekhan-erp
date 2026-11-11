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

## 6. PHASE_01 binding sheets (01.1, DRAFT — reviewed with the page owner before 01.5)

Contract: `docs/api/openapi-draft.yaml` 0.5.0-draft (all PHASE_01 operations are `x-aleekhan-status: planned`,
implemented in 01.4). Permissions: `docs/security/PERMISSION_MATRIX_DRAFT.md` (PROPOSED, DEC-049). Catalog pages
are DRAFT, `approved=False`; prototypes were read as text only. Legend: **BOUND** = element → endpoint of this
contract; **BLOCKED (DEC)** = rendered disabled with `این قاعده هنوز تصویب نشده است (DEC-xxx)` when the API
answers `RULE_NOT_APPROVED`; **REJECTED** = catalog element not adopted (reason given). Every page: states
loading / empty / error (Persian message + retry) / stale (if `as_of`) / forbidden (403/404) / offline; RTL;
screenshots 1440/1180/768/390 (C-32); allow/deny Playwright test per role; environment banner on non-production.

### 6.0 Shared shell (all PHASE_01 pages)
| Element | Endpoint / rule | Status |
|---|---|---|
| login form (username, password) | `GET /auth/login` (CSRF cookie) then `POST /auth/login`; error text for 401 is one generic message (no "user not found") | BOUND |
| MFA code step | `POST /auth/mfa/verify` | BLOCKED (DEC-050) |
| forced password change at first login | `POST /auth/password/change` | BLOCKED (DEC-051) |
| user menu (name, logout, my sessions) | `GET /me`, `POST /auth/logout`, `GET /auth/sessions`, `POST /auth/sessions/{session_id}/revoke` | BOUND |
| role-aware navigation | `GET /me/permissions` → show a menu item only if a required action is granted (cosmetic; backend re-checks) | BOUND |
| step-up prompt | any 401 `MFA_REQUIRED` → MFA dialog, then retry with the same Idempotency-Key | BLOCKED (DEC-050) until a factor exists |
| footer version | `GET /version` (public, C-17) | BOUND (PHASE_00) |

### 6.1 Page 36 — سلامت سیستم و Job (owner: IT / مدیریت سیستم; PHASE_01 part per C-34)
Catalog: `29_36_commercial_planning_admin/index.html?page=36`.
| Element | Endpoint → field | Status |
|---|---|---|
| component status chips | `GET /admin/health` → `components[]` | BOUND |
| outbox backlog / dead letters | `GET /admin/health` → `outbox.pending`, `outbox.failed`, `outbox.dead_letter`, `outbox.oldest_pending_at` | BOUND |
| job counters | `GET /admin/health` → `jobs.running`, `jobs.queued`, `jobs.failed_24h` | BOUND |
| security counters | `GET /admin/health` → `security.failed_logins_24h`, `security.locked_users` | BOUND |
| job table (id, type, state, progress, time) + filter | `GET /admin/jobs?state=&job_type=` → `items[]`; `progress` shown only when not null (no invented %); duration computed in UI from `started_at`/`finished_at` | BOUND |
| job type flags (protected) | `GET /admin/job-definitions` → `protected`, `cancellable` | BOUND |
| "پایان امن" (safe cancel) | `POST /admin/jobs/{job_id}/request-cancel` (reason dialog, MFA step-up, If-Match + Idempotency-Key); disabled for `protected` or not `cancellable` | BOUND |
| "توقف اجباری" (force cancel) | — | REJECTED in PHASE_01 (C-31; DEC-024, PHASE_11) |
| KPI "سلامت کلی ۹۶٪" | — | REJECTED (no formula; fabricated number, C-34/C-43) |

### 6.2 Page 39 — تسک‌ها و تأییدها (owner: گردش کار; all units)
Catalog: `37_44_hr_workflow_docs_data/index.html?page=39`.
| Element | Endpoint → field | Status |
|---|---|---|
| inbox list + filters (همه / نیازمند تصمیم / در حال انجام / مسدود) | `GET /workflow/tasks?inbox=mine\|my_units&status=` → `items[]` (subject, status, assignee, due_at, related) ; "نیازمند تصمیم" = `GET /workflow/approvals?inbox=to_decide` | BOUND |
| counters (کارهای من، منتظر تأیید، مسدود، سررسید امروز) | counts derived only from the returned pages with explicit "حداقل" wording, or omitted; no stored KPI endpoint in 0.5.0 | BOUND (derived) — catalog sample numbers REJECTED |
| task detail panel | `GET /workflow/tasks/{task_id}` | BOUND |
| state stepper (ایجاد … بسته‌شدن) | `Task.status` mapped to STATE_TRANSITIONS §4.3 | BOUND |
| start / complete / block / unblock | `POST /workflow/tasks/{task_id}/start\|complete\|block\|unblock` | BOUND |
| "درخواست ارجاع" (reassign) | `POST /workflow/tasks/{task_id}/reassign` (reason) | BOUND |
| "ثبت نتیجه" / close | `POST /workflow/tasks/{task_id}/verify-close` (only for verifier ≠ completer) | BOUND |
| approval card (approve / reject / withdraw) | `GET /workflow/approvals/{approval_id}`, `POST …/approve\|reject\|withdraw` | BLOCKED (DEC-032) for approve/reject; withdraw BOUND |
| approval route display | `Approval.route[]` | BLOCKED (DEC-048) |
| SLA clock / SLA pause | — | REJECTED in PHASE_01 (no approved rule, STATE_TRANSITIONS §4.3) |
| meetings, referrals, notifications panel | — | REJECTED in PHASE_01 (no entity/contract; notification channel not decided) |
| serial references ("سریال ۲۴۵۱") | `Task.related` shown as entity type/id only; serials exist from PHASE_02 | BOUND (generic ref) |

### 6.3 Page 40 — مدیریت اسناد (owner: سرویس اسناد; PHASE_01 part)
Catalog: `37_44_hr_workflow_docs_data/index.html?page=40`.
| Element | Endpoint → field | Status |
|---|---|---|
| document list + type filter (DXF/BOM/OPC/IMG/DOC) | `GET /documents?document_type=&entity_type=&entity_id=` | BOUND (type keys are data, no hard-coded list) |
| breadcrumb "Product → Style → Serial" | `Document.owner_entity` (type/id) | BOUND as generic ref; product/style/serial resolution PHASE_02+ |
| revision table (نسخه، وضعیت، تأییدکننده) | `GET /documents/{document_id}/revisions` → `revision_no`, `status`, `approved_by`, `scan_status` | BOUND |
| hash / size / type | `DocumentRevision.sha256`, `size_bytes`, `media_type` (server-detected) | BOUND |
| upload new revision | `POST /documents/{document_id}/revisions` (multipart) → shows QUARANTINED badge until CLEAN | BLOCKED (DEC-053) |
| download | `GET …/revisions/{revision_id}/content` (attachment; enabled only when CLEAN) | BOUND |
| submit / approve / reject | `POST …/submit-review`, `…/approve`, `…/reject` | submit BOUND; approve/reject BLOCKED (DEC-032) |
| UNC path "Y:\\…" | `Document.legacy_location_ref` as plain text with label "مرجع قدیمی (فقط متن)" | BOUND (text only, C-29) |
| check-out / check-in | — | REJECTED in PHASE_01 (C-46) |
| "فایل با خطای Hash" counter | — | REJECTED (no integrity-run endpoint for documents in 0.5.0) |

### 6.4 Page 42 — پارامترها و چیدمان UI (owner: مدیریت سیستم; PHASE_01 part per C-33)
Catalog: `37_44_hr_workflow_docs_data/index.html?page=42`.
| Element | Endpoint → field | Status |
|---|---|---|
| parameter catalogue table | `GET /admin/parameters` → key, label_fa, datatype, owner_module, classification, active value | BOUND |
| value history | `GET /admin/parameters/{parameter_key}/values` | BOUND |
| define parameter | `POST /admin/parameters` | BOUND |
| propose value (effective_from) | `POST /admin/parameters/{parameter_key}/values` | BOUND |
| publish | `POST …/values/{value_revision_id}/publish` | BLOCKED (DEC-032); BUSINESS_RULE parameters BLOCKED by their own decision id |
| dynamic field list / create / edit label (system key read-only) | `GET/POST /admin/dynamic-fields`, `PATCH /admin/dynamic-fields/{field_key}` | BOUND (DRAFT only) |
| zone designer, ordering, form preview, layout publish/rollback | — | REJECTED in PHASE_01 → PHASE_11 (C-33) |
| counters ("پارامترهای فعال ۲۸" …) | — | REJECTED (sample numbers) |

### 6.5 Page 46 — امنیت و کاربران (owner: مدیریت سیستم / کارفرما)
Catalog: `45_52_ai_security_pilot/index.html?page=46`.
| Element | Endpoint → field | Status |
|---|---|---|
| user list + status filter + search | `GET /admin/users?status=&q=` | BOUND |
| create user | `POST /admin/users` | BLOCKED (DEC-051) (initial credential) |
| user detail / edit | `GET/PATCH /admin/users/{user_id}` | BOUND |
| disable / enable / unlock | `POST /admin/users/{user_id}/disable\|enable\|unlock` (reason, MFA) | BOUND |
| reset password / reset MFA | `POST …/reset-password`, `…/reset-mfa` | BLOCKED (DEC-051 / DEC-050) |
| sessions of user + revoke all | `GET /admin/users/{user_id}/sessions`, `POST …/sessions/revoke-all` | BOUND |
| roles list / role detail with permissions | `GET /admin/roles`, `GET /admin/roles/{role_id}`, `GET /admin/permissions` | BOUND |
| create/edit DRAFT role | `POST /admin/roles`, `PATCH /admin/roles/{role_id}` | BOUND |
| activate role | `POST /admin/roles/{role_id}/activate` | BLOCKED (DEC-049) |
| role assignments (grant with scope + validity, revoke) | `GET/POST /admin/role-assignments`, `POST …/{assignment_id}/revoke`; self-assignment shows a warning and is flagged | BLOCKED (DEC-049) for grant; revoke BOUND |
| "role × action" yes/no table (catalog sample) | `GET /admin/users/{user_id}/effective-permissions` (explain view) | BOUND — catalog sample rows REJECTED |
| security events / access history | `GET /audits?resource_type=user&…` (MFA step-up) | BOUND |
| counters (کاربران فعال ۴۲، ورود ناموفق ۳ …) | `GET /admin/health` → `security.*`; user count only from list paging | BOUND for security.*; sample numbers REJECTED |
| temporary access / Break Glass | — | REJECTED in PHASE_01 → DEC-054 |
| "درخواست بازبینی دسترسی" | — | REJECTED (C-28: role changes are direct grants by owner/admin; review cycle not decided) |

### 6.6 Org tree view (DEC-043; new view inside page 46 or its own route)
| Element | Endpoint → field | Status |
|---|---|---|
| tree (units → positions → holders) with expand/collapse, keyboard navigation (arrow keys, `aria-expanded`), mobile = nested cards | `GET /org/tree?as_of=&root_unit_id=&depth=` → `roots[]` recursively; `truncated` → "بیشتر…" loads the subtree with `root_unit_id` | BOUND |
| "as of" date picker (Jalali display, UTC query) | `as_of` | BOUND |
| unit detail / edit / move / deactivate | `GET/PATCH /org/units/{unit_id}`, `POST …/move`, `POST …/deactivate` | BOUND |
| create unit / position / put a user in a position | `POST /org/units`, `POST /org/positions`, `POST /org/position-assignments` | BLOCKED (DEC-048) (unit types, holder kinds) |
| reports-to line | `Position.reports_to_position_id` | BOUND (display) |
| "approval route follows the tree" indicator | — | BLOCKED (DEC-048) |
| holder names | `holders[].display_name`, visible per `platform.org.read` | BOUND (DEC-048 may restrict) |

### 6.7 Catalog API names → 0.5.0 operations (for traceability)
| Catalog (DRAFT) | 0.5.0 |
|---|---|
| 39 ListTaskInbox / GetPendingApprovals / CreateTask / AssignTask / CompleteTask / RequestReassignment / ApproveTaskClosure | listTasks / listApprovals / createTask / reassignTask / completeTask / reassignTask / verifyCloseTask |
| 39 GetTaskDependencies | `Task.blocked_by` (no dependency graph in PHASE_01) |
| 40 SearchDocumentRegistry / GetDocumentRevisions / ValidateFileHash / SubmitDocumentReview / ApproveRevision | listDocuments / listDocumentRevisions / `DocumentRevision.sha256` (server-computed) / submitDocumentRevision / approveDocumentRevision |
| 40 CheckoutDocument / CheckinDocument | not adopted (C-46) |
| 42 GetParameterCatalog / CreateParameterDraft | listParameters / createParameterDefinition + proposeParameterValue |
| 42 PreviewLayout / ReorderLayoutFields / ValidateLayout / SubmitLayoutApproval / PublishLayoutRevision / RollbackLayout | PHASE_11 (C-33) |
| 46 ListUsers / GetEffectivePermissions / GetSecurityEvents | listUsers / getUserEffectivePermissions / listAuditEvents |
| 46 RequestRoleChange / ExpireTemporaryAccess / RequestBreakGlass | createRoleAssignment (direct, C-28) / `RoleAssignment.valid_to` / DEC-054 |
| 36 admin/jobs, request-cancel, request-force-cancel, admin/health | listJobs, requestJobCancel, — (C-31), getHealthDetail |

## 7. PHASE_02 binding sheets (02.1, DRAFT — reviewed with the page owner before 02.5)

Contract: `docs/api/openapi-draft.yaml` **0.7.0-draft**. Every PHASE_02 operation is `x-aleekhan-status: planned`
and `x-aleekhan-step: '02.4'`, and none is routed yet. Permissions are proposals (`identity.*`, `commercial.*`)
waiting for **DEC-057**. Until then no role holds them, so every page answers 403 for everyone except where a
PHASE_01 role is explicitly extended by DEC-057. Catalog pages are DRAFT, `approved=False`; prototypes were read as
text and images only.

Legend as in §6: **BOUND**, **BLOCKED (DEC)**, **REJECTED**, plus **LATER (PHASE_xx)** = a widget whose data belongs
to a later phase. A LATER widget is not rendered, or shows the placeholder `در دست ساخت — به داده واقعی متصل نیست`
with no number (rule 2). Every page has the states loading / empty / error (Persian message + retry) /
stale (if `as_of`) / forbidden (403/404) / offline, is RTL, has screenshots at 1440/1180/768/390, an allow/deny
Playwright test per role, and the environment banner outside production. Codes and serials are always shown LTR
inside RTL text (`dir="ltr"`, monospace), never with Persian digits, never re-formatted.

### 7.0 Shared elements (all PHASE_02 pages)
| Element | Binding |
|---|---|
| Code display | `Code14` string as returned; copy button copies the exact 14 characters; no thousands separator, no digit conversion |
| Serial display | `serial_number` string as returned; the customer's own serial is shown only as an ExternalRef with its namespace label |
| "Rule not approved" banner | any 409 `RULE_NOT_APPROVED` → `این قاعده هنوز تصویب نشده است (DEC-005)` / `(DEC-006)` / `(DEC-057)` / `(DEC-059)`; the action stays disabled |
| Search box (serial / style / product / PO no.) | `listSerials?q=`, `listProducts?q=`, `listCustomerOrders?external_po_number=` (server-side search, cursor pagination) |
| Dates | ISO date from the API → Jalali display (Asia/Tehran); input in Jalali, sent as ISO |

### 7.1 Page 1 — مرکز کنترل سریال، نمای خلاصه (owner: برنامه‌ریزی; DEC-027 for layout)
Catalog reference: no HTML (`prototype_path: null`); concept image `01_02_concepts/داشبورد_کنترل_سریال_*.png` (layout only).
| Element (concept) | Binding | Status |
|---|---|---|
| Serial header: number, product name, product code, customer/brand, required grade label, quantity, program/week | `getSerial` → `serial_number`, `style`, `product_code`, `customer`, `brand`, `quantity`, `uom`; `required_quality_requirement` (text label only, C-68); program = `program_ref` text | BOUND (after DEC-006 serials exist) |
| Status chip ("در تولید") | `Serial.status` (PHASE_02 values ALLOCATED / CANCELLED only) | BOUND; production states LATER (PHASE_07) |
| "Fast Track" tag | — | LATER (PHASE_05, DEC-014) |
| Product photo | — | REJECTED for PHASE_02 (no approved image source; documents module could hold it later) |
| Stage tracker (مواد و انبار → مهندسی → تأمین → برش → دوخت → کنترل کیفیت → آماده محصول) with WIP/Hold counts | — | LATER (PHASE_03/06/07/08/09); rendered as the placeholder; never with sample numbers |
| Active problems (material shortage, machine failure) | — | LATER (PHASE_06/07) |
| Decisions and tasks | `listTasks` / `listApprovals` filtered by `resource = serial` (PHASE_01 operations) + `listChangeRequests?serial_id=` | BOUND (change requests); tasks/approvals BOUND |
| Overall progress %, produced/remaining/FG/shipped counts | — | LATER (PHASE_07/09; Quantity Ledger, not a text state) |
| Material readiness %, complete/shortage/hold/awaiting counts | — | LATER (PHASE_06) |
| Current location (line, station counts, last record) | — | LATER (PHASE_07) |
| Quality standard and grade split | — | LATER (PHASE_08, DEC-019) |
| Bottom navigation (خانه، برنامه‌ریزی، ثبت، گزارش‌ها، بیشتر) | shared shell navigation of PHASE_01; "ثبت" opens page 29 if `commercial.order.manage` is held | BOUND (shell) |
| Notifications badge | PHASE_01 notifications are not implemented (01.2 note) | REJECTED until a notification endpoint exists |

### 7.2 Page 2 — مرکز کنترل سریال، تب سفارش (owner: بازرگانی + برنامه‌ریزی; DEC-027)
Catalog reference: no HTML; concept image `01_02_concepts/داشبورد_مدیریت_تولید_سریال_*.png` (layout only).
| Element | Binding | Status |
|---|---|---|
| Order header (order no., customer PO no., customer, brand, order type, order date, requested due date, status, current version) | `getCustomerOrder` | BOUND |
| Lines table (line no., style, style revision, product code, quantity + uom, due date, line status, serial) | `getCustomerOrder.lines[]` | BOUND |
| Serial snapshot of this line (what was committed) | `listSerialSnapshots` (latest + history) | BOUND (after DEC-006) |
| Order version history (v1 at confirm, one per applied change) | `listCustomerOrderVersions`, `getCustomerOrderVersion` (diff rendered client-side between two images) | BOUND |
| External references (Rahkaran project code, contract no., customer style/serial) | `listExternalRefs?target_type=customer_order&target_id=` and per line/serial | BOUND (namespaces: DEC-058) |
| Timeline (created, validated, confirmed, allocated, changes) | `getSerialTracking.events[]` (audit-backed, ids + times only) | BOUND |
| Actions: validate, reopen, confirm, release to plan, cancel (DRAFT/VALIDATED), allocate serial, request change | `validateCustomerOrder`, `reopenCustomerOrder`, `confirmCustomerOrder` (BLOCKED DEC-057/DEC-006), `releaseCustomerOrderToPlan` (BLOCKED DEC-057), `cancelCustomerOrder`, `allocateSerial` (BLOCKED DEC-006/DEC-057), `createChangeRequest` (BLOCKED DEC-059) | BOUND / BLOCKED as listed |
| Price, margin, invoice | — | LATER (PHASE_10); never in PHASE_02 |

### 7.3 Page 4 — ردیابی محصولات و استایل‌ها / Product 360 (owner: مهندسی + برنامه‌ریزی)
Catalog reference: `04_product_style/product_style_360.html` + `README_FA.md` (DRAFT).
| Element (catalog) | Binding | Status |
|---|---|---|
| Product profile (class path, product no., name, unit, status, product codes) | `getProduct`, `listProductCodes?product_id=` | BOUND (class levels and segment values BLOCKED DEC-005: shown as labels only) |
| Style list in the side column | `listProductStyles` | BOUND |
| Style revisions (colour, material text, hardware) | `listStyleRevisions` | BOUND |
| Serial table/cards "رنگ و جنس واقعی هر سریال" | `getStyleTracking.serials[]` (each with its own snapshot attributes, not the current style attributes) | BOUND (after DEC-006) |
| KPIs: related serials, active serials, number of orders | `getStyleTracking.counts` (`serials_total`, `serials_active`, `orders_total`: counts computed by the server from the same commit) | BOUND |
| KPIs: WIP, risk | — | LATER (PHASE_07 Quantity Ledger; PHASE_05 risk) |
| Filters: customer, material, colour, period, status, search | server filters of `getStyleTracking` (`customer_id`, `status`, `from`/`to`); material/colour = text match on snapshot attributes | BOUND (material/colour masters LATER PHASE_04/06) |
| Distribution chart and event history | history = `getSerialTracking` per serial; distribution chart only over the counts above | BOUND (no WIP distribution) |
| Buttons "خروجی Excel", "تنظیم ستون‌ها", "ایجاد محصول" | "ایجاد محصول" → `createProduct` (if permitted); Excel export and column settings | BOUND (create) / REJECTED in PHASE_02 (export: no approved export policy; CSV formula injection rule SECURITY_BASELINE) |
| Similar styles | `findSimilarStyles` (suggestion with reasons; never a merge, C-71) | BOUND |

### 7.4 Page 29 — ثبت سفارش و کدگذاری (owner: بازرگانی / Core; serial with planning approval)
Catalog reference: `29_36_commercial_planning_admin/index.html?page=29` (+ `app.js`, read as text).
| Element (catalog) | Binding | Status |
|---|---|---|
| Wizard step 1: customer/brand, order type, customer program, customer PO no., customer representative, required grade | `listCustomers`, `listCustomerBrands`, `createCustomerOrder` (`order_type`, `program_ref`, `external_po_number`, `required_quality_requirement`); duplicate-PO warning from the create/validate response | BOUND; **representative name REJECTED** (customer contact, DEC-028; C-54); grade list BLOCKED (DEC-019, text only) |
| Wizard step 2: nature, product type, sub-group, product no., style no., 14-digit preview | `listProductClasses` (labels), `listProducts`, `listProductStyles`; `validateProductCode` for an entered code; `previewProductCode` | BOUND for choosing an existing product/style/code; **preview BLOCKED (DEC-005)**: the catalog's fixed segment string and `padStart` logic are REJECTED (C-50/C-51) |
| Wizard step 3: quantity, order date, requested due date, colour, main material, hardware colour | `addCustomerOrderLine` (`quantity`, `uom`, `requested_due_date`); colour/material/hardware = attributes of the chosen style revision (`createStyleRevision` if new, engineering approval) | BOUND |
| Wizard step 4: checklist before sending to planning | `validateCustomerOrder` (server-side checks; the response lists failed checks) then `confirmCustomerOrder` | BOUND / confirm BLOCKED (DEC-057, DEC-006) |
| KPI "کد ۱۴رقمی نمونه" | — | REJECTED (a sample code shown as data; rule 1) |
| KPI "آمادگی فرم ۸۲٪", "مرحله ۲ از ۴" | wizard step counter is client state; readiness % REJECTED (no formula) | step counter BOUND (client) / % REJECTED |
| "بررسی استایل‌های موجود" table with verdicts | `findSimilarStyles` | BOUND (suggestions only) |
| Main action "بررسی و ارسال به برنامه‌ریزی" | `validateCustomerOrder` → `confirmCustomerOrder` → (planning) `allocateSerial` | BLOCKED (DEC-057, DEC-006) |
| Double-click protection | one `Idempotency-Key` per wizard submission, kept across retries (ID-04) | BOUND |

### 7.5 Page 33 — تغییرات سفارش و مهندسی (PHASE_02 part per C-61; PHASE_05 adds impact)
Catalog reference: `29_36_commercial_planning_admin/index.html?page=33`.
| Element (catalog) | Binding | Status |
|---|---|---|
| Request list (id, kind, serial, reason, state) | `listChangeRequests` (`kind`, `status`, `order_id`, `serial_id` filters) | BOUND |
| Before/after comparison | `getChangeRequest.items[]` (`old_value`, `new_value`) | BOUND |
| "تحلیل اثر موردنیاز" | `getChangeRequestImpact`: PHASE_02 part = affected lines, serials, snapshots, order version; sections `materials`, `wip`, `capacity`, `cost` answer `available: false` | BOUND (identity/order) / LATER (PHASE_05/06/07/10) |
| Approval gates (engineering, warehouse/supply, planning and QA) | PHASE_02 = one approval per request (`decideChangeRequest`); multi-gate routing per module later (DEC-048 "each module approves its route in its phase") | BLOCKED (DEC-057 approver, DEC-059 kinds); extra gates LATER |
| ECR/ECO cases (pattern change R4 → R5) | — | LATER (PHASE_03/04) |
| Cancellation with WIP disposition | `createChangeRequest(kind=CANCEL_ORDER / CANCEL_LINE)`; disposition | BLOCKED (DEC-059); disposition LATER (PHASE_05/07) |
| KPIs (open requests 14, needing impact 5, applied 23, cancellations 2) | counts from `listChangeRequests` with `status` filter (`page.total` is not in the contract; counts only if 02.4 adds a `counts` endpoint) | REJECTED as shown (sample numbers); BOUND later only from a server count |
| "پیشنهاد تصمیم" / "ثبت تصمیم روی درخواست" | `decideChangeRequest`, then `applyChangeRequest` | BLOCKED (DEC-057, DEC-059) |

### 7.6 Catalog API names → 0.7.0 operations (traceability)
| Catalog (DRAFT) | 0.7.0 operation |
|---|---|
| `POST /commercial/order-drafts` | `createCustomerOrder` (+ `addCustomerOrderLine`) |
| `POST /core/serials/allocate` | `allocateSerial` (`POST /identity/serials`) |
| `POST /core/product-codes/preview` | `previewProductCode` (BLOCKED DEC-005) |
| `GET /core/styles/similar` | `findSimilarStyles` (`GET /identity/style-suggestions`) |
| `POST /change/requests` | `createChangeRequest` |
| `GET /change/requests/{id}/impact` | `getChangeRequestImpact` |
| `POST /change/requests/{id}/decision` | `decideChangeRequest` (+ `applyChangeRequest`) |
| handoff `/product-codes/validate` | `validateProductCode` |
| handoff `/revisions` | `listCustomerOrderVersions`, `listStyleRevisions`, `listSerialSnapshots`, `listCodeRuleRevisions` |
