# دستور آغاز پروژه برای Codex / Claude Code

به‌عنوان Tech Lead، با تکیه بر کاتالوگ ۵۲ صفحه‌ای عالیخان و این فایل‌های آمادگی، **فعلاً فقط گیت A و اسکلت گیت B** را پیاده‌سازی کن. پیش از تغییر کد، فایل‌های `README_FIRST_FA.md`, `AUDIT_FINDINGS_FA.md`, `DEVELOPMENT_GATES_FA.md`, `VERTICAL_SLICE_01_FA.md`, `DECISIONS_PENDING_FA.md`, `PAGE_READINESS_52.json` و کاتالوگ UI را بخوان.

قواعد حیاتی:
1. کاتالوگ UI پیش‌نویس است؛ هیچ یک از تصاویر به معنی منطق قطعی نیست. متن‌ها فارسی و RTL؛ سایدبار **فقط سمت راست** با Hover/Pin و Drawer موبایل.
2. پیاده‌سازی Modular Monolith و مالکیت Schema/Domain. Authentication، RBAC، Audit، Transactional Outbox، Rule Revision و Error Contract را در هسته بگذار.
3. Product→Style→Serial؛ Customer PO Header چند Line دارد، هر Order Line تولیدی یک Serial. Snapshot و External Reference ضروری‌اند.
4. کد راهکاران **۱۴ رقم متنی** با صفرهای پیشرو؛ الگوریتم برای انواع محصول از `Planning--.xlsm` و Golden Test استخراج شود، نه hardcode یا تخمین. کد تیغه مسیر مستقل و هنوز در انتظار Python مرجع است.
5. از داده‌های واقعی اکسل مستقیم به Core DB وارد نکن؛ import staging و mapping versioned بساز و raw data/hash نگه دار.
6. متریال به‌صورت ردیف نامحدود با waste/unit/color/print/finish مستقل، نه ستون‌های ثابت.
7. اگر قاعده، مالکیت یا فیلدی مبهم بود، آن را با issue و blocking gate ثبت کن؛ Silent guess ممنوع.
8. تمام APIها Permission را در Backend بررسی کنند. برای درخواست‌های تکراری Idempotency و Concurrency کنترل شود.
9. Test suite از ابتدا: migration smoke, API validation, RBAC, concurrency, rollback, audit/event integrity, fa-IR/RLT responsive.
10. هر اجرای پایان گیت، گزارش `Implemented/Tests/Unresolved Risks/Required Approval` تولید کند. هیچ Mock را به‌عنوان قابلیت واقعی معرفی نکن.

گام اول: ساخت اسکلت پروژه، پشته پیشنهادی و ADR، ساخت migrations حداقلی Core و Runbook راه‌اندازی محیط Dev. سپس آزمون‌های واقعی ثبت سفارش را با نمونه‌های Golden Master شروع کن.
