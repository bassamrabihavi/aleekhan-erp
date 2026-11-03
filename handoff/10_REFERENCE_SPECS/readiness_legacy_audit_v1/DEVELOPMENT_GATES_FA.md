# گیت‌های توسعه: از امروز تا پایلوت و استقرار

## گیت A — مجاز برای شروع فوری (Scaffold)
- [ ] انتخاب و ثبت ADR پشته فنی (پیشنهاد اولیه: React + TypeScript؛ Backend پایتون/FastAPI؛ PostgreSQL؛ Job worker جدا؛ قابل تغییر با تصمیم تیم).
- [ ] Monorepo یا ساختار مستند repository و lint/test/build CI.
- [ ] محیط Dev و Staging ایزوله، Secrets امن، بکاپ اولیه و Audit فعال.
- [ ] Design Tokens واقعی RTL، فونت خوانای فارسی، Sidebar راست Hover/Pin و Breakpointهای چهارگانه.
- [ ] Authentication + RBAC + scopes + field-level restrictions + incident logging.
- [ ] Core Product/Style/Customer/OrderHeader/OrderLine/Serial + Extension Metadata.
- [ ] Audit/Event/Outbox، Task و Rule Version اولیه.
**خروجی گیت A:** برنامه‌ای که بالا می‌آید، login دارد، مهاجرت DB اجرا می‌شود و تست CI دارد؛ *هنوز سامانه تولیدی نیست*.

## گیت B — اولین جریان واقعی ثبت سفارش و ردیابی
- [ ] Golden-master dataset کدگذاری براساس Planning برای تمام خانواده‌های محصول.
- [ ] پیاده‌سازی کد ۱۴رقمی به‌صورت String و تخصیص اتمیک شماره سریال.
- [ ] OrderHeader/OrderLine و Product/Style/Serial با جلوگیری از تکرار و حفظ Snapshot.
- [ ] Mapping فیلدهای NOrder و PRD.Form به Schema + Dynamic Parameters.
- [ ] نمونه PDF/Print برگه تولید با تطبیق هدر.
- [ ] صفحه ۲۹، ۱، ۲ و ۴ به Backend واقعی وصل شوند.
- [ ] یکپارچه‌سازی Import اولیه و Data Quality.
**خروجی گیت B:** ثبت واقعی سفارش آزمایشی و جستجو/ردیابی آن از روی محصول، استایل، سریال، مشتری.

## گیت C — فنی/مهندسی
- [ ] Revision و Document Registry، الگوی تایید، BOM و OPC و Release Package.
- [ ] Ruleهای سازگاری، Alias/Material Master، QA Grade gates.
- [ ] PRD.Form، listGH، Die Registry، Cliche؛ اسکن اتومات DXF بعد از دریافت اسکریپت مرجع.
**خروجی گیت C:** Release معتبر و قابل بازتولید برای سفارش آزمایشی.

## گیت D — اجرای مواد تا تحویل
- [ ] Import WH/Rahkaran staging→validation→reconcile.
- [ ] Reservation/GAP/lot/grade/custody/Quantity Ledger.
- [ ] Cutting/production terminal/QC/FG/Shipment و Offline Conflict Recovery.
- [ ] Performance KPI با تاریخچه استاندارد و Data Freshness.
**خروجی گیت D:** یک Serial واقعی در جریان آزمایشی از سفارش تا تحویل، با صفر اختلاف ناموجه در تعداد/موجودی.

## گیت E — پایلوت و سخت‌سازی
- [ ] سناریوهای فشار هم‌زمان، قطع شبکه، Restore، امنیت و تراکنش معکوس.
- [ ] ثبت باگ P0/P1/P2، مالک، راه‌حل و Retest.
- [ ] اجرای موازی با Excel/Rahkaran؛ اختلاف‌های ناموجه صفر.
- [ ] تأیید واحدهای بازرگانی، برنامه‌ریزی، مهندسی، انبار، تولید، QA/QC و IT.
- [ ] Go/No-Go و انتشار تدریجی.
**خروجی گیت E:** مجوز انتقال Source of Truth از فایل‌های عملیاتی به پلتفرم.

## اولویت
*گیت A می‌تواند همین حالا شروع شود.* گیت‌های B تا E به ترتیب و با همپوشانیِ مدیریت‌شده توسعه داده می‌شوند. از اعلام مدت‌زمان قطعی بدون شناخت تعداد توسعه‌دهندگان، محیط IT و کیفیت داده خودداری شود.
