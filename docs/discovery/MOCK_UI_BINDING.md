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
