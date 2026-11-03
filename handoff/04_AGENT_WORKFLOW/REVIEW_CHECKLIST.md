# فرم ممیزی ChatGPT/مالک کارخانه — برای هر فاز یا گام

**ورودی ممیز:** diff/commit، گزارش مطابق Template، اسناد نسخه‌دار، نتیجه تست و Screenshot، خروجی خطا، Repro. ممیز بدون دیدن artifact نباید PASS بدهد.

| کد | کنترل | معیار |
|---|---|---|
| R01 | محدوده | دقیقاً دامنه فاز مصوب؛ No unauthorized extras |
| R02 | مرجع حقیقت | source registry, user-confirmed process, no undocumented assumptions |
| R03 | دیتابیس | PK/FK/unique/check/index, migration up/down, rollback, concurrency |
| R04 | تراکنش/دفتر | serial/stock/WIP/approval atomic, no duplicate, outbox and audit |
| R05 | موتور | الگوریتم و Golden Tests، unresolved decisions block publish |
| R06 | API | OpenAPI diff, idempotency, permission per action/record/field |
| R07 | UI | RTL, responsive, role-sensitive, error/empty/loading/stale states, accessibility |
| R08 | امنیت | SAST/SCA/secrets, Auth/MFA, IDOR/BOLA, logs/privacy, source quarantine |
| R09 | مالکیت ماژول | هیچ Write مستقیم به جدول Owner دیگر و تفکیک مسئولیت |
| R10 | Integration | raw+formula+hash preserved; staging/preview/reconcile/rollback; stale flag |
| R11 | کارایی/عملیات | SLA provisional, queue safe stop, backup restore, no data loss |
| R12 | تست/شواهد | CI tests reproducible, E2E real backend, no mocked evidence |
| R13 | مستندات/تغییرات | domain/API/ERD/readme/dependency/ADR updated |
| R14 | Owner Acceptance | تأیید واحد و کارفرما ثبت شده باشد |

### خروجی ممیزی
- **PASS:** همه بندهای لازم مدارک کافی دارند؛ تصمیم باز P0 در دامنه نداریم؛ Gate با تأیید کارفرما باز می‌شود.
- **REWORK:** شناسه عیب با شدت، فایل/خط و repro، انتظار اصلاح و تست برگشتی؛ همان گام دوباره بازبینی می‌شود.
- **BLOCKED:** داده حقیقی یا تصمیم حیاتی نامعلوم، خطر امنیتی/صحت داده یا فقدان مدرک؛ بدون کدنویسی بیشتر در بخش حساس.

نمونه پیام ممیز: `PHASE_06 / step 06.3 — REWORK: R04-002 — با دو رزرو هم‌زمان برای Lot X جمع رزرو > موجودی؛ reproduce command ...؛ معیار: transaction+locking و تست concurrency=pass.`
