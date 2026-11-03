# Aleekhan Master Handoff v1.0 — 2026-11-01

## محتوای این انتشار
- بسته واحد از UI اولیه ۵۲ صفحه، 15 فاز / ۱۲۰ گام، دستور مستقل Codex/Claude Code، گزارش، Gate، QA، ممیزی، Security و Source Registry.
- دامنه‌های اصلی Commercial, Identity, Engineering, BOM/OPC/Time, Planning, Warehouse, Supply, Production, QA/QC, FG/Dispatch, HR/Cost, AI/Admin.
- داده‌های واقعی به‌صورت «مرجع خصوصی» همراه Hash و بدون تغییر، از جمله جدیدترین Tracking Die و Inventory.
- تصحیح گردش تیغه براساس توضیح کارفرما: DXF extractor → tracker → دریافت کد و شرح راهکاران در tracker؛ Legacy Python در دسترس در مسیر Blade List ناقص است.
- موتور زمان/ظرفیت برای چهار خانواده در reference specs؛ مقادیر واقعی/زمان استاندارد تا UAT مصوب نشده‌اند.

## چه چیزی انجام نشده؟
- هیچ Backend, Frontend, DB یا Motor جدیدِ محصول در این انتشار کدنویسی نشده.
- امنیت و UI/DB محصول عملیاتی آزمون نشده‌اند؛ فقط **انسجام بسته و هش‌ها** بررسی شده.
- تصمیم‌های Critical باید توسط مالکان در Gateهای هر فاز تصویب شوند.
- نقشه API و داده منطقی است؛ DTO و DDL فیزیکی را اجرای Phase-0 به‌صورت نسخه‌دار ارائه می‌دهد.

## نحوه پذیرش
این بسته به‌عنوان «قرارداد شروع توسعه فاز صفر» تحویل داده می‌شود؛ نه ادعای آمادگی Go-Live.
