# قرارداد اولیه API — صفحات ۲۹ تا ۳۶

**هشدار:** این‌ها قراردادهای پیشنهادی برای بازبینی هستند، API اجرایی وجود ندارد. تمام Commandها AuthN/AuthZ، Idempotency Key، Domain Validation، Audit و خطای استاندارد فارسی لازم دارند.

## صفحه 29 — ثبت سفارش جدید و کدگذاری
- `POST /api/v1/commercial/order-drafts`
- `POST /api/v1/core/serials/allocate`
- `POST /api/v1/core/product-codes/preview`
- `GET /api/v1/core/styles/similar`

## صفحه 30 — برنامه سفارش فصل/ماه/هفته
- `GET /api/v1/planning/programs`
- `POST /api/v1/planning/programs/{id}/versions`
- `GET /api/v1/planning/aggregate-demand`
- `POST /api/v1/planning/forecast-consumption/preview`

## صفحه 31 — زمان‌بندی تفصیلی و صف عملیات
- `GET /api/v1/planning/operation-schedule`
- `POST /api/v1/planning/replanning/scenarios`
- `POST /api/v1/planning/scenarios/{id}/apply`

## صفحه 32 — سناریوساز ظرفیت و منابع
- `POST /api/v1/planning/capacity-scenarios/compute`
- `POST /api/v1/planning/capacity-scenarios`
- `POST /api/v1/planning/capacity-scenarios/{id}/approve`

## صفحه 33 — کنترل تغییرات سفارش و مهندسی
- `POST /api/v1/change/requests`
- `GET /api/v1/change/requests/{id}/impact`
- `POST /api/v1/change/requests/{id}/decision`

## صفحه 34 — بهای تمام‌شده و قیمت‌گذاری
- `POST /api/v1/costing/estimates`
- `POST /api/v1/costing/quotes`
- `POST /api/v1/costing/quotes/{id}/issue`

## صفحه 35 — گزارش و داشبورد مدیریتی
- `POST /api/v1/analytics/query`
- `GET /api/v1/analytics/metrics`
- `GET /api/v1/analytics/lineage/{metric}/{snapshot}`

## صفحه 36 — پایش سلامت و مدیریت پردازش
- `GET /api/v1/admin/jobs`
- `POST /api/v1/admin/jobs/{id}/request-cancel`
- `POST /api/v1/admin/jobs/{id}/request-force-cancel`
- `GET /api/v1/admin/health`

## اصول متقاطع
- هیچ PUT/POST حساس بدون بررسی نسخه رکورد و Permission معتبر نباشد.
- موتور کد راهکاران و تخصیص سریال باید در یک Transaction امن و با کنترل هم‌زمانی اجرا شوند.
- سناریوهای برنامه‌ریزی تا زمان تأیید نباید برنامه زنده را تغییر دهند.
- توقف Job: safe cancel/force cancel با Reason، Audit، Checkpoint و Recovery؛ Migration/Restore مستقیم قابل Kill نیست.
- 409 برای تعارض نسخه؛ 422 برای اعتبارسنجی؛ 403 برای عدم مجوز؛ پیام روشن فارسی و trace id.
