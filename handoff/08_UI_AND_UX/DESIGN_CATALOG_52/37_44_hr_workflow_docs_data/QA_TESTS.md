# برنامه تست و معیار پذیرش صفحات ۳۷–۴۴

## صفحه 37: عملکرد کارکنان و خطوط
- [ ] **Invariant:** زمان خارج از کنترل بدون تایید دلیل از مخرج KPI کسر نشود
- [ ] **Invariant:** هدف اولیه هرگز بازنویسی نشود
- [ ] **Invariant:** حقوق و نرخ شخصی در پاسخ سرپرست نمایش داده نشود
- [ ] دسکتاپ ۱۶۰۰، لپ‌تاپ ۱۳۶۶، تبلت ۸۲۰، موبایل ۳۹۰؛ سایدبار سمت راست و بدون اسکرول افقی بدنه.
- [ ] Permission/Scope در Backend آزمون شود، نه فقط پنهان‌کردن دکمه.
- [ ] در خطای API حالت Error و پیام فارسی، امکان Retry امن و نمایش Data Freshness برقرار باشد.
- [ ] Duplicate submit / lost network / outdated row_version / audit پوشش داده شود.

## صفحه 38: مهارت‌ها، آموزش و درخواست تغییر حقوق
- [ ] **Invariant:** مسیر تأیید حقوق حداقل از ارزیابی عملکرد و HR و مدیریت عبور کند
- [ ] **Invariant:** درخواست‌دهنده نمی‌تواند همان درخواست را تأیید کند
- [ ] **Invariant:** AI حق تغییر خودکار حقوق ندارد
- [ ] **Invariant:** حقوق برای کاربر فاقد مجوز از Response حذف شود
- [ ] دسکتاپ ۱۶۰۰، لپ‌تاپ ۱۳۶۶، تبلت ۸۲۰، موبایل ۳۹۰؛ سایدبار سمت راست و بدون اسکرول افقی بدنه.
- [ ] Permission/Scope در Backend آزمون شود، نه فقط پنهان‌کردن دکمه.
- [ ] در خطای API حالت Error و پیام فارسی، امکان Retry امن و نمایش Data Freshness برقرار باشد.
- [ ] Duplicate submit / lost network / outdated row_version / audit پوشش داده شود.

## صفحه 39: صندوق کارها و تأییدهای سازمانی
- [ ] **Invariant:** Completed با Closed یکی نیست
- [ ] **Invariant:** ارجاع بین واحدها ثبت دلیل و کنترل Scope داشته باشد
- [ ] **Invariant:** SLA Pause تنها بر اساس Rule با منبع مانع انجام شود
- [ ] دسکتاپ ۱۶۰۰، لپ‌تاپ ۱۳۶۶، تبلت ۸۲۰، موبایل ۳۹۰؛ سایدبار سمت راست و بدون اسکرول افقی بدنه.
- [ ] Permission/Scope در Backend آزمون شود، نه فقط پنهان‌کردن دکمه.
- [ ] در خطای API حالت Error و پیام فارسی، امکان Retry امن و نمایش Data Freshness برقرار باشد.
- [ ] Duplicate submit / lost network / outdated row_version / audit پوشش داده شود.

## صفحه 40: مدیریت اسناد فنی و نسخه‌ها
- [ ] **Invariant:** Approved Immutable
- [ ] **Invariant:** عدم انتخاب Latest از روی ModifiedDate
- [ ] **Invariant:** مسیر UNC نگهداری شود
- [ ] **Invariant:** جداکردن اسناد Master از Snapshot سریال
- [ ] دسکتاپ ۱۶۰۰، لپ‌تاپ ۱۳۶۶، تبلت ۸۲۰، موبایل ۳۹۰؛ سایدبار سمت راست و بدون اسکرول افقی بدنه.
- [ ] Permission/Scope در Backend آزمون شود، نه فقط پنهان‌کردن دکمه.
- [ ] در خطای API حالت Error و پیام فارسی، امکان Retry امن و نمایش Data Freshness برقرار باشد.
- [ ] Duplicate submit / lost network / outdated row_version / audit پوشش داده شود.

## صفحه 41: مرکز استانداردسازی و کیفیت داده
- [ ] **Invariant:** Code↔Canonical conflict Block BOM release
- [ ] **Invariant:** Finglish semantic mapping بدون تایید حساس مجاز نیست
- [ ] **Invariant:** RawValue همیشه حفظ شود
- [ ] **Invariant:** درخواست ادغام دارای DoNotMerge ممنوع است
- [ ] دسکتاپ ۱۶۰۰، لپ‌تاپ ۱۳۶۶، تبلت ۸۲۰، موبایل ۳۹۰؛ سایدبار سمت راست و بدون اسکرول افقی بدنه.
- [ ] Permission/Scope در Backend آزمون شود، نه فقط پنهان‌کردن دکمه.
- [ ] در خطای API حالت Error و پیام فارسی، امکان Retry امن و نمایش Data Freshness برقرار باشد.
- [ ] Duplicate submit / lost network / outdated row_version / audit پوشش داده شود.

## صفحه 42: مدیریت پارامترها و چیدمان صفحات
- [ ] **Invariant:** کلید فنی پس از ساخت تغییر نکند
- [ ] **Invariant:** چرخش فرمول و وابستگی حلقوی رد شود
- [ ] **Invariant:** فیلد اجباری جدید روی تاریخچه بدون Migration اعمال نشود
- [ ] **Invariant:** قبل از Publish تست و Approval الزامی است
- [ ] دسکتاپ ۱۶۰۰، لپ‌تاپ ۱۳۶۶، تبلت ۸۲۰، موبایل ۳۹۰؛ سایدبار سمت راست و بدون اسکرول افقی بدنه.
- [ ] Permission/Scope در Backend آزمون شود، نه فقط پنهان‌کردن دکمه.
- [ ] در خطای API حالت Error و پیام فارسی، امکان Retry امن و نمایش Data Freshness برقرار باشد.
- [ ] Duplicate submit / lost network / outdated row_version / audit پوشش داده شود.

## صفحه 43: مرکز ورود فایل‌های راهکاران
- [ ] **Invariant:** فقط خواندن، بدون Writeback
- [ ] **Invariant:** هیچ Import بدون Reconciliation/Control Totals عملیاتی نشود
- [ ] **Invariant:** Duplicate DocumentLine Idempotent
- [ ] **Invariant:** شماره‌سریال ممکن است در فیلد اضافی با Mapping پروفایل قرار گیرد
- [ ] دسکتاپ ۱۶۰۰، لپ‌تاپ ۱۳۶۶، تبلت ۸۲۰، موبایل ۳۹۰؛ سایدبار سمت راست و بدون اسکرول افقی بدنه.
- [ ] Permission/Scope در Backend آزمون شود، نه فقط پنهان‌کردن دکمه.
- [ ] در خطای API حالت Error و پیام فارسی، امکان Retry امن و نمایش Data Freshness برقرار باشد.
- [ ] Duplicate submit / lost network / outdated row_version / audit پوشش داده شود.

## صفحه 44: مرکز مغایرت و تطبیق اطلاعات
- [ ] **Invariant:** بدون اختلاف صفر یا Signoff معتبر پرونده بسته نشود
- [ ] **Invariant:** اختلاف با بازنویسی تاریخچه رفع نشود
- [ ] **Invariant:** موجودی رسمی را Platform از خود اختراع نکند
- [ ] **Invariant:** Source Snapshot timestamp همیشه نمایش یابد
- [ ] دسکتاپ ۱۶۰۰، لپ‌تاپ ۱۳۶۶، تبلت ۸۲۰، موبایل ۳۹۰؛ سایدبار سمت راست و بدون اسکرول افقی بدنه.
- [ ] Permission/Scope در Backend آزمون شود، نه فقط پنهان‌کردن دکمه.
- [ ] در خطای API حالت Error و پیام فارسی، امکان Retry امن و نمایش Data Freshness برقرار باشد.
- [ ] Duplicate submit / lost network / outdated row_version / audit پوشش داده شود.

## Smoke Test انجام‌شده روی Prototype
برای گزارش اجرا فایل `render_results.json` را ببینید. این Smoke Test جای آزمون‌های واقعی Backend، امنیت و کارکرد کارخانه را نمی‌گیرد.

## Pilot قبل از Go-live
- ورودی واقعی و Mask شده از راهکاران و نمونه‌های Planning/WH با کنترل مجموع و سند.
- اجرای عملی تسک، بازرسی QA و انتقال داده با یک گروه کوچک و بازبینی خطا.
- سناریوی انقضای گواهی، تغییر حقوق با عدم تفکیک وظایف، تعارض نام ماده ۲۲۸۸، Import تکراری و اختلاف موجودی.
- ثبت Issue، Severity، Owner، Reproduction Steps، Fix، Regression و Sign-off.
