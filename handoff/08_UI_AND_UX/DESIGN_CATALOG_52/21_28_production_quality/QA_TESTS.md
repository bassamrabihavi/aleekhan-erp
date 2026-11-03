# تست‌های QA / شرط ورود به پایلوت واقعی

## تست‌های مشترک

1. نقش بدون دسترسی با درخواست API مستقیم امکان ثبت تغییر نداشته باشد.
2. با دو کلیک پشت‌سرهم روی ثبت خروجی فقط یک Ledger Entry ساخته شود.
3. Update هم‌زمان یک سریال/بچ توسط دو کاربر Conflict معتبر بدهد.
4. تمام تغییرات با User/Role/Time/Reason/Version قابل Audit باشند.
5. فارسی/RTL و اعداد فارسی/لاتین در همه فیلترها قابل جستجو باشند.
6. بی‌برخورد بودن Layout در عرض ۳۹۰، ۸۲۰، ۱۳۶۶، ۱۶۰۰ بررسی شود.
7. جدول عریض در Mobile فقط داخل خودش اسکرول افقی داشته باشد.
8. Sidebar سمت راست باشد؛ Hover desktop و Drawer mobile باز و بسته شوند.

## آزمون‌های تخصصی

### صفحه 21: مدیریت برش و تحویل دسته‌های تولید
- تحویل از انبار باید Grade-compatible و با بسته فنی درست باشد
- تعداد ست کامل بیش از تعداد قطعه محدودکننده مجاز نیست
- تحویل به خط نیاز به تأیید تعداد طرف دریافت‌کننده دارد
- Empty, Error, Permission Denied, Offline و Stale Projection بررسی شوند.

### صفحه 22: مدیریت اجرای خطوط تولید
- تخصیص مجدد منابع نباید Double Booking ایجاد کند
- همزمان اثر روی ظرفیت خط‌دهنده و گیرنده دیده شود
- تغییر برنامه فقط از Workflow مجاز Planning اجرا شود
- Empty, Error, Permission Denied, Offline و Stale Projection بررسی شوند.

### صفحه 23: ترمینال اپراتور — ثبت سریع عملیات
- تعداد خروجی بیش از مانده عملیات نباشد
- تکرار ActionToken نباید دوباره روی Qty اثر بگذارد
- وقتی Offline است Conflict و Clock Drift باید قبل از Commit بررسی شود
- Empty, Error, Permission Denied, Offline و Stale Projection بررسی شوند.

### صفحه 24: تضمین کیفیت مواد و قرنطینه (QA)
- Lot دارای Hold از Available قابل تخصیص خارج شود
- گرید A ماده برای سفارش A+ خودکار مجاز نیست
- تغییر استاندارد اثر عطف‌به‌ماسبق روی سریال Release‌شده ندارد
- Empty, Error, Permission Denied, Offline و Stale Projection بررسی شوند.

### صفحه 25: کنترل کیفیت نهایی و درجه‌بندی (QC)
- بچ QC باید با QuantityLedger آشتی داده شود
- محصول Grade کمتر از Required بدون Concession ارسال نشود
- تمام موارد Rework برای تأیید مجدد به QC بازگردند
- Empty, Error, Permission Denied, Offline و Stale Projection بررسی شوند.

### صفحه 26: انبار محصول نهایی و تحویل از پروژه
- QC Release و شمارش فیزیکی مستقل بمانند
- هر دریافت قبل از Dispatch باید به Stock Ledger وارد شود
- Double Receipt به‌کمک Idempotency و External Doc Key ممنوع باشد
- Empty, Error, Permission Denied, Offline و Stale Projection بررسی شوند.

### صفحه 27: ارسال، حواله و تحویل مشتری
- حواله از بازرگانی و تحویل فروش از انبار تفکیک شوند
- موجودی QC Hold وارد برنامه ارسال قطعی نشود
- Partial Shipment باید مانده تعهد و مجموع ارسال را دقیق حفظ کند
- Empty, Error, Permission Denied, Offline و Stale Projection بررسی شوند.

### صفحه 28: داشبورد سرپرست خط و تحویل شیفت
- شاخص عملکرد نباید بر اساس شمار خام قطعه بین عملیات‌های متفاوت مقایسه شود
- هردو Target اولیه و اصلاح‌شده همراه Audit حفظ شوند
- حقوق افراد برای سرپرست قابل مشاهده نباشد
- Empty, Error, Permission Denied, Offline و Stale Projection بررسی شوند.


## نتایج تست‌های این نمونه

`render_results.json` با Playwright در حالت Headless ۳۲ Screenshot گرفت و برای آن اندازه‌ها خطای JS و Horizontal Overflow بدنه گزارش نشد. این **تست تصویری/نمایشی است** نه تست Backend یا Use Case عملیاتی. تسک‌های پایلوت، اصالت داده‌های ERP و تأیید مدیر QA هنوز بازند.
