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
