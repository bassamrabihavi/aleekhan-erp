# دستور مرحله‌ای به Codex / Claude Code

در ماژول Engineering/Dies، فایل `AutoJ-BoM.py` را فقط به‌عنوان **منبع تاریخی خواندنی** مطالعه کن؛ بخش‌های فهرست‌شده در LEGACY_DIE_EXCERPTS.txt پایه تشخیص گروه‌های ACI=1 و Bounding Box هستند. از BOM generator و خروجی تخریبی Excel استفاده نکن. **این فایل Blade List کامل ندارد؛ کد یا الگوریتم ۱۴رقمی ساخت تیغه را اختراع نکن.**

۱. ابتدا تشخیص کاندیدا را با fixtures مستقل و Test-First در یک ماژول جدا پیاده‌سازی کن؛ نام آن `DieCandidateExtractor` باشد، نه `DieIssuer`.
۲. قراردادهای `TARGET_CONTRACT_FA.md`، امنیت DXF و Data Lineage را رعایت کن.
۳. صفحه‌های ۷/۸/۹ را به API و مراجعات Revision/Approval متصل کن؛ خروجی اولیه «پیش‌نویس» است.
۴. هر Batch استخراج شامل Hash، زمان، warnings و audit باشد.
۵. ماژول صادرکننده کد راهکاران و واردکردن در بانک رسمی را تا دریافت الگوریتم تأییدشده در حالت Disabled/Blocked نگه دار.
۶. برای هر گام PR کوچک، Migration مستقل، Unit Test، Integration Test، Screenshot UI، Security Findings و توضیح تغییرات ارائه کن؛ بدون تأیید ممیز وارد گیت بعد نشو.
۷. اگر DXF واقعی از نسخه مرجع و نتیجه واقعی Excel در دسترس نیست، در گزارش BLOCKED ذکر کن؛ از داده ساختگی برای ادعای برابری ۱۰۰٪ استفاده نکن.

خروجی گزارش هر PR: فایل‌های تغییرکرده، ورودی/خروجی آزمایش، تعداد کاندیدا نه تعداد تیغه، Test Pass/Fail، امنیت، تصمیم‌های باز، نحوه Rollback و میزان پوشش مرجع.
