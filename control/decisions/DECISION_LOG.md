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
