# دفتر تصمیم‌ها

| تاریخ | شناسه | متن تصمیم | تصمیم‌گیرنده |
|---|---|---|---|
| 2026-11-03 | DEC-044 | گزینه B: بازگردانی یک‌باره بایت‌های CRLF برای ۱۳ CSV در handoff/؛ هش PACKAGE_MANIFEST.json نقص شناخته‌شده بسته | کارفرما |
| 2026-11-03 | DEC-045 | گزینه A: CI روی GitHub-hosted Actions فقط با داده ساختگی و بدون راز؛ اولین تمرین بازیابی Gate-0 روی محیط محلی؛ با آماده شدن سرور داخلی شرکت به runner خودمیزبان و تمرین روی staging منتقل شود | کارفرما |
| 2026-11-04 | DEC-046 | مخزن GitHub عمومی بماند (اصلاح نمایانی DEC-041؛ پاسخ REV-0701). همچنان هیچ داده خصوصی، رمز یا داده مشتری در مخزن؛ اسکن راز در CI گیت است | کارفرما |
| 2026-11-04 | DEC-047 | Gate-0: پذیرش حالت همه‌چیز بسته (deny-all)؛ تأیید ماتریس نقش‌ها و DEC-032 به گام ۰۱.۱ منتقل شد | بسام ربیهاوی (کارفرما) |

## 2026-11-04 — DEC-048 APPROVED
- **Decision:** جزئیات درخت سازمانی (ادامه DEC-043). پاسخ کارفرما ۲۰۲۶-۱۱-۰۴: (۴) مسیر تأیید ترکیبی (گزینه C)، ولی در فاز ۱ همه گردش‌ها فقط نقش + دامنه واحد (A)؛ هر ماژول مسیرش را در فاز خودش تصویب می‌کند. (۱) سطوح ثابت قابل افزایش توسط ادمین: COMPANY, DEPARTMENT, SECTION, LINE، حداکثر ۶ سطح. (۲) یک سمت اصلی + ACTING با تاریخ پایان؛ بدون سمت اضافی در فاز ۱. (۳) reports-to بین سمت‌ها. (۵) ویرایش فقط کارفرما/ادمین در فاز ۱. (۶) نام واحد/سمت/فرد برای همه کاربران داخلی؛ بدون اطلاعات تماس. (۷) تاریخچه با تاریخ اثر.
- **Decided by:** بسام ربیهاوی (کارفرما)
- **Unblocks:** createOrgUnit / createPosition / createPositionAssignment (01.4); Approval.route stays role+scope only in PHASE_01.

## 2026-11-04 — DEC-049 APPROVED
- **Decision:** تصویب ماتریس دسترسی فاز ۱ (`docs/security/PERMISSION_MATRIX_DRAFT.md`). matrix v0.1 approved (2026-11-04). پاسخ‌ها: (۱) هر ۱۱ نقش ساخته شوند. (۲) it_ops هم قفل کاربر را باز کند (با MFA و Audit؛ بدون تغییر رمز). (۴) کارفرما در شروع فقط owner_admin دارد؛ نقش‌های کسب‌وکار بعداً و صریح با علامت خودانتسابی. (۵) MFA تازه برای همه ردیف‌های MFA حتی داخل شبکه کارخانه. (۳) سطح دیدن اسناد جدا پرسیده نشد: پیش‌فرض v0.1 (EMP: S1، MGR/MGT: S1–S2) اجرا می‌شود و کارفرما می‌تواند تغییر دهد.
- **Decided by:** بسام ربیهاوی (کارفرما)
- **Unblocks:** activateRole / createRoleAssignment (01.4). Matrix doc to be promoted to APPROVED v1.0 in 01.2.

## 2026-11-04 — DEC-050 APPROVED
- **Decision:** روش ورود دومرحله‌ای. پاسخ کارفرما ۲۰۲۶-۱۱-۰۴: عامل دوم = TOTP (برنامه کد روی گوشی، مثل Google/Microsoft Authenticator)؛ کلید سخت‌افزاری/passkey بعداً اختیاری. بازیابی = ۱۰ کد بازیابی یک‌بارمصرف + بازنشانی توسط ادمین با دلیل، MFA ادمین و Audit (R1+R2)؛ بازیابی مالک طبق DEC-054. پنجره step-up در DEC-051.
- **Decided by:** بسام ربیهاوی (کارفرما)
- **Unblocks:** MFA enrolment/verify and resetUserMfa (01.3/01.4).

## 2026-11-04 — DEC-051 APPROVED
- **Decision:** سیاست رمز، قفل و جلسه. پاسخ کارفرما ۲۰۲۶-۱۱-۰۴: (۱) رمز به روش سنتی (گزینه B): حداقل ۸ نویسه + ترکیب اجباری (حرف بزرگ، عدد، نماد) + تعویض هر ۹۰ روز. (۲) رمز اولیه یک‌بارمصرف ساخته ادمین، اعتبار ۷۲ ساعت، تعویض اجباری در اولین ورود. (۳) قفل L1: ۵ ورود ناموفق در ۱۵ دقیقه → قفل خودکار ۱۵ دقیقه + اعلان در صفحه ۳۶/۴۶. (۴) جلسه S2 برای کاربران عادی (بی‌کاری ۲ ساعت، حداکثر ۱۲ ساعت) و S3 برای اپراتورها (بی‌کاری ۸ ساعت، فقط شبکه داخلی). (۵) حداکثر ۳ جلسه همزمان. (۶) پنجره step-up ۱۵ دقیقه.
- **Decided by:** بسام ربیهاوی (کارفرما)
- **Unblocks:** createUser / resetUserPassword / session policy (01.3/01.4).

## 2026-11-04 — DEC-052 APPROVED
- **Decision:** شبکه داخل کارخانه و مدل حساب اپراتور. پاسخ کارفرما ۲۰۲۶-۱۱-۰۴: شبکه N-A: فهرست صریح CIDR فقط در تنظیمات سرور (نه Git)، IP فقط از پراکسی معتمد؛ نامعلوم = بیرون؛ VPN = بیرون (MFA لازم). حساب اپراتور O-A: حساب شخصی هر اپراتور، فقط از شبکه داخلی؛ حساب ایستگاه + کارت/PIN در فاز ۷ با DEC-018 بررسی می‌شود.
- **Decided by:** بسام ربیهاوی (کارفرما)
- **Note:** IT must supply the factory CIDR list at deployment (server config only).

## 2026-11-04 — DEC-053 APPROVED
- **Decision:** بارگذاری فایل و قرنطینه (SEC-03). پاسخ کارفرما ۲۰۲۶-۱۱-۰۴: ضدبدافزار AV-A = ClamAV در کانتینر ایزوله روی همان سرور (بدون ارسال فایل به بیرون) + فهرست سفید نوع + بررسی magic bytes + سقف حجم. انواع مجاز: PDF، PNG، JPG، DXF، XLSX بدون ماکرو؛ XLSM/DOCM/EXE/اسکریپت هرگز. حداکثر ۲۵ مگابایت (تغییر برای DXF با تصمیم تازه). ذخیره ST-A: پوشه رمزگذاری‌شده روی سرور داخلی. فایل ردشده ۳۰ روز قرنطینه سپس حذف بایت‌ها (متادیتا و هش می‌ماند). هیچ فایل در مرورگر نمایش/اجرا نمی‌شود؛ فقط دانلود.
- **Decided by:** بسام ربیهاوی (کارفرما)

## 2026-11-04 — DEC-054 APPROVED
- **Decision:** دسترسی اضطراری و بازیابی ادمین تنها. پاسخ کارفرما ۲۰۲۶-۱۱-۰۴: C از ابتدا (دستور بازیابی روی کنسول سرور با دسترسی فیزیکی/SSH، بازنشانی رمز/MFA مالک با Audit) + A پیش از Production (حساب اضطراری مهروموم در گاوصندوق، هشدار فوری و Audit ویژه، جلسه ۲ ساعته، تعویض رمز پس از هر استفاده). B (ادمین دوم) فعلاً نه.
- **Decided by:** بسام ربیهاوی (کارفرما)

## 2026-11-04 — DEC-032 APPROVED
- **Decision:** الگوی maker-checker و نگهداری Audit. پاسخ کارفرما ۲۰۲۶-۱۱-۰۴: بخش ۱ = B (متوسط): maker≠checker برای approveDocumentRevision، publishParameterValue پارامترهای BUSINESS_RULE، و createRoleAssignment نقش‌های دارای حق تأیید کسب‌وکار؛ تا تعریف نفر دوم این موارد «در انتظار» می‌مانند. بن‌بست یک‌نفره = D1 (هرگز خودتأیید؛ تأیید اضطراری فقط با تصمیم بعدی). انقضای درخواست تأیید ۳۰ روز. بخش ۲ = R-A: Audit کسب‌وکار و دسترسی هرگز حذف نشود (بایگانی سالانه)؛ رخدادهای ورود ۲ سال؛ مدت الزام قانونی را مشاور حقوقی/مالی تأیید کند.
- **Decided by:** بسام ربیهاوی (کارفرما)

## 2026-11-05 — Employer answers to 01.2 open questions (detail of DEC-051/053/048/032; REV-0110)
- **Q-0101 (DEC-051):** on the 4th concurrent login the oldest session is ended automatically (audited).
- **Q-0102 (DEC-051):** operator absolute session limit 12 h.
- **Q-0103 (DEC-032):** OWNER_POLICY parameters are changed by the owner alone (owner_admin), no second person; MFA step-up + reason + audit.
- **Q-0104 (DEC-053):** 25 MB = 26,214,400 bytes.
- **Q-0105 (DEC-051):** password reuse check refuses the last 5 passwords.
- **Q-0106 (DEC-048):** a position may have several PRIMARY holders up to a per-position capacity (default 1).
- **Back-dating (DEC-048):** org-tree changes take effect only from now on; no past effective dates.
- **Decided by:** بسام ربیهاوی (کارفرما), in the Claude Code session.
- **2026-11-05 (REV-0109 follow-up, DEC-048):** no back-dating applies to person-to-position assignments too (valid_from and valid_to only from now on). Unit-head positions always have exactly one PRIMARY holder; a stand-in is recorded as ACTING. Decided by بسام ربیهاوی (کارفرما).

## 2026-11-05 — DEC-055 APPROVED: first holder of a business-approval role (REV-0116)
- **Decision:** option B. The owner (owner_admin) may approve, inside the system, his own request for the **first** holder of each business-approval role, once per role: only while that role has no ACTIVE holder, with a fresh MFA step-up, a mandatory reason, and a special audit flag (`bootstrap_self_approval`). From the second holder on, DEC-032 maker-checker applies unchanged.
- **Decided by:** بسام ربیهاوی (کارفرما), in the Claude Code session.
- **2026-11-05 (REV-0111 follow-up, DEC-049 operator cell):** an operator sees only the current APPROVED revision of a document linked to one of their open tasks. If a task is pinned to a revision and a newer revision is approved, the operator sees no revision until the task is re-linked (prevents building from a stale drawing). Decided by بسام ربیهاوی (کارفرما).

## 2026-11-06 — DEC-056 APPROVED: owner approval rights (permission matrix v1.1; amends DEC-003 for the owner)
- **Decision:** the owner role (`owner_admin`) reads **all** approval requests and holds the business **decide** right directly, without assigning himself a separate approver role. Every decision by the owner is audited with his role.
- **Unchanged:** nobody decides their own request (DEC-032 maker ≠ checker), except the one-time bootstrap approval of DEC-055. Other technical roles (IT, auditor) still hold no business approval.
- **Implementation:** permission matrix v1.1, a seed migration, and the DB guard "TECHNICAL role holds no business-approval permission" gets an explicit owner_admin exception. Scheduled with step 01.5.
- **Decided by:** بسام ربیهاوی (کارفرما), in the Claude Code session, as the answer to the 01.4 review question.
- **2026-11-10 (DEC-056 follow-up):** an in-app grant of `owner_admin` to another person needs a second approver (DEC-032); the console bootstrap of the owner stays exempt. Decided by بسام ربیهاوی (کارفرما).
- **2026-11-10 (DEC-056 extension, REV-0125; matrix v1.2):** the owner (`owner_admin`) also decides document revisions (approve/reject) and BUSINESS_RULE parameter publish requests directly. Maker ≠ checker unchanged: never his own request/proposal (except DEC-055). Decided by بسام ربیهاوی (کارفرما).
- **2026-11-10 (DEC-056 extension 2; matrix v1.3, scheduled in 01.7):** the owner (`owner_admin`) also reads all documents and downloads them (download only CLEAN files, audited), so he can open a file before deciding. Decided by بسام ربیهاوی (کارفرما), answer to the 01.6 question.
- **2026-11-10 (failed-event handling, REV-0133):** IT (`it_ops`) may also **replay** a dead-lettered event; **discard** stays owner-only (`owner_admin`, reason required). Both audited. Decided by بسام ربیهاوی (کارفرما), answer to the 01.7 question.

## 2026-11-11 — PHASE_01 Gate items (employer, Claude Code session)
- **UAT T-003 PASS:** the employer ran steps 1–5 in the browser. The orchestrator verified the rest on the UAT DB, and E2E passed 22.
- **Security checklist PHASE_01:** accept with conditions. Items 1.10, 2.6, 2.7, 3.4, 3.11 and 4.8 close before the production server and the pilot.
- **Technical defaults confirmed:**
  - login rate limit 20/min per IP and 10/min per username;
  - upload limit 25 MB;
  - housekeeping overdue alert after 26 h;
  - orphan-file grace 24 h;
  - notification retention 180 days.

  They stay changeable later. Decided by بسام ربیهاوی (کارفرما).
- **Scope splits confirmed:** as proposed in 01.1 and built:
  - C-33: page 42 has parameters and DRAFT dynamic fields; the rest is in PHASE_11.
  - C-34: page 36 has health, jobs and event delivery; the monitoring dashboards are in PHASE_11.
  - C-46: document check-out is in PHASE_12.

  Decided by بسام ربیهاوی (کارفرما).
- **Rollback boundary acknowledged:** once job runs exist, reversing 0011 is refused by design, and the way back is restore from backup (`docs/ops/ROLLBACK.md` §3a; drill PASS). Acknowledged by بسام ربیهاوی (کارفرما).

## 2026-11-11 — DEC-060 APPROVED: real customer data in handoff/ (public repo)
- **Facts:** the names in the handoff catalogue files are **real**. They are customer and brand names, a customer representative's name, a Rahkaran project code and an internal network path.
- **Decision:** option X-B + X-D.
  - The repo `bassamrabihavi/aleekhan-erp` becomes **private**. This amends DEC-046.
  - A one-time exception allows editing `handoff/`, like DEC-044. The values are replaced with a "redacted" label, and the changed hashes are recorded as a registered exception in `verify_handoff`.
  - Git history is **not** rewritten (no X-C).
- **Decided by:** بسام ربیهاوی (کارفرما).
- **2026-11-11 (DEC-060 amended, X-D only):** the permission system blocked the edit to `handoff/`. A read-only dry run then showed a much wider scope: 108 text values in 10 files, the concept images, about 140 preview images, a file name, and other brand names. So the employer chose **X-D only**:
  - The repo is made private.
  - `handoff/` stays untouched, so no exception is opened.
  - Rule R-38 stays in force: no new document, test, fixture or image may repeat these values.

  The X-B redaction is withdrawn. Decided by بسام ربیهاوی (کارفرما).

## 2026-11-11 — DEC-006 (serial), answers 1/2/4/5 — format still open
- **Namespace:** S-A, one counter for the whole factory.
- **Timing:** L-A. Every line gets its serial when the order is confirmed, in the same transaction. No confirmed line is ever without a serial.
- **Gaps:** **G-B, gapless.** The employer chose this over the recommended G-A. Allocation takes a row lock on the counter inside the confirm transaction, so a failed confirm does not consume a number. This trades throughput under high concurrency for no gaps. The ID-02 race test must prove both: no duplicates and no gaps.
- **Legacy:** P-A. Numbering continues after the largest legacy serial (Planning, paper, Rahkaran), plus a safety margin. The largest value comes from the Planning extraction.
- **Still open:** question 3, the format (prefix, length, leading zeros, check digit). It is to be read from the Planning workbook, with synthetic examples only. DEC-006 stays open until then.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-12 — DEC-006 APPROVED (serial format closed)
- **Evidence:** read-only, in-memory profile of `NOrder!B` in the Planning workbook (intake sha `113f5400…`, see `control/SOURCE_INTAKE.csv`). Only aggregates were taken. No serial value is stored in the repo.
  - 3,779 of the 3,920 entries are plain integers. They have no prefix and no leading zeros.
  - The recent entries are consecutive 5-digit numbers, and the largest legacy serial is below 63000. The column holds values entered by hand, with no formulas.
  - 141 legacy entries have other shapes: an `S` prefix (40), a `-digit` suffix (85), a `-P` suffix (13), a `-N` suffix (2) and a `BG` prefix (1). In addition, 2 values are duplicated.
- **Format (Q3):** a plain integer, with no prefix, no fixed length, no leading zeros and no check digit. It is stored as text (`varchar(32)`) so that legacy variants can be imported.
- **Start (P-A):** the first serial issued by the system is **63001**. The gap above the legacy maximum is the safety margin. The condition is that no paper or Rahkaran serial is 63000 or above; the import must verify this.
- **Legacy variants:** they are imported as **history only** and kept as text, exactly as they are. The new system never generates them. If a special kind is needed later, it gets its own decision. The 2 legacy duplicates are flagged at import and are not merged silently.
- **Combined with the 2026-11-11 answers:** S-A + L-A + G-B (gapless, counter row lock) + P-A.
- **Q6 (who allocates):** decided in DEC-057.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-12 — DEC-037 amendment (Planning baseline)
- **Decision:** the Planning workbook in `ALEEKHAN_PRIVATE_DIR` is the golden baseline. It has intake sha `113f5400…` and file mtime 2026-11-11.
- **Supersedes:** the 2026-11-03 copy, which is now history.
- **Scope:** golden tests and the DEC-005 extraction are locked to this hash.
- **Resolves:** C-22 / C-74 for Planning (hash recorded in `control/SOURCE_INTAKE.csv`).
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-12 — DEC-060 amended again: repo stays public (X-A)
- **Decision:** the employer does **not** want the repo made private. It stays public so that it can be used without passwords or logins. This withdraws X-D and **reaffirms DEC-046 (public repo)**.
- **Accepted consequence:** the real names already present in the `handoff/` catalogue files stay publicly visible. The employer knows that these values are real (DEC-060, 2026-11-11). `handoff/` stays untouched.
- **Still in force:**
  - R-38: no new document, test, fixture, image, log or message may repeat these values.
  - DEC-005 / DEC-028 / DEC-046: real Planning values, codes, serials and customer names never enter Git. They stay only in `F:/aleekhan/private-extract` (outside the repo) and in the server DB.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-12 — DEC-005 APPROVED (14-digit product code rule)
- **Evidence:** `docs/discovery/PLANNING_EXTRACTION_SUMMARY.md` (aggregates only). Real cases and cell addresses are only in the private report outside the repo.
- **Rule:** `02` (nature = product) + product-type code (2) + category code (2) + product number (4) + style number (4).
  - **New product number:** the largest number of the same product type + 1.
  - **Belt:** the product number is the buckle-type code (2) followed by the belt width (2).
  - **New style:** numbered sequentially from 0001 for each product within each category.
  - Codes are always 14-character strings.
- **Q-B:** **B1**. The system builds and reserves the code (`RESERVED / ERP_PENDING`). The item is created by hand in Rahkaran, and the code becomes `ERP_MATCHED` when the Rahkaran import shows it. Nothing is written to Rahkaran.
- **Q-C:** "family" means the **product type**. All 5 types have more than 20 real cases. Belt is tested on its own because of its special product-number rule.
- **Q-D:** the 634 legacy rows whose code is not 14 digits are imported as history and flagged `DISPUTED`. They are never corrected automatically, and planning decides each one.
- **Q-A (confirmer):** the employer approves the rule and the golden cases **himself**. This replaces the recommended planning + commercial maker-checker for the rule.
- **Technical note C-77:** the code preview in `Order form` and `NOrder!FY` look up the category code from different `Sorce` columns. Golden tests must assert that both give the same code.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-12 — DEC-057 APPROVED (PHASE_02 permission matrix, M-A)
- **Roles:** five new BUSINESS roles, `commercial_officer`, `commercial_manager`, `planning_officer`, `product_data_steward` and `code_rule_approver`, with the permission table of `DEC-057_PACKET.md` as written.
- **Fresh MFA:** required for 4 actions: `identity.product_code.issue`, `identity.code_rule.approve`, `commercial.order.confirm` and `commercial.change.decide`.
- **Order confirm:** `commercial.order.confirm` goes to **`planning_officer`**, and the serials are allocated in the same transaction (DEC-006 L-A). This answers DEC-006 Q6.
- **Customer scope:** all customers for all the roles above. There is no per-officer customer assignment; every read and change is audited.
- **Owner:** `owner_admin` may decide directly on code-rule approval, order confirm and change-request decisions (an extension of DEC-056). **Self-approval stays forbidden:** the owner never approves his own request.
- **Unchanged:**
  - `management_viewer` is read-only.
  - `employee` has no PHASE_02 access.
  - Technical roles get no business approvals (DEC-003).
- **Implementation:** matrix v2.0 is a seed migration in 02.2.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-12 — DEC-059 APPROVED (change after confirmation, cancel, hold)
- **Base rule:** a confirmed order is never edited directly.
  - Every change is a change request (CR).
  - Applying an approved CR creates a new order version and a new serial snapshot. Earlier versions are never modified.
- **Page 33 split (C-61):**
  - PHASE_02 covers commercial order changes: lines, serials and snapshots.
  - ECR/ECO belongs to PHASE_03 and PHASE_04.
  - Effects on material, WIP, capacity and cost come in PHASE_05 and later.
- **Change types:** quantity, due date, add line, cancel line, cancel whole order, hold and resume.
  - **After the order is released to planning:** only due date and hold/resume are allowed.
  - **Line cancel after release:** the employer also accepted it in the change-type answer. It is **blocked by C-A below** until PHASE_05, and the more specific cancel answer prevails.
- **Cancel (C-A):** a confirmed order or line may be cancelled only before release to planning.
  - After release, cancel is blocked until PHASE_05, where material and WIP disposition arrive.
  - The serial of a cancelled line becomes `CANCELLED` and its number is never reused.
- **Quantity increase:** the line keeps the same serial; only a new order version is created. No threshold exists. If the employer later wants one, he sets it; the system never guesses a number.
- **Hold:** a single `ON_HOLD` state. Resume returns the order to its previous state.
- **Approval:**
  - `commercial_manager` decides every CR and `planning_officer` applies it.
  - A **due-date change** also needs **planning approval**: a second approval by `planning_officer`, in addition to `commercial_manager`. This replaces the recommended "notify planning".
  - The owner may decide directly, but never on his own request (DEC-057).
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-12 — DEC-058 APPROVED (customer and order master data)
- **Brand:** B-A. Brand is a separate table under the customer (one customer, many brands). The brand on an order is optional.
- **Customer representative:** the employer chose to **record the name** (overriding the recommendation "do not record").
  - **Name only.** No phone, email or other contact details are stored (DEC-028 is still in force for contact data).
  - The field is classified as personal data (`PII`) and every read and change is audited.
  - It is visible only with `identity.customer.read`; `management_viewer` sees it masked.
  - It never appears in exports, logs, tests or fixtures; tests use synthetic names only.
- **Customer PO number:** there is no uniqueness constraint. A duplicate within the same customer gives a warning, and the user must acknowledge it.
- **External references:** Rahkaran project code, contract number, customer style code and customer serial. Each one has a system and a type, and none is ever used as our serial. `product_data_steward` may add new reference types.
- **Units:** shoe = pair (جفت). Bag, belt, pocket item (جیبی), accessory and set = piece (عدد); a set counts as one piece. The six product types come from the Planning `Sorce` sheet.
- **Order types:** the four Planning types: پیش تولید، سری تولید، نمونه‌سازی، تولید آزمایشی. The page 29 concept labels are not used.
- **Q7 (required grade on the order):** not asked. The packet default applies, so the grade is free text only, with no comparison, until DEC-019 (PHASE_08). The employer can change this.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-12 — DEC-057 amendment (owner read) and DEC-059 amendment (due-date approver, cancel from hold)
Raised by the 02.2 implementation and review (REV-0222); asked with AskUserQuestion; employer chose the recommended option each time.
- **DEC-057, owner read:** `owner_admin` gets every PHASE_02 `identity.*`/`commercial.*` **read** permission. This is the same fix v1.3 made for documents. The no-self-approval rule is unchanged.
- **DEC-059, due-date planning approval:**
  - The approval is given by `planning_officer`.
  - The approver must be a **different person** from the requester and from the commercial manager who decided the request. This is enforced in the DB and the engine.
  - A matrix permission for this approval is added (commercial.change_request.planning_approve, final name set in 02.3).
- **DEC-059, cancel from hold:** an order or line that is ON_HOLD may be **cancelled directly** when its stored previous state is before release. After release, cancel stays blocked (C-A).
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-13 — DEC-005 amendment: style number 0000
Found by the 02.3 golden run on the Planning baseline (aggregates only): 14 real 14-digit codes, all of product type code 02, have style segment 0000. Asked with AskUserQuestion; the employer chose the recommended option.
- **Legacy only:** existing codes with style 0000 are accepted as history at import, and may be registered or matched like any other legacy code.
- **Never issued:** the system never generates style 0000; new styles always start at 0001.
- **Golden tests:** these cases are marked legacy-only. They must parse exactly, and the build path must refuse them.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-14 — PHASE_02 engine rules (02.3 review REV-0232 + implementer open items)
Asked with AskUserQuestion, in Persian.
- **Number format (DEC-058 amendment):** the employer chose **with the year**: `SO-1405-000001`, and likewise `CU-` for customers and `CR-` for change requests.
  - The year is the Jalali year of creation, in Asia/Tehran time.
  - Numbering restarts at 1 every year.
  - Numbers are unique and race-safe; gaps are allowed.
  - This replaces the PROPOSED plain format of 02.3.
- **Held order (DEC-059 amendment):** recommended option. While ON_HOLD, only resume or cancel is allowed, and cancel only before release. Quantity, due-date and add-line changes are refused.
- **Style number collision (DEC-005 amendment, REV-0232):** recommended option.
  - If count + 1 is already used, the system takes the **first free number after it**.
  - It records an audit reason. A duplicate code is never created.
  - This replaces the STYLE_NO_COLLISION refusal.
- **Planning reject (DEC-059 amendment):** recommended option. Planning may approve **or reject** a due-date change.
  - A rejection needs a reason.
  - The change request is closed as REJECTED and the old due date stays.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-14 — DEC-005 / DEC-006 follow-ups (02.4 review REV-0241, open item allocateSerial)
Asked with AskUserQuestion, in Persian. The first question was unclear and was asked again with a synthetic example.
- **Legacy belt rows whose order "buckle type" differs from the product number (15 rows):** the **14-digit code is authoritative**. The rows are accepted at import without review, and the order's buckle-type column is kept only as a note.
  - Golden evidence for belts uses only rows where the order's buckle agrees with the code.
- **Belt width:** for a new belt product, the **user enters the two-digit width in the form** (for example 35 for 3.5 cm), and the system stores it. For legacy codes the width is read from the code (`product_no[2:4]`).
- **`allocateSerial`:** **removed** from the API. A serial is created only by order confirmation (DEC-006 L-A).
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-15 — DEC-027 APPROVED (P-A) and PHASE_02 approval follow-ups
Asked with AskUserQuestion, in Persian; the employer chose the recommended option each time.
- **DEC-027 = P-A, with the proposed structure:** pages 1 and 2 are built in PHASE_02 from the mobile design images, using PHASE_02 data only.
  - Page 1 is the serial summary.
  - Page 2 is the order tab.
  - Sections owned by later phases show «در دست ساخت — به داده واقعی متصل نیست» with no numbers.
  - The layout is confirmed in the 02.5 UAT.
- **Approval inbox:** PHASE_02 decisions also appear in the PHASE_01 approval inbox (کارتابل), linking to their page. These are order confirm, change-request decide, planning decision and code-rule approve.
- **`commercial.change.planning_approve` flags:** fresh MFA, business approval and maker-checker are confirmed. The approver must be neither the requester nor the deciding manager.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-15 — DEC-057 amendment (conflict queue access) and DEC-005 follow-up (imported catalogue status)
Raised by step 02.6. Asked with AskUserQuestion, in Persian; the employer chose the recommended option each time.
- **Conflict queue (Planning imports):** `product_data_steward` and the owner may read the conflict queue and resolve items. `management_viewer` sees counts and data freshness only. This is matrix v2.2.
- **Imported catalogue status:** product types and categories imported from the approved Planning baseline are created **ACTIVE**. Any later change comes only from a new import plus the conflict queue.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-15 — DEC-005 Q-D clarification and conflict-queue rules (02.6 review REV-0261/0263)
Asked with AskUserQuestion, in Persian; the employer chose the recommended option each time.
- **Who decides disputed legacy codes:** `product_data_steward` and the owner, through the conflict queue. This replaces the "planning decides" wording of DEC-005 Q-D. Planning takes part only if the owner gives a planner the steward role.
- **Granularity:** one decision per **distinct value**. There are 224 values in the Planning baseline, covering 634 order rows. The decision applies to every row carrying that value, and the item shows the row count.
- **Raiser cannot resolve:** confirmed. Whoever raised a conflict item cannot resolve it (maker-checker). System-raised import items are not affected.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-16 — DEC-005 Q-D follow-up: a decision on a disputed value carries over to later imports (02.7 review REV-0271)
Asked with AskUserQuestion, in Persian; the employer chose the recommended option.
- **Carry-over:** once the steward + owner have resolved a disputed legacy value, a later Planning file that carries the same value does **not** open a new conflict item. The earlier resolution is applied, and the import records that it reused it (item reference in its counts and audit).
- **Count note:** the 02.7 counting includes identical repeated rows, so the baseline is 224 values over 640 rows (634 above counted distinct rows).
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-17 — DEC-059 amendment: order change-request limits (Gate PHASE_02 item c-1, REV-0203)
Asked with AskUserQuestion, in Persian; the employer chose the recommended option (both rules).
- **One open request:** an order may have at most one change request in SUBMITTED or APPROVED at a time; a second submit is refused until the first is applied, rejected, withdrawn or expired.
- **Expiry:** a change request that stays SUBMITTED or APPROVED (not applied) for 30 days moves to EXPIRED, the same period as platform approval requests (DEC-032).
- **Status:** decided; not yet enforced in code (STATE_TRANSITIONS §5.5 still marks them PROPOSED). Implementation follows as a separate reviewed change.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-17 — DEC-032 amendment: requester name in the approval inbox (Gate PHASE_02 item c-2, REV-0254)
Asked with AskUserQuestion, in Persian; the employer chose the recommended option.
- **Display:** the approval inbox and page 33 show the requester's display name (internal user display name only, no other personal data) instead of only the short id.
- **Status:** decided; not yet implemented. Implementation follows as a separate reviewed change.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-17 — DEC-005 amendment: a dismissed disputed value is not raised again (Gate PHASE_02 item g)
Asked with AskUserQuestion, in Persian; the employer chose **against** the implementer's recommendation.
- **Rule:** a disputed legacy value that the steward + owner DISMISSED carries over to later Planning imports exactly like a RESOLVED one: no new conflict item; the import records that it reused the earlier decision.
- **Replaces:** the 02.8 interpretation "DISMISSED re-raises" (`test_dismissed_disputed_value_is_raised_again`). Not yet changed in code; follows as a separate reviewed change.
- **Also recorded at the Gate (acknowledgements, no rule change):** item d — rollback boundary accepted (after real orders/serials exist, rollback is restore-from-backup only); item e — keep the unused `identity.serial.allocate` permission row for possible future manual allocation.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-17 — DEC-061: ≥95% visual fidelity to the design-catalogue mockups (new employer requirement)
Given by the employer in chat, in Persian, after the orchestrator compared page 4 (mockup) with the built page and found the built page much simpler.
- **Acceptance rule:** a page is accepted only when the orchestrator's fidelity test shows ≥95% match with its mockup in `handoff/08_UI_AND_UX/DESIGN_CATALOG_52` (all four widths 1440/1180/768/390). Reaching it is the orchestrator's responsibility.
- **Mockup review first:** before each phase starts, the employer reviews and approves (or amends) that phase's mockup pages; the approved/amended mockup is the target.
- **Frame from the start:** the mockup's layout frame (KPI cards, full tables, icon side menu, sections in the same place) is built in the step itself; only final polish waits for the polish phase (narrows the earlier UI-polish-backlog approach).
- **PHASE_02:** pages 1, 2, 4, 29, 33 are brought to ≥95% before the PHASE_02 Gate.
- **Unchanged guardrail:** demo numbers in a mockup are never shown as real; an element whose data comes from a later phase sits in the same place with an honest "در دست ساخت" / empty state.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-18 — DEC-005 amendment: ACTIVE product required for style activation and code issue (REV-0293)
Asked in chat, in Persian (options A/B/C); the employer chose A (the recommended option).
- **Rule:** activating a style and issuing a product code are refused while the style's product is not ACTIVE. Removes the T-004 dead end (style active + code issued under a DRAFT product that the order wizard cannot list).
- **Status:** decided; implementation follows in 02.8 rework.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-18 — DEC-061 amendment: tablet target for pages 1/2 and extra sections
Asked with AskUserQuestion, in Persian; the employer chose both recommended options.
- **Tablet (768) for pages 1 and 2:** they have no tablet mockup (only a phone concept). At 768 their shell regions (side menu/menu button, top-bar search, user element) are measured against the catalogue's shared shell, the same targets as pages 29/33. The phone-concept scaling stays for the page body.
- **Extra sections:** a section the work needs but the mockup lacks (e.g. page 4 style detail, code issue, revisions) is allowed only below all mockup content, or in a separate tab/dialog. The fidelity test adds a penalty for any non-mockup section placed above or between mockup regions.
- **Decided by:** بسام ربیهاوی (کارفرما).

## 2026-11-19 — KPI display definitions (REV-0299)
Asked with AskUserQuestion, in Persian; the employer chose both recommended options.
- **Page 4 «سفارش‌های فعال»:** CONFIRMED, RELEASED_TO_PLAN, ON_HOLD, PARTIAL_FULFILLED — confirmed as implemented.
- **Page 33 «درخواست‌های باز»:** SUBMITTED + APPROVED-not-yet-applied only (same set as the DEC-059 one-open-request rule); DRAFT is not counted as open and is shown separately.
- **Decided by:** بسام ربیهاوی (کارفرما).
