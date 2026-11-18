# PHASE_02 UI fidelity baseline (DEC-061)

Measured by `frontend/e2e/fidelity/fidelity.spec.ts` (method: `frontend/e2e/fidelity/README.md`).
Commit `54a40b35c1ec` · 2026-11-18 · browser channel msedge · threshold 95.0% at every width.

Score per width = 0.5 × presence + 0.3 × layout (IoU ≥ 0.5) + 0.2 × style. Colours are checked against the approved brand tokens, not the mockup colours.

| Page | 1440 | 1180 | 768 | 390 | min | ≥ 95%? |
|---|---|---|---|---|---|---|
| 01 مرکز کنترل سریال — نمای خلاصه (hand spec) | 44.2% | 44.2% | 58.3% | 54.1% | 44.2% | no |
| 02 مرکز کنترل سریال — تب سفارش (hand spec) | 39.6% | 39.6% | 50.7% | 43.2% | 39.6% | no |
| 04 ردیابی محصولات و استایل‌ها | 45.6% | 45.6% | 42.6% | 54.6% | 42.6% | no |
| 29 ثبت سفارش و کدگذاری | 43.7% | 45.9% | 39.2% | 44.6% | 39.2% | no |
| 33 تغییرات سفارش | 40.3% | 42.6% | 37.6% | 43.5% | 37.6% | no |

## Page 01 — مرکز کنترل سریال — نمای خلاصه

| Width | score | presence | layout | style |
|---|---|---|---|---|
| 1440 | 44.2% | 49.4% | 7.7% | 85.7% |
| 1180 | 44.2% | 49.4% | 7.7% | 85.7% |
| 768 | 58.3% | 69.0% | 22.2% | 85.7% |
| 390 | 54.1% | 62.1% | 10.0% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | misplaced | 0.23 | 1180: misplaced |
| topbar (نوار بالا) | ok | 0.85 |  |
| topbar-search (جستجوی سراسری) | MISSING | - | no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| topbar-date (تاریخ امروز) | MISSING | - | no data-fid region on the built page · 1180: missing |
| topbar-user (کاربر) | misplaced | 0.23 | 1180: misplaced, 768: missing, 390: missing |
| serial-header (سربرگ سریال (شماره، محصول، کد، مشتری، وضعیت، تعداد)) | incomplete + misplaced | 0.37 | «رنگ»، «جنس» · 1180: misplaced, 390: misplaced |
| header-actions (دکمه‌های اقدام سریال (تصمیم برنامه‌ریزی، تغییر اولویت، Fast Track، سناریو، بیشتر)) [PHASE_05] | MISSING | - | «تصمیم برنامه‌ریزی»، «تغییر اولویت»، «سناریو»، «بیشتر» · no data-fid region on the built page · 1180: missing |
| date-cards (کارت‌های تعهد / پیش‌بینی / اختلاف) [PHASE_05] | MISSING | - | «تعهد»، «Forecast»، «اختلاف» · no data-fid region on the built page · 1180: missing |
| stage-flow (مراحل تولید سریال) [PHASE_03 … PHASE_09] | misplaced | 0.00 | later phase: honest «در دست ساخت» in place · 1180: misplaced, 768: misplaced, 390: misplaced |
| tabs (زبانه‌های مرکز کنترل سریال) | incomplete + misplaced | 0.00 | «برنامه‌ریزی»، «مهندسی»، «مواد و انبار»، «برش»، «تولید»، «کیفیت»، «محصول و ارسال»، «بهای تمام‌شده»، «تسک‌ها»، «اسناد»، «تاریخچه» · items 2/13 · 1180: misplaced |
| side-panel (تصمیم‌ها و پیگیری‌ها / تسک‌ها / ریسک‌ها) | incomplete + misplaced | 0.05 | «تسک‌های نزدیک موعد»، «ریسک‌ها» · 1180: misplaced, 768: misplaced, 390: misplaced |
| summary-cards (کارت‌های خلاصه (پیشرفت، موقعیت، مشکلات، آمادگی مواد، کیفیت)) [PHASE_06 … PHASE_09] | misplaced | 0.13 | later phase: honest «در دست ساخت» in place · 1180: misplaced, 768: misplaced, 390: misplaced |
| events (تاریخچه رویدادها) | MISSING | - | «تاریخچه رویدادها» · no data-fid region on the built page · 1180: missing |

Style checks at 1440: side-menu-icons FAIL (menu visible, 0 icons); panel-radius ok (built 9px vs mockup 10px (±4)); panel-border ok (4/4 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 26px (±25%)); content-padding ok (built 22px vs mockup 16px (±8)); brand-colours ok (page bg = --color-bg)

## Page 02 — مرکز کنترل سریال — تب سفارش

| Width | score | presence | layout | style |
|---|---|---|---|---|
| 1440 | 39.6% | 39.8% | 8.3% | 85.7% |
| 1180 | 39.6% | 39.8% | 8.3% | 85.7% |
| 768 | 50.7% | 44.6% | 37.5% | 85.7% |
| 390 | 43.2% | 39.7% | 11.1% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | misplaced | 0.11 | 1180: misplaced |
| topbar (نوار بالا) | ok | 0.85 |  |
| topbar-search (جستجوی سراسری) | MISSING | - | no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| topbar-date (تاریخ امروز) | MISSING | - | no data-fid region on the built page · 1180: missing |
| topbar-user (کاربر) | misplaced | 0.23 | 1180: misplaced, 768: missing, 390: missing |
| serial-header (سربرگ سریال (شماره، محصول، کد، مشتری، وضعیت، تعداد)) | incomplete + misplaced | 0.37 | «رنگ»، «جنس» · 1180: misplaced, 390: misplaced |
| header-actions (دکمه‌های اقدام سریال (تصمیم برنامه‌ریزی، تغییر اولویت، Fast Track، سناریو، بیشتر)) [PHASE_05] | MISSING | - | «تصمیم برنامه‌ریزی»، «تغییر اولویت»، «سناریو»، «بیشتر» · no data-fid region on the built page · 1180: missing |
| date-cards (کارت‌های تعهد / پیش‌بینی / اختلاف) [PHASE_05] | MISSING | - | «تعهد»، «Forecast»، «اختلاف» · no data-fid region on the built page · 1180: missing |
| stage-flow (مراحل تولید سریال) [PHASE_03 … PHASE_09] | MISSING | - | «مواد و انبار»، «مهندسی»، «تأمین»، «برش»، «دوخت»، «کنترل کیفیت»، «آماده محصول» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| tabs (زبانه‌های مرکز کنترل سریال) | incomplete + misplaced | 0.00 | «برنامه‌ریزی»، «مهندسی»، «مواد و انبار»، «برش»، «تولید»، «کیفیت»، «محصول و ارسال»، «بهای تمام‌شده»، «تسک‌ها»، «اسناد»، «تاریخچه» · items 2/13 · 1180: misplaced |
| side-panel (تصمیم‌ها و پیگیری‌ها / تسک‌ها / ریسک‌ها) | MISSING | - | «تصمیم‌ها و پیگیری‌ها»، «تسک‌های نزدیک موعد»، «ریسک‌ها» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| order-tab (محتوای تب سفارش (سربرگ سفارش، ردیف‌ها، Snapshot، نسخه‌ها، مرجع‌های خارجی، خط زمانی)) | incomplete + misplaced | 0.20 | «مرجع‌های خارجی» · 1180: misplaced, 390: misplaced |

Style checks at 1440: side-menu-icons FAIL (menu visible, 0 icons); panel-radius ok (built 13px vs mockup 10px (±4)); panel-border ok (1/1 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 26px (±25%)); content-padding ok (built 22px vs mockup 16px (±8)); brand-colours ok (page bg = --color-bg)

## Page 04 — ردیابی محصولات و استایل‌ها

| Width | score | presence | layout | style |
|---|---|---|---|---|
| 1440 | 45.6% | 52.6% | 7.1% | 85.7% |
| 1180 | 45.6% | 52.6% | 7.1% | 85.7% |
| 768 | 42.6% | 41.6% | 15.4% | 85.7% |
| 390 | 54.6% | 58.2% | 18.2% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | incomplete + misplaced | 0.13 | items 10/11 · 1180: misplaced, 768: missing |
| topbar (نوار بالا) | ok | 0.92 |  |
| topbar-search (جستجوی سراسری) | MISSING | - | no data-fid region on the built page · 1180: missing |
| topbar-date (تاریخ امروز) | MISSING | - | no data-fid region on the built page · 1180: missing, 768: missing |
| topbar-user (کاربر) | misplaced | 0.00 | 1180: misplaced, 768: missing |
| page-header (سربرگ و عنوان صفحه) | misplaced | 0.22 | 1180: misplaced, 768: misplaced, 390: misplaced |
| header-actions (دکمه‌های اقدام صفحه) | MISSING | - | «پاک‌کردن فیلترها»، «خروجی Excel»، «محصول / استایل جدید» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| kpis (کارت‌های شاخص (KPI)) | incomplete + misplaced | 0.00 | «سفارش‌های فعال»، «در جریان تولید»، «تعهدهای در معرض ریسک» · items 3/5 · 1180: misplaced, 768: misplaced, 390: misplaced |
| filters (نوار فیلتر) | incomplete + misplaced | 0.00 | «جستجوی کد محصول، استایل یا سریال»، «مشتری / برند»، «جنس اصلی»، «رنگ اصلی»، «دوره سفارش»، «موقعیت سریال» · 1180: misplaced, 768: misplaced, 390: misplaced |
| product-card (شناسنامه محصول) | incomplete + misplaced | 0.00 | «شناسنامه محصول»، «تعداد استایل»، «گرید پیش‌فرض»، «آخرین نسخه فنی»، «سریال‌های فعال» · 1180: misplaced, 768: misplaced, 390: misplaced |
| product-styles (استایل‌های این محصول) | misplaced | 0.00 | 1180: misplaced, 768: misplaced, 390: misplaced |
| serial-table (جدول سریال‌های مرتبط) | incomplete + misplaced | 0.00 | «دوره سفارش»، «گرید»، «مرحله فعلی»، «پیشرفت»، «تعهد» · 1180: misplaced |
| stage-distribution (نمودار توزیع سریال‌ها در چرخه تولید) [PHASE_07] | misplaced | 0.00 | later phase: honest «در دست ساخت» in place · 1180: misplaced, 768: misplaced, 390: misplaced |
| events (آخرین رخدادهای مرتبط) [PHASE_07] | MISSING | - | «آخرین رخدادهای مرتبط» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |

Style checks at 1440: side-menu-icons FAIL (menu visible, 0 icons); panel-radius ok (built 9px vs mockup 11px (±4)); panel-border ok (6/6 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 21px (±25%)); content-padding ok (built 22px vs mockup 22px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

## Page 29 — ثبت سفارش و کدگذاری

| Width | score | presence | layout | style |
|---|---|---|---|---|
| 1440 | 43.7% | 43.8% | 15.4% | 85.7% |
| 1180 | 45.9% | 47.5% | 16.7% | 85.7% |
| 768 | 39.2% | 39.2% | 8.3% | 85.7% |
| 390 | 44.6% | 39.2% | 16.7% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | misplaced | 0.27 | 1180: misplaced |
| topbar (نوار بالا) | ok | 0.95 |  |
| topbar-search (جستجوی سراسری) | MISSING | - | no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| topbar-date (تاریخ امروز) | MISSING | - | no data-fid region on the built page |
| topbar-user (کاربر) | misplaced | 0.00 | 1180: misplaced, 768: missing, 390: missing |
| page-header (سربرگ و عنوان صفحه) | misplaced | 0.34 | 1180: misplaced, 768: misplaced |
| header-actions (دکمه‌های اقدام صفحه) | MISSING | - | «راهنمای صفحه»، «مالکیت و منبع داده»، «بررسی و ارسال به برنامه‌ریزی» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| kpis (کارت‌های شاخص (KPI)) | MISSING | - | «مرحله ثبت سفارش»، «کد ۱۴رقمی نمونه»، «استایل‌های مشابه»، «آمادگی فرم» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| order-wizard (فرم مرحله‌ای ثبت سفارش) | incomplete | 0.52 | «فرم مرحله‌ای ثبت سفارش»، «مرحله قبل»، «مرحله بعد» · 768: misplaced, 390: misplaced |
| wizard-steps (مراحل فرم) | misplaced | 0.00 | 1180: misplaced, 768: misplaced, 390: misplaced |
| coding-validation (کدگذاری راهکاران و اعتبارسنجی) | MISSING | - | «کدگذاری راهکاران و اعتبارسنجی»، «بخش»، «مقدار نمونه»، «منبع» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| similar-styles (بررسی استایل‌های موجود) | MISSING | - | «بررسی استایل‌های موجود»، «استایل»، «ویژگی»، «نتیجه» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| pre-checks (کنترل‌های داده پیش از ثبت) | MISSING | - | «کنترل‌های داده پیش از ثبت»، «هویت محصول»، «استایل جدید»، «ثبت نهایی» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |

Style checks at 1440: side-menu-icons FAIL (menu visible, 0 icons); panel-radius ok (built 13px vs mockup 13px (±4)); panel-border ok (1/1 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 23px (±25%)); content-padding ok (built 22px vs mockup 20px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

## Page 33 — تغییرات سفارش

| Width | score | presence | layout | style |
|---|---|---|---|---|
| 1440 | 40.3% | 40.9% | 9.1% | 85.7% |
| 1180 | 42.6% | 45.0% | 10.0% | 85.7% |
| 768 | 37.6% | 35.0% | 10.0% | 85.7% |
| 390 | 43.5% | 35.0% | 20.0% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | misplaced | 0.27 | 1180: misplaced |
| topbar (نوار بالا) | ok | 0.95 |  |
| topbar-search (جستجوی سراسری) | MISSING | - | no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| topbar-date (تاریخ امروز) | MISSING | - | no data-fid region on the built page |
| topbar-user (کاربر) | misplaced | 0.00 | 1180: misplaced, 768: missing, 390: missing |
| page-header (سربرگ و عنوان صفحه) | misplaced | 0.26 | 1180: misplaced, 768: misplaced, 390: misplaced |
| header-actions (دکمه‌های اقدام صفحه) | MISSING | - | «راهنمای صفحه»، «مالکیت و منبع داده»، «ثبت تصمیم روی درخواست» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| kpis (کارت‌های شاخص (KPI)) | MISSING | - | «درخواست‌های باز»، «نیازمند تحلیل اثر»، «تغییرات اجراشده»، «درخواست لغو» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| change-list (فهرست درخواست‌ها) | incomplete + misplaced | 0.40 | «فهرست درخواست‌ها» · 1180: misplaced, 768: misplaced |
| change-compare (مقایسه قبل و بعد و گیت‌های تأیید) | MISSING | - | «مقایسه قبل و بعد»، «وضعیت قبل»، «وضعیت درخواستی»، «تحلیل اثر موردنیاز»، «گیت‌های تأیید»، «مهندسی»، «انبار/تأمین»، «برنامه‌ریزی و QA» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |
| revision-effectivity (قاعده اثرپذیری Revision بر مقدار) [PHASE_04 / PHASE_05] | MISSING | - | «قاعده اثرپذیری Revision بر مقدار» · no data-fid region on the built page · 1180: missing, 768: missing, 390: missing |

Style checks at 1440: side-menu-icons FAIL (menu visible, 0 icons); panel-radius ok (built 13px vs mockup 13px (±4)); panel-border ok (1/1 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 23px (±25%)); content-padding ok (built 22px vs mockup 20px (±8)); brand-colours ok (page bg = --color-bg)

