# PHASE_02 UI fidelity — FINAL under the tightened DEC-061 harness (2026-11-19)

Harness commit `a3d2d98` (visual form checks + blurred-grayscale structure SSIM; README "Form" / "Structure";
weights presence 0.30, layout 0.25, form checks 0.20, structure 0.10, style 0.15; threshold 95 % per page per
width). Measured on app commit `b0cba1a` with `FIDELITY_ENFORCE=1 npm run fidelity`: exit 1 (only page 04 at 768 below 95 %)
(`reports/phase-02/step-8/logs/rework5/fidelity_final_enforce.log`). Raw result: `final.json`; side-by-side shots: `shots/page-XX-<width>-final.jpg` (1440 and 390).
Baseline of the tightened harness on the unchanged app: `BASELINE2.md`.

| Page | 1440 | 1180 | 768 | 390 | min | ≥ 95%? |
|---|---|---|---|---|---|---|
| 01 مرکز کنترل سریال — نمای خلاصه | 96.0% | 96.0% | 96.0% | 95.8% | 95.8% | yes |
| 02 مرکز کنترل سریال — تب سفارش | 96.3% | 96.2% | 95.8% | 95.9% | 95.8% | yes |
| 04 ردیابی محصولات و استایل‌ها | 96.8% | 96.8% | 91.1% | 96.4% | 91.1% | **no** |
| 29 ثبت سفارش و کدگذاری | 98.6% | 99.0% | 98.4% | 98.3% | 98.3% | yes |
| 33 تغییرات سفارش | 97.1% | 96.3% | 98.9% | 97.6% | 96.3% | yes |

## Page 4 at 768: harness defect (mockup side), not fixable in the app

The page-4 mockup (`04_product_style/product_style_360.html`) overflows horizontally at 768 px
(`scrollWidth` 942 > `clientWidth` 768, RTL). Chromium's viewport screenshot of such a page starts at the
document's left origin, i.e. it is offset by `scrollWidth − clientWidth` = 174 px against the coordinates of
`getBoundingClientRect()`. `tallShot` crops the mockup regions with the unshifted rectangles, so every page-4
mockup crop at 768 is taken 174 px off its region (the side menu is cut off, the date and user crops are blank).
Evidence: a diagnostic run that only adds the 174 px offset to the mockup crop rectangles (outside the harness,
not committed) gives page 4 at 768 a structure part of 54 % instead of 30 % (93.5 % instead of 91.1 %; the
offset must not be applied to the fixed side menu, which then drops to 0 in that run, so the true value is
higher). Page 4 at 768 also loses one layout region (`product-styles`): the mockup's own box there is the
overflowing one (x −0.227 … 0.669), so the best attainable IoU with any in-page box is ≈ 0.53. The other pages'
mockups do not overflow at any width (checked: 29 / 33 share the catalogue shell; 1 / 2 are PNGs).

Measured by `frontend/e2e/fidelity/fidelity.spec.ts` (method: `frontend/e2e/fidelity/README.md`).
Commit `b0cba1a2ac86` · 2026-11-18 · browser channel msedge · threshold 95.0% at every width.

Score per width = 0.3 × presence + 0.25 × layout (IoU ≥ 0.5) + 0.2 × form checks + 0.1 × structure (blurred SSIM) + 0.15 × style. Colours are checked against the approved brand tokens, not the mockup colours.
Each extra (non-mockup) section above or between the mockup regions (`extra_above`) removes 5.0% of the total from the layout part (DEC-061 amendment).

| Page | 1440 | 1180 | 768 | 390 | min | ≥ 95%? |
|---|---|---|---|---|---|---|
| 01 مرکز کنترل سریال — نمای خلاصه (hand spec) | 96.0% | 96.0% | 96.0% | 95.8% | 95.8% | yes |
| 02 مرکز کنترل سریال — تب سفارش (hand spec) | 96.3% | 96.2% | 95.8% | 95.9% | 95.8% | yes |
| 04 ردیابی محصولات و استایل‌ها | 96.8% | 96.8% | 91.1% | 96.4% | 91.1% | no |
| 29 ثبت سفارش و کدگذاری | 98.6% | 99.0% | 98.4% | 98.3% | 98.3% | yes |
| 33 تغییرات سفارش | 97.1% | 96.3% | 98.9% | 97.6% | 96.3% | yes |

## Page 01 — مرکز کنترل سریال — نمای خلاصه

| Width | score | presence | layout | in place | extra_above | form checks | structure | style |
|---|---|---|---|---|---|---|---|---|
| 1440 | 96.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 59.8% | 100.0% |
| 1180 | 96.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 60.2% | 100.0% |
| 768 | 96.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 59.7% | 100.0% |
| 390 | 95.8% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 58.0% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 0.87 |  |
| topbar (نوار بالا) | ok | 0.90 |  |
| topbar-search (جستجوی سراسری) | ok | 0.53 |  |
| topbar-date (تاریخ امروز) | ok | 0.80 |  |
| topbar-user (کاربر) | ok | 0.87 |  |
| serial-header (سربرگ سریال (شماره، محصول، کد، مشتری، وضعیت، تعداد)) | ok | 0.75 |  |
| header-actions (دکمه‌های اقدام سریال (تصمیم برنامه‌ریزی، تغییر اولویت، Fast Track، سناریو، بیشتر)) [PHASE_05] | ok | 0.74 | later phase: honest «در دست ساخت» in place |
| date-cards (کارت‌های تعهد / پیش‌بینی / اختلاف) [PHASE_05] | ok | 0.79 | later phase: honest «در دست ساخت» in place |
| stage-flow (مراحل تولید سریال) [PHASE_03 … PHASE_09] | ok | 0.71 | later phase: honest «در دست ساخت» in place |
| tabs (زبانه‌های مرکز کنترل سریال) | ok | 0.61 |  |
| side-panel (تصمیم‌ها و پیگیری‌ها / تسک‌ها / ریسک‌ها) | ok | 0.87 |  |
| summary-cards (کارت‌های خلاصه (پیشرفت، موقعیت، مشکلات، آمادگی مواد، کیفیت)) [PHASE_06 … PHASE_09] | ok | 0.95 | later phase: honest «در دست ساخت» in place |
| events (تاریخچه رویدادها) | ok | 0.88 |  |

Form failures per width (region: failed checks; ssim when below full):

- 1440: side-menu: form ok; ssim 0.59 · topbar: form ok; ssim 0.50 · topbar-search: form ok; ssim 0.57 · topbar-date: form ok; ssim 0.05 · topbar-user: form ok; ssim 0.48 · serial-header: form ok; ssim 0.52 · header-actions: form ok; ssim 0.43 · date-cards: form ok; ssim 0.24 · stage-flow: form ok; ssim 0.24 · tabs: form ok; ssim 0.44 · side-panel: form ok; ssim 0.25 · summary-cards: form ok; ssim 0.11 · events: form ok; ssim 0.24
- 1180: topbar: form ok; ssim 0.55 · topbar-search: form ok; ssim 0.36 · topbar-date: form ok; ssim 0.17 · topbar-user: form ok; ssim 0.51 · serial-header: form ok; ssim 0.53 · header-actions: form ok; ssim 0.43 · date-cards: form ok; ssim 0.22 · stage-flow: form ok; ssim 0.26 · tabs: form ok; ssim 0.45 · side-panel: form ok; ssim 0.25 · summary-cards: form ok; ssim 0.10 · events: form ok; ssim 0.26
- 768: serial-header: form ok; ssim 0.42 · stage-flow: form ok; ssim 0.48 · side-panel: form ok; ssim 0.28 · summary-cards: form ok; ssim 0.14 · active-problems: form ok; ssim 0.47
- 390: serial-header: form ok; ssim 0.33 · stage-flow: form ok; ssim 0.52 · side-panel: form ok; ssim 0.49 · summary-cards: form ok; ssim -0.02 · active-problems: form ok; ssim 0.40

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 10px vs mockup 10px (±4)); panel-border ok (5/5 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 26px vs mockup 26px (±25%)); content-padding ok (built 20px vs mockup 16px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

## Page 02 — مرکز کنترل سریال — تب سفارش

| Width | score | presence | layout | in place | extra_above | form checks | structure | style |
|---|---|---|---|---|---|---|---|---|
| 1440 | 96.3% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 62.8% | 100.0% |
| 1180 | 96.2% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 61.5% | 100.0% |
| 768 | 95.8% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 57.7% | 100.0% |
| 390 | 95.9% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 59.4% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 0.87 |  |
| topbar (نوار بالا) | ok | 0.90 |  |
| topbar-search (جستجوی سراسری) | ok | 0.53 |  |
| topbar-date (تاریخ امروز) | ok | 0.80 |  |
| topbar-user (کاربر) | ok | 0.87 |  |
| serial-header (سربرگ سریال (شماره، محصول، کد، مشتری، وضعیت، تعداد)) | ok | 0.75 |  |
| header-actions (دکمه‌های اقدام سریال (تصمیم برنامه‌ریزی، تغییر اولویت، Fast Track، سناریو، بیشتر)) [PHASE_05] | ok | 0.74 | later phase: honest «در دست ساخت» in place |
| date-cards (کارت‌های تعهد / پیش‌بینی / اختلاف) [PHASE_05] | ok | 0.79 | later phase: honest «در دست ساخت» in place |
| stage-flow (مراحل تولید سریال) [PHASE_03 … PHASE_09] | ok | 0.71 | later phase: honest «در دست ساخت» in place |
| tabs (زبانه‌های مرکز کنترل سریال) | ok | 0.61 |  |
| side-panel (تصمیم‌ها و پیگیری‌ها / تسک‌ها / ریسک‌ها) | ok | 0.74 |  |
| order-tab (محتوای تب سفارش (سربرگ سفارش، ردیف‌ها، Snapshot، نسخه‌ها، مرجع‌های خارجی، خط زمانی)) | ok | 0.76 |  |

Form failures per width (region: failed checks; ssim when below full):

- 1440: side-menu: form ok; ssim 0.58 · topbar: form ok; ssim 0.51 · topbar-search: form ok; ssim 0.57 · topbar-date: form ok; ssim 0.05 · topbar-user: form ok; ssim 0.48 · serial-header: form ok; ssim 0.52 · header-actions: form ok; ssim 0.43 · date-cards: form ok; ssim 0.24 · stage-flow: form ok; ssim 0.26 · tabs: form ok; ssim 0.44 · side-panel: form ok; ssim 0.27 · order-tab: form ok; ssim 0.18
- 1180: side-menu: form ok; ssim 0.57 · topbar: form ok; ssim 0.55 · topbar-search: form ok; ssim 0.36 · topbar-date: form ok; ssim 0.17 · topbar-user: form ok; ssim 0.51 · serial-header: form ok; ssim 0.50 · header-actions: form ok; ssim 0.43 · date-cards: form ok; ssim 0.22 · stage-flow: form ok; ssim 0.22 · tabs: form ok; ssim 0.42 · side-panel: form ok; ssim 0.27 · order-tab: form ok; ssim 0.21
- 768: serial-header: form ok; ssim 0.42 · stage-flow: form ok; ssim 0.48 · side-panel: form ok; ssim 0.29 · order-tab: form ok; ssim 0.20
- 390: serial-header: form ok; ssim 0.33 · stage-flow: form ok; ssim 0.52 · side-panel: form ok; ssim 0.49 · order-tab: form ok; ssim 0.08

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 10px vs mockup 10px (±4)); panel-border ok (4/4 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 26px vs mockup 26px (±25%)); content-padding ok (built 20px vs mockup 16px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

## Page 04 — ردیابی محصولات و استایل‌ها

| Width | score | presence | layout | in place | extra_above | form checks | structure | style |
|---|---|---|---|---|---|---|---|---|
| 1440 | 96.8% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 67.9% | 100.0% |
| 1180 | 96.8% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 68.0% | 100.0% |
| 768 | 91.1% | 100.0% | 92.3% | 92.3% | 0 | 100.0% | 30.1% | 100.0% |
| 390 | 96.4% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 63.8% | 100.0% |

Extra sections below all mockup regions at 1440 (free): `section.panel[style-detail] «استایل 0001 · استایل ساختگی (محیط آزمایشی — داده ساختگی)»`, `div.split «محصولات»`
Extra sections below all mockup regions at 1180 (free): `section.panel[style-detail] «استایل 0001 · استایل ساختگی (محیط آزمایشی — داده ساختگی)»`, `div.split «محصولات»`
Extra sections below all mockup regions at 768 (free): `section.panel[style-detail] «استایل 0001 · استایل ساختگی (محیط آزمایشی — داده ساختگی)»`, `div.split «محصولات»`
Extra sections below all mockup regions at 390 (free): `section.panel[style-detail] «استایل 0001 · استایل ساختگی (محیط آزمایشی — داده ساختگی)»`, `div.split «محصولات»`

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

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
| stage-distribution (نمودار توزیع سریال‌ها در چرخه تولید) [PHASE_07] | ok | 0.94 | later phase: honest «در دست ساخت» in place |
| events (آخرین رخدادهای مرتبط) [PHASE_07] | ok | 0.94 | later phase: honest «در دست ساخت» in place |

Form failures per width (region: failed checks; ssim when below full):

- 1440: topbar-date: form ok; ssim 0.10 · kpis: form ok; ssim 0.34 · filters: form ok; ssim 0.14 · product-card: form ok; ssim 0.42 · product-styles: form ok; ssim 0.21 · serial-table: form ok; ssim 0.12 · stage-distribution: form ok; ssim 0.33 · events: form ok; ssim 0.45
- 1180: topbar-date: form ok; ssim 0.10 · kpis: form ok; ssim 0.35 · filters: form ok; ssim 0.06 · product-card: form ok; ssim 0.42 · product-styles: form ok; ssim 0.14 · serial-table: form ok; ssim 0.11 · stage-distribution: form ok; ssim 0.33
- 768: topbar: form ok; ssim 0.25 · topbar-date: form ok; ssim 0.00 · topbar-user: form ok; ssim 0.00 · page-header: form ok; ssim -0.09 · header-actions: form ok; ssim 0.01 · kpis: form ok; ssim 0.18 · filters: form ok; ssim 0.08 · product-card: form ok; ssim 0.25 · product-styles: form ok; ssim 0.34 · serial-table: form ok; ssim -0.01 · stage-distribution: form ok; ssim 0.23 · events: form ok; ssim 0.41
- 390: topbar: form ok; ssim 0.43 · header-actions: form ok; ssim 0.29 · kpis: form ok; ssim 0.41 · product-card: form ok; ssim 0.45 · product-styles: form ok; ssim 0.16 · serial-table: form ok; ssim 0.22 · stage-distribution: form ok; ssim 0.27 · events: form ok; ssim 0.19

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 12px vs mockup 11px (±4)); panel-border ok (7/7 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 21px vs mockup 21px (±25%)); content-padding ok (built 20px vs mockup 22px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

## Page 29 — ثبت سفارش و کدگذاری

| Width | score | presence | layout | in place | extra_above | form checks | structure | style |
|---|---|---|---|---|---|---|---|---|
| 1440 | 98.6% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 85.5% | 100.0% |
| 1180 | 99.0% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 90.0% | 100.0% |
| 768 | 98.4% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 84.2% | 100.0% |
| 390 | 98.3% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 83.1% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 0.97 |  |
| topbar (نوار بالا) | ok | 0.97 |  |
| topbar-search (جستجوی سراسری) | ok | 0.64 |  |
| topbar-date (تاریخ امروز) | ok | 0.72 |  |
| topbar-user (کاربر) | ok | 0.94 |  |
| page-header (سربرگ و عنوان صفحه) | ok | 0.86 |  |
| header-actions (دکمه‌های اقدام صفحه) | ok | 0.88 |  |
| kpis (کارت‌های شاخص (KPI)) | ok | 0.90 |  |
| order-wizard (فرم مرحله‌ای ثبت سفارش) | ok | 0.95 |  |
| wizard-steps (مراحل فرم) | ok | 0.65 |  |
| coding-validation (کدگذاری راهکاران و اعتبارسنجی) | ok | 0.95 |  |
| similar-styles (بررسی استایل‌های موجود) | ok | 0.69 |  |
| pre-checks (کنترل‌های داده پیش از ثبت) | ok | 0.69 |  |

Form failures per width (region: failed checks; ssim when below full):

- 1440: topbar: form ok; ssim 0.40 · topbar-date: form ok; ssim 0.18 · page-header: form ok; ssim 0.59 · order-wizard: form ok; ssim 0.55 · coding-validation: form ok; ssim 0.34 · similar-styles: form ok; ssim 0.41
- 1180: topbar: form ok; ssim 0.49 · page-header: form ok; ssim 0.51 · order-wizard: form ok; ssim 0.57 · coding-validation: form ok; ssim 0.34 · similar-styles: form ok; ssim 0.37
- 768: topbar-search: form ok; ssim 0.56 · page-header: form ok; ssim 0.51 · order-wizard: form ok; ssim 0.49 · wizard-steps: form ok; ssim 0.44 · coding-validation: form ok; ssim 0.42 · similar-styles: form ok; ssim 0.04
- 390: topbar: form ok; ssim 0.60 · page-header: form ok; ssim 0.52 · order-wizard: form ok; ssim 0.52 · wizard-steps: form ok; ssim 0.30 · coding-validation: form ok; ssim 0.31 · similar-styles: form ok; ssim 0.14

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 13px vs mockup 13px (±4)); panel-border ok (5/5 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 23px (±25%)); content-padding ok (built 20px vs mockup 20px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

## Page 33 — تغییرات سفارش

| Width | score | presence | layout | in place | extra_above | form checks | structure | style |
|---|---|---|---|---|---|---|---|---|
| 1440 | 97.1% | 100.0% | 100.0% | 100.0% | 0 | 93.8% | 83.9% | 100.0% |
| 1180 | 96.3% | 100.0% | 90.0% | 90.0% | 0 | 100.0% | 87.8% | 100.0% |
| 768 | 98.9% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 89.5% | 100.0% |
| 390 | 97.6% | 100.0% | 100.0% | 100.0% | 0 | 100.0% | 76.2% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 0.97 |  |
| topbar (نوار بالا) | ok | 0.97 |  |
| topbar-search (جستجوی سراسری) | ok | 0.66 |  |
| topbar-date (تاریخ امروز) | ok | 0.72 |  |
| topbar-user (کاربر) | ok | 0.94 |  |
| page-header (سربرگ و عنوان صفحه) | ok | 0.78 |  |
| header-actions (دکمه‌های اقدام صفحه) | ok | 0.90 |  |
| kpis (کارت‌های شاخص (KPI)) | ok | 0.90 |  |
| change-list (فهرست درخواست‌ها) | ok | 0.97 |  |
| change-compare (مقایسه قبل و بعد و گیت‌های تأیید) | ok | 0.97 |  |
| revision-effectivity (قاعده اثرپذیری Revision بر مقدار) [PHASE_04 / PHASE_05] | ok | 0.86 | later phase: honest «در دست ساخت» in place · 1180: misplaced |

Form failures per width (region: failed checks; ssim when below full):

- 1440: topbar: form ok; ssim 0.45 · topbar-date: form ok; ssim 0.18 · page-header: form ok; ssim 0.27 · kpis: big number -px (mockup 23px; need >= 18.4); ssim 0.71 · change-list: form ok; ssim 0.58 · change-compare: form ok; ssim 0.47
- 1180: topbar: form ok; ssim 0.51 · page-header: form ok; ssim 0.18 · change-list: form ok; ssim 0.58 · change-compare: form ok; ssim 0.40
- 768: topbar-search: form ok; ssim 0.56 · page-header: form ok; ssim 0.25 · kpis: form ok; ssim 0.60 · change-list: form ok; ssim 0.45 · change-compare: form ok; ssim 0.54 · revision-effectivity: form ok; ssim 0.56
- 390: topbar: form ok; ssim 0.58 · topbar-user: form ok; ssim 0.54 · menu-toggle: form ok; ssim 0.39 · page-header: form ok; ssim 0.22 · kpis: form ok; ssim 0.53 · change-list: form ok; ssim 0.22 · change-compare: form ok; ssim 0.42 · revision-effectivity: form ok; ssim 0.47

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 13px vs mockup 13px (±4)); panel-border ok (4/4 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 23px (±25%)); content-padding ok (built 20px vs mockup 20px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

