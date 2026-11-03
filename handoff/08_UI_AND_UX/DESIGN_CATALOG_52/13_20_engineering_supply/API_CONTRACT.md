# قرارداد اولیه API — صفحات ۱۳ تا ۲۰

همه endpointها پیشنهادی‌اند؛ پیش از اجرای Backend باید نسخه و مجوزهای آن‌ها تأیید شود.

## الگوی مشترک
- Session RBAC + scope + field permissions در Backend؛ نه فقط مخفی‌کردن دکمه‌ها.
- GET بدون side effect؛ POST/PUT با `Idempotency-Key` و `If-Match` برای Revision.
- تاریخ DB به UTC، نمایش تقویم شمسی. UUID داخلی از کد کسب‌وکار جداست.
- خطای استاندارد: `{code, message_fa, entity, correlation_id, fields, recoverable}`.

## مسیرها
- **13 مدیریت مقر و جیگ**: GET `/engineering/jigs` / GET `/engineering/jigs/:id` / POST `/engineering/jigs/draft` / POST `/engineering/jigs/validate` — مالک: مهندسی و طراحی
- **14 نقشه و عملیات لیویس**: GET `/engineering/skiving` / GET `/engineering/skiving/:id` / POST `/engineering/skiving/draft` / POST `/engineering/skiving/validate` — مالک: مهندسی و طراحی
- **15 ویرایشگر BOM و کنترل معنایی**: GET `/engineering/boms` / GET `/engineering/boms/:id` / POST `/engineering/boms/draft` / POST `/engineering/boms/validate` — مالک: مهندسی و طراحی
- **16 مسیر عملیات و OPC**: GET `/engineering/opc` / GET `/engineering/opc/:id` / POST `/engineering/opc/draft` / POST `/engineering/opc/validate` — مالک: مهندسی و طراحی
- **17 بسته فنی و آزادسازی مهندسی**: GET `/engineering/releases` / GET `/engineering/releases/:id` / POST `/engineering/releases/draft` / POST `/engineering/releases/validate` — مالک: مهندسی و طراحی
- **18 جداسازی و رزرو مواد**: GET `/warehouse/separation` / GET `/warehouse/separation/:id` / POST `/warehouse/separation/draft` / POST `/warehouse/separation/validate` — مالک: انبار و مواد
- **19 کسری‌ها و پرونده GAP**: GET `/warehouse/gaps` / GET `/warehouse/gaps/:id` / POST `/warehouse/gaps/draft` / POST `/warehouse/gaps/validate` — مالک: انبار و مواد
- **20 نیازسنجی و تأمین تجمیعی**: GET `/supply/requirements` / GET `/supply/requirements/:id` / POST `/supply/requirements/draft` / POST `/supply/requirements/validate` — مالک: تأمین

## نمونه خطاهای لازم
- `BOM_MATERIAL_CODE_NAME_CONFLICT`: «کد ماده با عنوان استاندارد آن مطابقت ندارد.»
- `OPC_DEPENDENCY_CYCLE`: «وابستگی عملیات به صورت حلقوی تعریف شده است.»
- `ENGINEERING_PACKAGE_INCOMPATIBLE`: «نسخه‌های موجود در بسته فنی با یکدیگر سازگار نیستند.»
- `LOT_GRADE_INELIGIBLE`: «گرید این Lot برای سفارش قابل استفاده نیست.»
- `INSUFFICIENT_AVAILABLE_STOCK`: «موجودی آزاد برای رزرو این مقدار کافی نیست.»
- `GAP_UNCONFIRMED_RECEIPT`: «بدون تأیید دریافت واقعی انبار امکان بستن کسری وجود ندارد.»
- `FORECAST_ALREADY_CONSUMED`: «بخشی از تقاضای پیش‌بینی‌شده قبلاً توسط سفارش قطعی مصرف شده است.»
