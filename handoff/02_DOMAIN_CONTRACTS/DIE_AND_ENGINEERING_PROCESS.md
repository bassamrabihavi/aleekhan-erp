# DXF, تیغه، کلیشه و فایل‌های فنی — CONTRACT

## مسیر تیغه مورد تأیید کارفرما
1. مهندسی، DXF با Revision/Hash مشخص را انتخاب می‌کند.
2. Parser Python فقط کاندیداهای تیغه را از هندسه و متن استخراج می‌کند. گروه رنگ قرمز AutoCAD ACI=1 در کد تاریخی نشانه کاندیداست، **نه تضمین یکتایی یا معتبر بودن تمام DXFها**.
3. فهرست کاندیداها با پرونده منبع و ابزار متناظر در «جدول پیگیری تیغه» ثبت/بازبینی می‌شود؛ عملیات تکراری نباید تکرار بی‌حساب ایجاد کند.
4. **جدول پیگیری تیغه** محل دریافت/تخصیص کد ۱۴رقمی و شرح راهکاران طبق فرآیند فعلی است. Parser نباید خودش کد ۱۴رقمی بسازد یا موجودی فیزیکی ثبت کند.
5. Engineering approval → Supply fabrication if needed → Warehouse/انبارک physical receipt → Engineering availability/projection.

## محدودیت اصل فایل Python
`AutoJ-BoM.py` دکمه Blade List دارد، اما branch `BL` به مسیر کاملی نمی‌رود؛ تابع `component_list` فعال نیست. بنابراین قوانین `BL writer` فقط از UX/رفتار کسب‌وکار قابل استنتاج است؛ **اجبار استخراج Golden Outputs پیش از Write**. اسکریپت قبلی نباید به خط تولید متصل شود.

## مشخصات Parser پیشنهادی
Input: sanctioned DXF hash, product/style/revision, selected layer/color rules, units, modelspace, optional tracker snapshot. Output: deterministic candidates with geometric entity handles, normalized texts+raw text, bounding boxes, transform units, group membership confidence, warnings, source hash, parser version. All rejected/ambiguous candidates review queue. When coordinates overlap, duplicated DXF entities or invalid geometry, STOP or flag; never silently discard.

## کلیشه
شماره کلیشه (ممکن است غیرعددی)، فایل/عکس، لوگو/برند/مشتری، اندازه، revision، موقعیت داغی در DXF، رنگ چاپ سفارش، compatibility tool, physical inventory from انبارک؛ Approval مشتری توسط بازرگانی. از تولید مجدد کد مشترک که ابعاد متعارض دارد جلوگیری شود تا بررسی دستی.

## مقر و لیویس
مقر: شیء فنی + Compatibility + Revision + مکان/ماشین/جیک. لیویس: هر Segment/Edge قطعه با عرض، نوع، ماشین، جهت، استاندارد و Validation هندسه؛ شبیه‌ساز نباید بدون مدرک عملیات را Approved کند.

## Release
فقط نسخه سازگار Patterns/BOM/OPC/Skiving/Tool/Quality می‌تواند Release شود؛ هر تغییر پس از Release یک Change Request جدید + Impact Analysis روی مواد رزروشده/WIP/سفارش دارد.
