# آزمون‌های لازم برای تحویل به پایلوت

## امنیت و داده
- RBAC و Field-Level: حقوق و Margin برای نقش‌های غیرمجاز حتی از API حذف شوند.
- کاربران هم‌زمان نتوانند Serial، Rahkaran Code، Reservation یا Qty را دوبار ثبت کنند.
- انقضا/لغو مجوز، تغییر Revision، Split Batch و Quantity Ledger با History درست باقی بمانند.
- هر Import نسخه خام، Hash، Source Row، Validation، Reject و Reconciliation داشته باشد.
- ناشناخته/کد مبهم با خام نگهداری شود؛ اجباری به Master نامعتبر Map نشود.

## سفارش و کدگذاری
- Golden test برای ۱۴رقم و صفر ابتدایی؛ Product/Style category-dependent.
- Snapshot واقعی رنگ/متریال، Grade و برنامه فصلی/هفتگی از Master فعلی جدا بماند.
- Forecast firm consumption باعث double count نشود.

## مهندسی و مواد
- هر Release فقط از BOM/OPC/Pattern سازگار و Approved ساخته شود.
- هر ماده متریال نقش/واحد/پرت مستقل داشته باشد، تعداد آستر/خرجکار نامحدود.
- آزمون Material Code 2288: عنوان متعارض از روی حدس merge نشود.
- Lot Grade A برای Serial A+ بدون Deviation اجازه Issue ندهد.

## تولید و کیفیت
- جمع WIP/FG/Scrap/Rework/Shipment با Quantity Ledger سازگار بماند.
- دوباره ارسال Offline Action دوبار خروجی ثبت نکند.
- مراحل موازی، Batch Split، Transfer Difference و QA Hold دیده شوند.
- QC Grade واقعی و Required Grade دو مفهوم جدا باشند.

## ادمین و قابلیت اطمینان
- Safe Stop/Force Kill با دلیل، Permission، Checkpoint و Recovery؛ DB خراب نشود.
- Restore موفق روی محیط تست، بدون تهدید داده واقعی.
- Console خطا و هشدار کاملاً فارسی قابل فهم باشد.

## خروج از پایلوت
- P0 باز: صفر.
- اختلاف ناموجه Serial/Code/Qty/Stock/Quality Grade: صفر.
- امضای تأیید صاحبان فرآیند و مسئول IT؛ گزارش موارد P1/P2 و برنامه اصلاح ثبت شود.
