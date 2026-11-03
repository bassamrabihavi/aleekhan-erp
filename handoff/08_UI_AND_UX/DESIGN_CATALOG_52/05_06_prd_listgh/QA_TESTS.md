# سناریوهای اجباری پذیرش — فاز پایلوت واقعی

1. محصول کیف، کد و استایل و سریال واقعی را وارد کن، هدر PRD مطابق Excel/ERP تأیید شود؛ leading zeros حفظ شوند.
2. سریال با **۵ خرجکار و ۲ آستر** ثبت شود؛ ترتیب، چاپ، فینیش، رنگ، واحد و پرت هر سطر مستقل بماند؛ در Preview و Print هم جدا دیده شود.
3. سریال با **۰ خرجکار، ۱۰ خرجکار، ۱۲ آستر، ۳ ماده با نقش یکسان** ثبت شود؛ هیچ Hard Limit یا Overwrite رخ ندهد.
4. ثبت ۲ لاین از یک کد ماده با Usage متفاوت مجاز باشد، ولی یک کد با دو **نام هویت متعارض** در Gate رد شود.
5. `سرزیپ ۵` با `آویز زیپ` فقط با تأیید Master Data Steward ارتباط Alias/Usage بگیرد؛ `نیمهلحقه ۹ میل` به صورت پیشنهاد `نیم‌حلقه ۹ میلی‌متر` نمایش یابد.
6. Material Grade B برای سفارش A+ نباید Eligible باشد مگر Deviation Permit مصوب و Scope محدود.
7. تغییر پرت/واحد/متریال بعد از Release فقط با Revision/Impact Analysis.
8. لیست `listGH` با قطعات ۱ تا N، Bundle/Die/Print/Crop و Qty چاپ شود؛ ستون‌های منبع حذف نشوند.
9. برای ۱۴رقمی کد محصول و تیغه: فرمت/Unique/مثال‌های واقعی/تطبیق کد و شرح در راهکاران تست شود؛ ثبت همزمان نباید کد تکراری بسازد.
10. WH Import (همه ستون‌های کاتالوگ و Split DB) Count/Quantity/Discrepancy/Unmapped Control Total داشته باشد؛ Import دوباره Idempotent.
11. نمایش/چاپ با Widthهای 1920/1440/1366/1024/820/390 و دستگاه لمس؛ Sidebar سمت راست، Hover فقط desktop، Drawer mobile.
12. دو کاربر همزمان در برگه واحد؛ optimistic locking و Conflict Diff، نه overwrite.
13. Offline terminal و Retry پس از Crash؛ ورود/خروج/مصرف دوباره ثبت نشود.
14. Kill شدن Import/Print/Projection از Admin و Recovery: هیچ Half Commit، Checkpoint و DLQ قابل مشاهده.
15. نسخه چاپی برگه تولید و listGH با Excel مبنا از نظر Header / Position / Pagination در جلسه تایید پیکسل‌به‌پیکسل مقایسه شود.
16. نمونه خرید/قیمت/انبار: محاسبه مصرف ورودی از BOM با پرت استاندارد مخصوص هر ماده و UOMهای تایید شده؛ مستقل از تعداد/نقش نمونه.

**خروج از پایلوت:** P0/P1 باز صفر؛ اختلاف حل‌نشده در کد/مقدار/Grade/WIP/موجودی صفر؛ Sign-off بازرگانی، برنامه‌ریزی، مهندسی، انبار، QA/QC و ERP.
