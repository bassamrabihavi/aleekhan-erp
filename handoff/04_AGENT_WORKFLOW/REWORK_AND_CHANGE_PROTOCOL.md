# پروتکل رفع اشکال و Change Control

1. هر Issue با شناسه `REV-XXXX`, severity P0/P1/P2/P3, phase/step, owner, reproduction، expected، actual، source artifact، و rollback ثبت شود.
2. Codex/Claude Code همان Issue را در Branch اصلاح کند؛ Test بازتولید و Test برگشت اضافه کند؛ اگر schema/API تغییر لازم دارد Migration+ADR و impact بر فازهای قبلی گزارش کند.
3. ممیز دوباره روی commit جدید بررسی کند. فقط نتیجه `PASS` مسئله را می‌بندد؛ «خودم بررسی کردم» کافی نیست.
4. Scope Creep: ویژگی خارج فاز با CR و برآورد اثر، اولویت و موافقت کارفرما. بدون تایید از backlog فعلی جدا نگهداری شود.
5. تصمیم‌های کسب‌وکار (Grade, Code, Rate, QC override, Safety) فقط توسط مالک آن دامنه تصویب می‌شوند.
6. در یک مخزن واحد Commitهایی با Phase/Step مشخص انجام شود. هر فاز Release Candidate و tag `phase-XX-rcN`, و Gate Accepted tag `phase-XX-accepted` داشته باشد. هیچ ZIP جدیدِ ناسازگار جایگزین مخزن واحد نشود.
