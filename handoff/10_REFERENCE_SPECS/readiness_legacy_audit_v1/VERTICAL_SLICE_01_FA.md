# Vertical Slice 01 — نخستین مسیر قابل آزمون End-to-End

## دامنه
بازرگانی سفارش آزمایشی می‌سازد، برنامه‌ریزی برای یک Order Line محصول/Style/Serial را با کد ۱۴رقمی تأیید می‌کند، سیستم اسناد و Snapshot را ذخیره می‌کند، Event/Audit می‌نویسد، و کاربر دارای دسترسی در صفحه Serial 360 و Product/Style 360 آن را می‌بیند.

### موجودیت‌ها
Customer, CustomerBrand, CustomerOrderHeader, OrderLine, Product, Style, Serial, SerialSpec, OrderProgram, ExternalReference, QualityRequirement, ParameterDefinition, ParameterValue, Task, Approval, AuditEvent, OutboxEvent.

### تراکنش اصلی
1. Parse/Validate فرم + Master codes؛ `raw_value` حفظ شود.
2. Check Customer/Brand/Type/Category/Style uniqueness و Permission.
3. انتخاب Code Rules Revision؛ خروجی کد ۱۴رقمی به‌صورت Text با صفرهای ابتدایی.
4. در همان تراکنش تخصیص Serial اتمیک، Snapshot سفارش/Grade، تاریخچه و Outbox؛ در خطا همه Rollback.
5. `SerialCreated` روی Read Projection اعمال و برای Product/Style Search قابل مشاهده شود.
6. Issue/Retry با Idempotency Key دوباره Serial نسازد.
7. Post-handoff Editing فقط از طریق Change Request.

### باید در تست‌ها اثبات شود
- دو درخواست همزمان کد/Serial یکسان ندهند.
- یک Product Code اشتباه یا Style متعلق به Product دیگر رد شود.
- تغییر نام Material/Style جدید، Snapshot تاریخی را تغییر ندهد.
- داده Finglish/نیم‌فاصله پیشنهاد بدهد اما Code/Title conflict خودکار حل نشود.
- Code 14 chars with leading zero؛ مثال تاییدشده جیبی/جا کارتی: `02040400240007`.
- Browser روی 390/820/1366/1600 پیکسل و پرینت قابل استفاده باشد.
- مبنای OrderHeader چندخطی باشد؛ هر Line تولیدی یک Serial.

### خارج از این Slice
برنامه‌ریز خودکار پیشرفته، حقوق، ML، AI Action، برش CNC واقعی، رهگیری کامل تولید، Kill Job حساس.
