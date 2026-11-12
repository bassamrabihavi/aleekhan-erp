# وضعیت پروژه عالیخان — ۲۱ آبان ۱۴۰۵

> تاریخ‌ها برآورد برنامه‌ریزی‌اند، نه تعهد. با هر گام قبول‌شده، ضریب سرعت واقعی جایگزین فرض می‌شود.

## خلاصه

- **فاز فعال:** PHASE_02 مشتری، محصول، استایل، ثبت سفارش و سریال (فعال)
- **گام جاری:** 02.3 Domain Engine (در صف)
- **پیشرفت:** 18/120 گام قبول‌شده
- **آماده تست شما:** 0 مورد
- **تصمیم P0 باز (کل پروژه):** 15
- **شروع پایلوت (PHASE_13):** خوش‌بینانه ۲۱ دی ۱۴۰۵ · مبنا **۱۴ بهمن ۱۴۰۵** · بدبینانه ۲۹ اسفند ۱۴۰۵
- **مسیر بحرانی:** 00 → 01 → 02 → 03 → 04 → 05 → 07 → 08 → 09 → 10 → 12 → 13 — تا شروع پایلوت 36 هفته برآوردی

## آماده تست

هنوز چیزی برای تست عملیاتی آماده نیست.

## منتظر تصمیم شما (افق فعلی)

تصمیم بازی در افق فعلی نیست.

## گراف وابستگی فازها

```mermaid
flowchart LR
  P00["00 · تثبیت قراردادهای مبنا و راه‌اندازی مخزن امن<br/>2w · پذیرفته‌شده"]:::ok
  P01["01 · هسته سازمانی، امنیت، اسناد و گردش کار<br/>3w · پذیرفته‌شده"]:::ok
  P02["02 · مشتری، محصول، استایل، ثبت سفارش و سریال<br/>3w · فعال"]:::act
  P03["03 · تیغه، کلیشه، مقر، لیویس و بسته فنی<br/>4w · شروع‌نشده"]:::ns
  P04["04 · ساختار مواد، قطعه، مسیر عملیات، استاندارد زمان<br/>4w · شروع‌نشده"]:::ns
  P05["05 · تقاضا، تعهد، سناریوی ظرفیت و زمان‌بندی<br/>4w · شروع‌نشده"]:::ns
  P06["06 · انبار مواد، راهکاران، تفکیک و GAP<br/>4w · شروع‌نشده"]:::ns
  P07["07 · برش، خطوط، بچ، اپراتور و توقف‌ها<br/>5w · شروع‌نشده"]:::ns
  P08["08 · کیفیت مواد و محصول، گرید و بازکاری<br/>3w · شروع‌نشده"]:::ns
  P09["09 · انبار محصول، ارسال جزئی و بستن سریال<br/>2w · شروع‌نشده"]:::ns
  P10["10 · بهای تمام‌شده، منابع انسانی و داشبورد<br/>3w · شروع‌نشده"]:::ns
  P11["11 · دستیار AI، قوانین پویا و مانیتورینگ<br/>3w · شروع‌نشده"]:::ns
  P12["12 · مهاجرت و آزمون سرتاسری روی داده امن<br/>3w · شروع‌نشده"]:::ns
  P13["13 · پایلوت عملیاتی کنترل‌شده و بازخورد<br/>4w · شروع‌نشده"]:::ns
  P14["14 · بهره‌برداری کنترل‌شده و پشتیبانی<br/>4w · شروع‌نشده"]:::ns
  P00 ==> P01
  P01 ==> P02
  P01 --> P03
  P02 ==> P03
  P02 --> P04
  P03 ==> P04
  P02 --> P05
  P04 ==> P05
  P01 --> P06
  P02 --> P06
  P04 --> P06
  P03 --> P07
  P04 --> P07
  P05 ==> P07
  P06 --> P07
  P04 --> P08
  P06 --> P08
  P07 ==> P08
  P02 --> P09
  P07 --> P09
  P08 ==> P09
  P04 --> P10
  P05 --> P10
  P07 --> P10
  P09 ==> P10
  P01 --> P11
  P02 --> P11
  P06 --> P11
  P07 --> P11
  P01 --> P12
  P02 --> P12
  P03 --> P12
  P04 --> P12
  P05 --> P12
  P06 --> P12
  P07 --> P12
  P08 --> P12
  P09 --> P12
  P10 ==> P12
  P11 --> P12
  P12 ==> P13
  P13 --> P14
  classDef ns fill:#eef0f3,stroke:#8a94a6,color:#1d2433
  classDef act fill:#dbe9ff,stroke:#2f6fe4,color:#0b2a66,stroke-width:2px
  classDef gp fill:#fff1cc,stroke:#c98a00,color:#5a3d00,stroke-width:2px
  classDef ok fill:#d8f3e3,stroke:#1f9254,color:#0c3d22
  classDef bl fill:#ffe0e0,stroke:#d33b3b,color:#5c0f0f,stroke-width:2px
```

## جدول فازها

| فاز | عنوان | وابستگی | وضعیت | گام قبول | برآورد (هفته) | شروع | پایان (مبنا) |
|---|---|---|---|---|---|---|---|
| PHASE_00 | تثبیت قراردادهای مبنا و راه‌اندازی مخزن امن | — | پذیرفته‌شده | 8/8 | 2 | ۱۴۰۵/۰۸/۱۲ | ۱۴۰۵/۰۸/۱۳ |
| PHASE_01 | هسته سازمانی، امنیت، اسناد و گردش کار | 00 | پذیرفته‌شده | 8/8 | 3 | ۱۴۰۵/۰۸/۱۳ | ۱۴۰۵/۰۸/۲۰ |
| PHASE_02 | مشتری، محصول، استایل، ثبت سفارش و سریال | 01 | فعال | 2/8 | 3 | ۱۴۰۵/۰۸/۲۰ | ۱۴۰۵/۰۸/۲۷ |
| PHASE_03 | تیغه، کلیشه، مقر، لیویس و بسته فنی | 01, 02 | شروع‌نشده | 0/8 | 4 | ۱۴۰۵/۰۸/۲۷ | ۱۴۰۵/۰۹/۰۸ |
| PHASE_04 | ساختار مواد، قطعه، مسیر عملیات، استاندارد زمان | 02, 03 | شروع‌نشده | 0/8 | 4 | ۱۴۰۵/۰۹/۰۸ | ۱۴۰۵/۰۹/۱۹ |
| PHASE_05 | تقاضا، تعهد، سناریوی ظرفیت و زمان‌بندی | 02, 04 | شروع‌نشده | 0/8 | 4 | ۱۴۰۵/۰۹/۱۹ | ۱۴۰۵/۰۹/۳۰ |
| PHASE_06 | انبار مواد، راهکاران، تفکیک و GAP | 01, 02, 04 | شروع‌نشده | 0/8 | 4 | ۱۴۰۵/۰۹/۱۹ | ۱۴۰۵/۰۹/۳۰ |
| PHASE_07 | برش، خطوط، بچ، اپراتور و توقف‌ها | 03, 04, 05, 06 | شروع‌نشده | 0/8 | 5 | ۱۴۰۵/۰۹/۳۰ | ۱۴۰۵/۱۰/۱۴ |
| PHASE_08 | کیفیت مواد و محصول، گرید و بازکاری | 04, 06, 07 | شروع‌نشده | 0/8 | 3 | ۱۴۰۵/۱۰/۱۴ | ۱۴۰۵/۱۰/۲۲ |
| PHASE_09 | انبار محصول، ارسال جزئی و بستن سریال | 02, 07, 08 | شروع‌نشده | 0/8 | 2 | ۱۴۰۵/۱۰/۲۲ | ۱۴۰۵/۱۰/۲۸ |
| PHASE_10 | بهای تمام‌شده، منابع انسانی و داشبورد | 04, 05, 07, 09 | شروع‌نشده | 0/8 | 3 | ۱۴۰۵/۱۰/۲۸ | ۱۴۰۵/۱۱/۰۶ |
| PHASE_11 | دستیار AI، قوانین پویا و مانیتورینگ | 01, 02, 06, 07 | شروع‌نشده | 0/8 | 3 | ۱۴۰۵/۱۰/۱۴ | ۱۴۰۵/۱۰/۲۲ |
| PHASE_12 | مهاجرت و آزمون سرتاسری روی داده امن | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11 | شروع‌نشده | 0/8 | 3 | ۱۴۰۵/۱۱/۰۶ | ۱۴۰۵/۱۱/۱۴ |
| PHASE_13 | پایلوت عملیاتی کنترل‌شده و بازخورد | 12 | شروع‌نشده | 0/8 | 4 | ۱۴۰۵/۱۱/۱۴ | ۱۴۰۵/۱۱/۲۵ |
| PHASE_14 | بهره‌برداری کنترل‌شده و پشتیبانی | 13 | شروع‌نشده | 0/8 | 4 | ۱۴۰۵/۱۱/۲۵ | ۱۴۰۵/۱۲/۰۶ |

## آخرین رویدادها

- `2026-11-12T17:41:29+00:00` step phase=PHASE_02 step=02.2 state=PASS
- `2026-11-12T17:29:05+00:00` step phase=PHASE_02 step=02.2 state=IN_REVIEW commit=c8b3dff
- `2026-11-12T09:30:34+00:00` step phase=PHASE_02 step=02.2 state=IN_PROGRESS
- `2026-11-12T09:30:08+00:00` decision id=DEC-058 status=APPROVED by=بسام ربیهاوی note=B-A brand table; customer rep NAME recorded (PII, no contact data, masked for viewers); PO no. not unique, warn; 4 external ref types; units shoe=pair others=piece; order types = 4 Planning types; grade text-only default
- `2026-11-12T09:22:37+00:00` decision id=DEC-059 status=APPROVED by=بسام ربیهاوی note=CR-only changes, new version+snapshot; 7 change types, after release only due date + hold/resume; C-A cancel before release only, serial CANCELLED never reused; qty increase keeps serial; single ON_HOLD returns to previous; commercial_manager decides, planning applies; due-date change also needs planning approval
- `2026-11-12T09:06:02+00:00` decision id=DEC-057 status=APPROVED by=بسام ربیهاوی note=M-A: 5 business roles per packet table; 4 fresh-MFA actions; order confirm = planning_officer (+serials same tx); scope all customers; owner may decide directly except own requests
- `2026-11-12T06:30:36+00:00` decision id=DEC-005 status=APPROVED by=بسام ربیهاوی note=Code14 = 02+type(2)+category(2)+product(4)+style(4); product=max per type+1 (belt=buckle code+width); style seq per product+category from 0001; B1 system reserves, Rahkaran confirms; family=product type; non-14 legacy DISPUTED; confirmer: employer
- `2026-11-12T06:10:55+00:00` decision id=DEC-060 status=APPROVED by=بسام ربیهاوی note=amended 2026-11-12: X-A, repo stays public (DEC-046); real handoff names remain, accepted; handoff untouched; R-38 in force
- `2026-11-12T05:25:15+00:00` decision id=DEC-006 status=APPROVED by=بسام ربیهاوی note=S-A one factory counter + L-A allocate at order confirm (same tx) + G-B gapless (counter row lock) + P-A start 63001 (legacy max <63000 in Planning intake 113f5400…) + format: plain integer, no prefix, no leading zeros; legacy variants (S-prefix, -digit/-P/-N suffix, BG) import as text history only, never generated. Who allocates -> DEC-057.
- `2026-11-11T18:28:32+00:00` decision id=DEC-060 status=APPROVED by=بسام ربیهاوی note=واقعی‌اند؛ فقط X-D: مخزن خصوصی؛ handoff دست نمی‌خورد (X-B پس گرفته شد پس از مسدودشدن ویرایش و دامنه وسیع)
- `2026-11-11T16:26:39+00:00` decision id=DEC-060 status=APPROVED by=بسام ربیهاوی note=واقعی‌اند؛ X-B + X-D: حذف از فایل‌های handoff (استثنای یک‌باره) + مخزن GitHub خصوصی شود؛ بدون بازنویسی تاریخچه
- `2026-11-11T16:26:39+00:00` step phase=PHASE_02 step=02.1 state=PASS
- `2026-11-11T15:43:05+00:00` step phase=PHASE_02 step=02.1 state=IN_REVIEW commit=1c69e99
- `2026-11-11T15:42:27+00:00` decision_added id=DEC-060 status=OPEN
- `2026-11-11T15:42:27+00:00` decision_added id=DEC-059 status=OPEN
