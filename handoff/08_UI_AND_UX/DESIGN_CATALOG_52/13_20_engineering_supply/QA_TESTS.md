# چک‌لیست QA / Acceptance — صفحات ۱۳ تا ۲۰

## مشترک
- [ ] Sidebar در راست باز شود، Auto-hide با Hover و امکان Pin؛ موبایل Drawer از راست.
- [ ] چهار Breakpoint و نبود اسکرول افقی ناخواسته در Body؛ جدول ممکن است داخلی Scroll شود.
- [ ] متن‌ها فارسی و RTL صحیح؛ تمرکز صفحه‌کلید و Esc در Modal.
- [ ] Role/Field Permissions از سرور enforce شود.
- [ ] نمایش Loading/Empty/Error/Offline/Permission Denied برای هر صفحه.
- [ ] کلیک دوباره/Retry باعث Duplicate Write نشود؛ Idempotency.
- [ ] Change Audit، Revision، Snapshot و Correlation ID داشته باشد.
- [ ] داده‌های Sample با Production اشتباه گرفته نشوند.

## موارد خاص
- [ ] ۱۳: تغییر Pattern، مقرهای متاثر را برای بازبینی علامت‌گذاری کند؛ وضعیت موجودی از انبارک.
- [ ] ۱۴: چند ناحیه لیویس برای یک Piece/Revision با توالی مستقل؛ F11 = ۱٫۱ میلی‌متر؛ اثر تغییر جنس.
- [ ] ۱۵: نام مترادف و Finglish، نمایش Canonical و Raw؛ کد ≠ عنوان Conflict؛ پرت/واحد مستقل؛ BOM چندسطحی.
- [ ] ۱۶: DAG بدون Cycle؛ عملیات موازی؛ زمان انتظار بدون مصرف دقیقه نفر؛ چند منبع همزمان؛ خط توسط Planning.
- [ ] ۱۷: Package Manifest دقیق، immutability بعد Release؛ تغییر میانی با Effectivity.
- [ ] ۱۸: کنترل Availability/Grade/Owner/Quarantine/Expiry؛ رزرو همزمان؛ partial issue؛ ledger.
- [ ] ۱۹: ETA تغییرپذیر با History؛ اعلام تأمین GAP را نبندد؛ تأیید انبار و ERP Reconciliation.
- [ ] ۲۰: عدم Double Count سفارش قطعی و Forecast؛ Aggregation Grade-aware؛ پوشش BOM ناقص صریح؛ Snapshot.

## آزمون نمونه فرانت‌اند
- [ ] لینک‌های ۱۳ تا ۲۰ هر صفحه را باز می‌کنند.
- [ ] فیلتر متنی تعداد ردیف را کم می‌کند.
- [ ] افزودن ردیف نمایش جدول را تغییر می‌دهد (فقط محلی).
- [ ] Modal بدون دلیل برای Action حساس ثبت نمی‌شود.
- [ ] در ۳۹۰×۸۴۴ منو از سمت راست باز و بسته می‌شود.
- [ ] در ۱۴۴۰×۹۰۰ Sidebar باز و بسته و سنجاق می‌شود.
