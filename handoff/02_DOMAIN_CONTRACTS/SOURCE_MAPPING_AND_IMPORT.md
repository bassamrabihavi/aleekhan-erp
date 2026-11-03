# قرارداد Import و داده مرجع واقعی

## فایل‌های مرجع داخل بسته
- `Planning--.xlsm`: منبع قدیمی Planning، شامل NOrder، Sorce، Codding، PRD.Form، listGH؛ رمز آن در بسته/سورس ذخیره نمی‌شود. اجرای Macro ممنوع؛ برای تحلیل باید در محیط امن و فقط‌خواندنی بررسی شود.
- `WH-.xlsm`: منبع WH و Split DB/Forms؛ محتویات خام و فرمول‌ها بدون حذف حفظ شوند.
- `جدول پیگیری تیغه(1).xlsx`: آخرین نسخه پیگیری تیغه طبق کارفرما؛ Sheets/کد ۱۴رقمی/شرح، ردیف‌های تکراری و خطاها باید با ابزار Import بررسی شوند.
- `ListData (2).xlsx`: آخرین Snapshot انبار راهکاران طبق کارفرما؛ **موجودی تجمیعی** نه Lot-grade-reserved-location کامل.
- `جدول کلیشه.xlsx`: بانک کلیشه؛ تاریخچه Code/Brand/Dimension؛ کدهایی مثل DOR51 حروفی-عددی هستند.
- `AutoJ-BoM.py`: اسکریپت مرجع ناقص؛ از اجرا پرهیز و رفتار observable را جدا کنید.
- DXF نمونه و BOM نمونه: فقط Test Fixture خصوصی؛ هر الگوریتم جدید باید با مالک مهندسی مقایسه و تأیید گردد.

## ویژگی‌های الزامی Import
1. SourceFile(id, original_name, SHA256, size, import_actor, received_utc, source_type, encrypted?, parse_status, claimed_origin); binary original immutable.
2. ExcelSourceRecord(workbook, sheet_name, row_number, cell_ref, raw_value, cell_type, formula_text, cached_value, normalized_value, transform_rule_version, error_code)؛ این ستون‌ها باید موجب بازسازی شوند حتی اگر سطر در طرح نهایی استفاده نشود.
3. Staging جدول مجزا از داده رسمی؛ Dry Run، Preview Diff، Row Validation، Reject/Approve batch، Error Report، Resume، Dedup/Idempotency، Audit، Rollback-with-compensation.
4. Cell formula ≠ evaluated truth; stale cached values must not be silently used. Date/time Jalali/Excel serial, Persian numerals and Unicode normalized with original kept.
5. Product code `02 + ...` source formula includes `Sorce!O`, `NOrder!A/FY/C/D` as previously observed; mapping کامل همه دسته‌ها هنوز requires golden examples و VBA audit.
6. Item code/description match uses exact code first within **type namespace**, then similarity as suggestion only; never auto-merge semantically different texts or two code duplicates.
7. Warehouse official snapshot `Opening+Inbound-Outbound=Closing` verified in prior observation, but does not tell own reservations/lots. `effective_at`, `as_of`, `freshness`, `source_reliability` always shown. Do not advertise stale stock as real-time.
8. Tool follow-up `DXF → DieCandidate → tracking file` separate stage. Tracker handles code/description Rahkaran. Do not issue ERP tool code in DXF parser.

## Source uncertainty
آمارهای استخراج‌شده در ممیزی‌های قبلی Snapshot audit هستند نه Constraint قطعی DB. لازم است Codex با ابزار امن همان فایل‌های ضمیمه را دوباره شمارش و **گزارش آشتی** ثبت کند. برای یک تناقض، نتیجه را به‌عنوان اختلاف ارائه کند و هیچ‌یک را خودکار «اصلاح» نکند.
