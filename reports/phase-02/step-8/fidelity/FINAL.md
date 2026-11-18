# PHASE_02 UI fidelity — FINAL under the DEC-061 amendment (2026-11-18)

Measured by `frontend/e2e/fidelity/fidelity.spec.ts` (method: `frontend/e2e/fidelity/README.md`), run with
`FIDELITY_ENFORCE=1` on app commit `0e0d92787786` (harness commit `deea35a`) · 2026-11-18 · browser channel msedge ·
threshold 95.0 % at every width. Enforce run: exit 0, `2 passed` (`reports/phase-02/step-8/logs/rework4/fidelity_final_enforce.log`).
Raw result: `final.json`; side-by-side shots: `shots/page-XX-<width>-final.jpg` (1440 and 390).

Score per width = 0.5 × presence + 0.3 × layout (IoU ≥ 0.5) + 0.2 × style; each extra (non-mockup) section above or
between the mockup regions (`extra_above`) removes 5.0 % of the total from the layout part.

| Page | 1440 | 1180 | 768 | 390 | min | extra_above (1440/1180/768/390) | ≥ 95%? |
|---|---|---|---|---|---|---|---|
| 01 مرکز کنترل سریال — نمای خلاصه (hand spec) | 95.4% | 95.4% | 100.0% | 100.0% | 95.4% | 0/0/0/0 | yes |
| 02 مرکز کنترل سریال — تب سفارش (hand spec) | 95.0% | 95.0% | 96.2% | 96.7% | 95.0% | 0/0/0/0 | yes |
| 04 ردیابی محصولات و استایل‌ها | 100.0% | 100.0% | 97.7% | 97.3% | 97.3% | 0/0/0/0 | yes |
| 29 ثبت سفارش و کدگذاری | 100.0% | 100.0% | 100.0% | 97.5% | 97.5% | 0/0/0/0 | yes |
| 33 تغییرات سفارش | 100.0% | 100.0% | 100.0% | 97.0% | 97.0% | 0/0/0/0 | yes |

## What changed since the previous FINAL (fb7eb29)

1. **Harness (commit `deea35a`, the only harness change; employer amendment of 2026-11-18).**
   - Pages 1 and 2 at 768: the shell regions (side-menu, topbar, topbar-search, topbar-date, topbar-user,
     menu-toggle) take the catalogue shared-shell targets of `specs/page-29.json` at 768. Body regions unchanged.
   - Extra-section penalty (`extra_above`), see README "Extra sections". The scan does find extra sections: page 4
     has two (`section.panel[style-detail]`, the product list `div.split`), both fully below all mockup regions at
     every width, so free (listed as `extra_free` in `final.json` and below).
2. **App (commit `0e0d927`, CSS only).** Under the amended harness page 1 lost only body regions at 768
   (stage-flow, active-problems, side-panel, summary-cards: built sections much shorter than the concept). In the
   tablet range (601–900 px) the serial-center sections now keep the concept's proportions to the content width
   (`aspect-ratio` as preferred height, content can still grow) and 16 px spacing. Phone and desktop unchanged.
   No data, button, marker or test id changed.

## Remaining region losses (inside the 95 % budget)

- Pages 1 / 2 at 1440 and 1180: `topbar-date`, `topbar-user` (one shared shell vs. the hand-read desktop concept).
  Page 2 at 1440 / 1180 is **exactly 95.0 %** (10 of 12 regions in place): it passes, with no margin.
- Page 2 at 768 / 390: `side-panel` (the order head above it is taller than in the concept).
- Page 4 at 768: `product-styles` (IoU 0.43); at 390: `menu-toggle` (0.42).
- Pages 29 / 33 at 390: `topbar-search` (phone search behind its icon).

## Page 01 — مرکز کنترل سریال — نمای خلاصه

| Width | score | presence | layout | in place | extra_above | style |
|---|---|---|---|---|---|---|
| 1440 | 95.4% | 100.0% | 84.6% | 84.6% | 0 | 100.0% |
| 1180 | 95.4% | 100.0% | 84.6% | 84.6% | 0 | 100.0% |
| 768 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% |
| 390 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% |

Regions at 1440 ( widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 0.87 |  |
| topbar (نوار بالا) | ok | 0.90 |  |
| topbar-search (جستجوی سراسری) | ok | 0.53 |  |
| topbar-date (تاریخ امروز) | misplaced | 0.00 | 1180: misplaced |
| topbar-user (کاربر) | misplaced | 0.01 | 1180: misplaced |
| serial-header (سربرگ سریال (شماره، محصول، کد، مشتری، وضعیت، تعداد)) | ok | 0.78 |  |
| header-actions (دکمه‌های اقدام سریال (تصمیم برنامه‌ریزی، تغییر اولویت، Fast Track، سناریو، بیشتر)) [PHASE_05] | ok | 0.82 | later phase: honest «در دست ساخت» in place |
| date-cards (کارت‌های تعهد / پیش‌بینی / اختلاف) [PHASE_05] | ok | 0.68 | later phase: honest «در دست ساخت» in place |
| stage-flow (مراحل تولید سریال) [PHASE_03 … PHASE_09] | ok | 0.71 | later phase: honest «در دست ساخت» in place |
| tabs (زبانه‌های مرکز کنترل سریال) | ok | 0.65 |  |
| side-panel (تصمیم‌ها و پیگیری‌ها / تسک‌ها / ریسک‌ها) | ok | 0.60 |  |
| summary-cards (کارت‌های خلاصه (پیشرفت، موقعیت، مشکلات، آمادگی مواد، کیفیت)) [PHASE_06 … PHASE_09] | ok | 0.75 | later phase: honest «در دست ساخت» in place |
| events (تاریخچه رویدادها) | ok | 0.57 |  |

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 10px vs mockup 10px (±4)); panel-border ok (6/6 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 26px vs mockup 26px (±25%)); content-padding ok (built 20px vs mockup 16px (±8)); brand-colours ok (page bg = --color-bg)

## Page 02 — مرکز کنترل سریال — تب سفارش

| Width | score | presence | layout | in place | extra_above | style |
|---|---|---|---|---|---|---|
| 1440 | 95.0% | 100.0% | 83.3% | 83.3% | 0 | 100.0% |
| 1180 | 95.0% | 100.0% | 83.3% | 83.3% | 0 | 100.0% |
| 768 | 96.2% | 100.0% | 87.5% | 87.5% | 0 | 100.0% |
| 390 | 96.7% | 100.0% | 88.9% | 88.9% | 0 | 100.0% |

Regions at 1440 ( widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 0.87 |  |
| topbar (نوار بالا) | ok | 0.90 |  |
| topbar-search (جستجوی سراسری) | ok | 0.53 |  |
| topbar-date (تاریخ امروز) | misplaced | 0.00 | 1180: misplaced |
| topbar-user (کاربر) | misplaced | 0.01 | 1180: misplaced |
| serial-header (سربرگ سریال (شماره، محصول، کد، مشتری، وضعیت، تعداد)) | ok | 0.78 |  |
| header-actions (دکمه‌های اقدام سریال (تصمیم برنامه‌ریزی، تغییر اولویت، Fast Track، سناریو، بیشتر)) [PHASE_05] | ok | 0.82 | later phase: honest «در دست ساخت» in place |
| date-cards (کارت‌های تعهد / پیش‌بینی / اختلاف) [PHASE_05] | ok | 0.68 | later phase: honest «در دست ساخت» in place |
| stage-flow (مراحل تولید سریال) [PHASE_03 … PHASE_09] | ok | 0.71 | later phase: honest «در دست ساخت» in place |
| tabs (زبانه‌های مرکز کنترل سریال) | ok | 0.65 |  |
| side-panel (تصمیم‌ها و پیگیری‌ها / تسک‌ها / ریسک‌ها) | ok | 0.66 | 768: misplaced, 390: misplaced |
| order-tab (محتوای تب سفارش (سربرگ سفارش، ردیف‌ها، Snapshot، نسخه‌ها، مرجع‌های خارجی، خط زمانی)) | ok | 0.74 |  |

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 10px vs mockup 10px (±4)); panel-border ok (4/4 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 26px vs mockup 26px (±25%)); content-padding ok (built 20px vs mockup 16px (±8)); brand-colours ok (page bg = --color-bg)

## Page 04 — ردیابی محصولات و استایل‌ها

| Width | score | presence | layout | in place | extra_above | style |
|---|---|---|---|---|---|---|
| 1440 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% |
| 1180 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% |
| 768 | 97.7% | 100.0% | 92.3% | 92.3% | 0 | 100.0% |
| 390 | 97.3% | 100.0% | 90.9% | 90.9% | 0 | 100.0% |

Extra sections below all mockup regions at 1440 (free): `section.panel[style-detail] «استایل 0001 · استایل ساختگی (محیط آزمایشی — داده ساختگی)»`, `div.split «محصولات»`
Extra sections below all mockup regions at 1180 (free): `section.panel[style-detail] «استایل 0001 · استایل ساختگی (محیط آزمایشی — داده ساختگی)»`, `div.split «محصولات»`
Extra sections below all mockup regions at 768 (free): `section.panel[style-detail] «استایل 0001 · استایل ساختگی (محیط آزمایشی — داده ساختگی)»`, `div.split «محصولات»`
Extra sections below all mockup regions at 390 (free): `section.panel[style-detail] «استایل 0001 · استایل ساختگی (محیط آزمایشی — داده ساختگی)»`, `div.split «محصولات»`

Regions at 1440 ( widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 1.00 |  |
| topbar (نوار بالا) | ok | 1.00 |  |
| topbar-search (جستجوی سراسری) | ok | 0.65 |  |
| topbar-date (تاریخ امروز) | ok | 0.73 |  |
| topbar-user (کاربر) | ok | 0.88 |  |
| page-header (سربرگ و عنوان صفحه) | ok | 0.84 |  |
| header-actions (دکمه‌های اقدام صفحه) | ok | 0.81 |  |
| kpis (کارت‌های شاخص (KPI)) | ok | 0.93 |  |
| filters (نوار فیلتر) | ok | 0.91 |  |
| product-card (شناسنامه محصول) | ok | 0.96 |  |
| product-styles (استایل‌های این محصول) | ok | 0.82 | 768: misplaced |
| serial-table (جدول سریال‌های مرتبط) | ok | 0.98 |  |
| stage-distribution (نمودار توزیع سریال‌ها در چرخه تولید) [PHASE_07] | ok | 0.97 | later phase: honest «در دست ساخت» in place |
| events (آخرین رخدادهای مرتبط) [PHASE_07] | ok | 0.97 | later phase: honest «در دست ساخت» in place |

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 12px vs mockup 11px (±4)); panel-border ok (7/7 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 21px vs mockup 21px (±25%)); content-padding ok (built 20px vs mockup 22px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

## Page 29 — ثبت سفارش و کدگذاری

| Width | score | presence | layout | in place | extra_above | style |
|---|---|---|---|---|---|---|
| 1440 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% |
| 1180 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% |
| 768 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% |
| 390 | 97.5% | 100.0% | 91.7% | 91.7% | 0 | 100.0% |

Regions at 1440 ( widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 0.97 |  |
| topbar (نوار بالا) | ok | 0.97 |  |
| topbar-search (جستجوی سراسری) | ok | 0.64 | 390: misplaced |
| topbar-date (تاریخ امروز) | ok | 0.72 |  |
| topbar-user (کاربر) | ok | 0.94 |  |
| page-header (سربرگ و عنوان صفحه) | ok | 0.86 |  |
| header-actions (دکمه‌های اقدام صفحه) | ok | 0.88 |  |
| kpis (کارت‌های شاخص (KPI)) | ok | 0.90 |  |
| order-wizard (فرم مرحله‌ای ثبت سفارش) | ok | 0.87 |  |
| wizard-steps (مراحل فرم) | ok | 0.65 |  |
| coding-validation (کدگذاری راهکاران و اعتبارسنجی) | ok | 0.87 |  |
| similar-styles (بررسی استایل‌های موجود) | ok | 0.64 |  |
| pre-checks (کنترل‌های داده پیش از ثبت) | ok | 0.64 |  |

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 13px vs mockup 13px (±4)); panel-border ok (5/5 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 23px (±25%)); content-padding ok (built 20px vs mockup 20px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

## Page 33 — تغییرات سفارش

| Width | score | presence | layout | in place | extra_above | style |
|---|---|---|---|---|---|---|
| 1440 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% |
| 1180 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% |
| 768 | 100.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% |
| 390 | 97.0% | 100.0% | 90.0% | 90.0% | 0 | 100.0% |

Regions at 1440 ( widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 0.97 |  |
| topbar (نوار بالا) | ok | 0.97 |  |
| topbar-search (جستجوی سراسری) | ok | 0.66 | 390: misplaced |
| topbar-date (تاریخ امروز) | ok | 0.72 |  |
| topbar-user (کاربر) | ok | 0.94 |  |
| page-header (سربرگ و عنوان صفحه) | ok | 0.78 |  |
| header-actions (دکمه‌های اقدام صفحه) | ok | 0.90 |  |
| kpis (کارت‌های شاخص (KPI)) | ok | 0.90 |  |
| change-list (فهرست درخواست‌ها) | ok | 0.98 |  |
| change-compare (مقایسه قبل و بعد و گیت‌های تأیید) | ok | 0.98 |  |
| revision-effectivity (قاعده اثرپذیری Revision بر مقدار) [PHASE_04 / PHASE_05] | ok | 0.75 | later phase: honest «در دست ساخت» in place |

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 13px vs mockup 13px (±4)); panel-border ok (4/4 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 23px (±25%)); content-padding ok (built 20px vs mockup 20px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

