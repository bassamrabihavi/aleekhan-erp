# فاز تحویل به Codex / Claude Code و پایلوت واقعی

## خروجی موردنیاز قبل از Coding Handoff
1. فهرست قطعی صفحات + ماژول مالک + لینک ناوبری + نقش‌های مجاز.
2. Design System: tokenهای سایز/رنگ/فاصله، Sidebar RTL، ساختار Responsive و حالت‌های خطا.
3. Data Dictionary نهایی با Source Mapping واقعی Planning/WH/Rahkaran و قواعد کدگذاری قطعی.
4. ERD، Migrationهای نسخه‌دار، unique/FK constraints، الگوریتم concurrency، check-pointهای Transaction.
5. OpenAPI/DTO، Event schema، Permission matrix، Rule version و Audit.
6. Test Pack: Unit/Contract/Integration/E2E/Security/Load/Restore/Offline/UX.
7. خروجی‌های Sample و Golden Master از Excel اصلی برای تطبیق مقادیر.
8. دستور Build/Run/Test، Seed demo، نصب، Backup و Rollback.

## پایلوت واقعی پس از کدنویسی
- فاز ۱ Shadow Read-only: ثبت مقایسه Planning/WH/Rahkaran بدون تغییر عملیات رسمی.
- فاز ۲ محدودشده: انتخاب سریال واقعی و یک مسیر تولیدی، تأیید روزانه برنامه‌ریزی/انبار/کیفیت.
- فاز ۳ چندواحدی: سفارش→انبار→برش→تولید→QC→محصول→ارسال با Reconciliation کامل.
- فاز ۴ اصلاحات: باگ با severity، Owner، رخداد واقعی، Root Cause، Fix و Regression.
- Gate Go-Live: شمارش‌ها/موجودی/اسناد سازگار، صفر باگ بحرانی باز، بازیابی و Backup آزموده، کاربران آموزش‌دیده.

**از پایان طراحی تصویری ۵۲ صفحه، توسعه خودکار موفق یا پایلوت قبول‌شده نتیجه نمی‌شود.** تا زمان تأیید قراردادها، این فایل‌ها «پیش‌نویس مشخصات» هستند.
