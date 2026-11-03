# یافته‌های ممیزی انسجام قبل از توسعه

## یافته‌های تأییدشده از کاتالوگ
1. **[P0 برای تحویل خودکار]** تمام ۵۲ صفحه DRAFT و `approved=false` هستند؛ بنابراین نباید به دستیار برنامه‌نویسی گفت UI نهایی است.
2. **[P1]** در Manifest صفحات ۱ و ۲ `prototype_path=null` دارند؛ طراحی آن‌ها در تصاویر گفت‌وگو وجود دارد ولی در ZIP نمونه HTML مستقل ندارند.
3. **[P0 برای تحویل نهایی]** قراردادهای API و مدل داده در بسته‌های جدا نوشته شده‌اند؛ یک OpenAPI نهایی، Schema migration واحد، Permission Matrix اجرایی، Event Catalog نهایی و یک Test Suite یکپارچه موجود نیست.
4. **[P0 برای اتصال واقعی]** تمام رابط‌ها نمونه نمایشی‌اند؛ اجرای واقعی Transaction، Integration راهکاران، عملیات Offline و سازگاری Report/DB هنوز اثبات نشده است.
5. **[P1]** تصاویر Responsive و نمونه‌های مرورگری جایگزین آزمون‌های Multi-user، امنیت، Recoverability و داده واقعی نیستند.

## وابستگی‌های فنیِ معلوم از فایل‌ها و معماری
6. **[P0 حوزه کدگذاری]** فرمول `NOrder!FZ2 = "02" & INDEX(Sorce!O:O, MATCH(A2,Sorce!E:E,0)) & FY2 & C2 & D2` کد ۱۴رقمی برای نمونه‌های شناخته‌شده می‌سازد؛ اما شاخه‌های VBA، کمربند/کفش/ست و مقایسه با نمونه‌های تاریخی به golden test نیاز دارند. تخصیص Serial با MAX()+1 نباید عیناً به چندکاربره منتقل شود.
7. **[P0 حوزه تیغه]** کد ۱۴رقمی تیغه هویت و منطق مستقلی دارد؛ فایل Python اصلی اسکن روزانه DXF که کاربر گفته بعداً می‌فرستد هنوز برای تطبیق این بخش دریافت نشده است.
8. **[P0 حوزه مواد]** باید WH و Planning را با آدرس سلول/هدر/فرمول/مقدار خام در Import Registry Map کنیم؛ نادیده‌گرفتن حتی فیلد ناشناخته ممنوع است.
9. **[P0 حوزه موجودی]** راهکاران مرجع رسمی اسناد/موجودی است؛ Platform مالک Reservation/GAP/QA است. اتصال Excel-only مستلزم timestamp، reconciliation، idempotency، و قطعیتِ منبع هر مقدار است.
10. **[P1 حوزه متریال]** متریال‌ها به‌صورت ردیف‌های نامحدود با Role، Unit، Waste Rule، Color، Print، Finish و Revision ذخیره می‌شوند؛ نه ستون ثابت `آستر۱` تا `آستر۵`.
11. **[P1 حوزه کیفیت]** `Customer Quality Requirement A+/A/B/C` و `Actual Product Grade` دو مفهوم جدا هستند؛ QA Lot eligibility و QC Customer Standard Revision را اعمال می‌کنند.
12. **[P1 حوزه داده]** Alias/Finglish فقط پیشنهاد معنایی می‌دهد؛ Code/Name conflict حساس مانند «سرزیپ ۵» و «آویز زیپ» بدون تأیید اصلاح یا Merge نمی‌شود.

## اصول اجرایی پیشنهادی قبل از برنامه‌نویسی
- Backend Modular Monolith با مالکیت صریح هر Domain؛ هیچ Module مستقیماً جدول Owner دیگر را ویرایش نمی‌کند.
- داده مالی/حقوقی فقط با Permission و Field-level filtering؛ حتی Admin فنی به‌تنهایی صاحب تأیید تجاری نیست.
- Event + Audit + Transactional Outbox؛ یک `Current Stage` ساده جایگزین Quantity Ledger و WIP Distribution نمی‌شود.
- هر ماژول باید با تست E2E واقعی و داده نمایشیِ برچسب‌دار تحویل شود.
- تمام تصمیم‌های باز در `DECISIONS_PENDING_FA.md` ثبت شوند و به‌عنوان TODO غیراجرایی در کد پنهان نشوند.
