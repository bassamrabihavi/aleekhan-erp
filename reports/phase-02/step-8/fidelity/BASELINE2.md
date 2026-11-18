# PHASE_02 UI fidelity — BASELINE 2 (tightened harness, unchanged app)

Harness commit `a3d2d98` (visual form + structure similarity; README "Form" / "Structure"), run unchanged against the current app (app code as of `7cd42c5`; the harness commit touches only `frontend/e2e/fidelity/**`). Command: `FIDELITY_OUT=<tmp> npm run fidelity` (no FIDELITY_ENFORCE), exit 0, `2 passed` — log `reports/phase-02/step-8/logs/rework5/fidelity_baseline2.log`. Raw result: `baseline2.json`; side-by-side shots `shots/page-XX-<width>-baseline2.jpg`. The previous FINAL (old metric, all pages ≥ 95 %) is superseded: under the tightened metric no page reaches 95 %.

Measured by `frontend/e2e/fidelity/fidelity.spec.ts` (method: `frontend/e2e/fidelity/README.md`).
Commit `a3d2d98e1910` · 2026-11-18 · browser channel msedge · threshold 95.0% at every width.

Score per width = 0.3 × presence + 0.25 × layout (IoU ≥ 0.5) + 0.2 × form checks + 0.1 × structure (blurred SSIM) + 0.15 × style. Colours are checked against the approved brand tokens, not the mockup colours.
Each extra (non-mockup) section above or between the mockup regions (`extra_above`) removes 5.0% of the total from the layout part (DEC-061 amendment).

| Page | 1440 | 1180 | 768 | 390 | min | ≥ 95%? |
|---|---|---|---|---|---|---|
| 01 مرکز کنترل سریال — نمای خلاصه (hand spec) | 81.7% | 81.2% | 84.5% | 86.1% | 81.2% | no |
| 02 مرکز کنترل سریال — تب سفارش (hand spec) | 81.9% | 81.5% | 81.1% | 84.2% | 81.1% | no |
| 04 ردیابی محصولات و استایل‌ها | 91.5% | 91.3% | 85.4% | 88.5% | 85.4% | no |
| 29 ثبت سفارش و کدگذاری | 93.8% | 94.3% | 94.6% | 90.5% | 90.5% | no |
| 33 تغییرات سفارش | 93.0% | 93.3% | 92.8% | 86.5% | 86.5% | no |

## Page 01 — مرکز کنترل سریال — نمای خلاصه

| Width | score | presence | layout | in place | extra_above | form checks | structure | style |
|---|---|---|---|---|---|---|---|---|
| 1440 | 81.7% | 100.0% | 84.6% | 84.6% | 0 | 53.8% | 47.5% | 100.0% |
| 1180 | 81.2% | 100.0% | 84.6% | 84.6% | 0 | 53.8% | 42.6% | 100.0% |
| 768 | 84.5% | 100.0% | 100.0% | 100.0% | 0 | 57.1% | 30.7% | 100.0% |
| 390 | 86.1% | 100.0% | 100.0% | 100.0% | 0 | 66.3% | 28.5% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

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

Form failures per width (region: failed checks; ssim when below full):

- 1440: topbar: form ok; ssim 0.31 · topbar-search: form ok; ssim 0.57 · topbar-date: icons 0 (mockup 1; need 1+); ssim -0.10 · topbar-user: form ok; ssim 0.08 · serial-header: pills 2 (mockup 4; need 3..8); image slot none (mockup 0.069x0.070); ssim 0.25 · header-actions: form ok; ssim 0.23 · date-cards: cards 0 (mockup 3; need 2+); icon_cards 0 (mockup 3; need 2+); big number -px (mockup 18px; need >= 14.4); ssim 0.13 · stage-flow: circles 0 (mockup 8; need 6+); icons 0 (mockup 8; need 6+); ssim 0.09 · side-panel: circles 0 (mockup 2; need 2+); buttons 0 (mockup 3; need 2+); icon_cards 0 (mockup 4; need 3+); ssim 0.30 · summary-cards: dots 0 (mockup 15; need 11..25); bars 0 (mockup 2; need 2..5); icon_cards 0 (mockup 5; need 4+); big number 12px (mockup 20px; need >= 16); ssim 0.30 · events: buttons 0 (mockup 7; need 1+); icons 0 (mockup 6; need 1+); ssim 0.27
- 1180: topbar: form ok; ssim 0.32 · topbar-search: form ok; ssim 0.36 · topbar-date: icons 0 (mockup 1; need 1+); ssim -0.10 · topbar-user: form ok; ssim 0.08 · serial-header: pills 1 (mockup 4; need 3..8); image slot none (mockup 0.069x0.070); ssim 0.24 · header-actions: form ok; ssim 0.18 · date-cards: cards 0 (mockup 3; need 2+); icon_cards 0 (mockup 3; need 2+); big number -px (mockup 18px; need >= 14.4); ssim 0.03 · stage-flow: circles 0 (mockup 8; need 6+); icons 0 (mockup 8; need 6+); ssim 0.13 · side-panel: circles 0 (mockup 2; need 2+); buttons 0 (mockup 3; need 2+); icon_cards 0 (mockup 4; need 3+); ssim 0.22 · summary-cards: dots 0 (mockup 15; need 11..25); bars 0 (mockup 2; need 2..5); icon_cards 0 (mockup 5; need 4+); big number 12px (mockup 20px; need >= 16); ssim 0.29 · events: buttons 0 (mockup 7; need 1+); icons 0 (mockup 6; need 1+); ssim 0.29
- 768: serial-header: pills 2 (mockup 4; need 3..8); cards 1 (mockup 2; need 2+); icons 1 (mockup 2; need 2+); image slot none (mockup 0.185x0.170); ssim 0.17 · stage-flow: circles 0 (mockup 7; need 5+); icons 0 (mockup 7; need 5+); ssim -0.02 · side-panel: circles 0 (mockup 2; need 2+); icon_cards 0 (mockup 3; need 2+); ssim 0.21 · summary-cards: dots 0 (mockup 12; need 9..20); bars 0 (mockup 1; need 1..4); icon_cards 0 (mockup 4; need 3+); big number 12px (mockup 18px; need >= 14.4); ssim 0.13 · active-problems: icon_cards 0 (mockup 1; need 1+); ssim 0.41
- 390: serial-header: pills 1 (mockup 4; need 3..8); image slot none (mockup 0.185x0.170); ssim 0.09 · stage-flow: circles 0 (mockup 7; need 5+); icons 0 (mockup 7; need 5+); ssim 0.20 · side-panel: circles 0 (mockup 2; need 2+); icon_cards 0 (mockup 3; need 2+); ssim 0.21 · summary-cards: dots 0 (mockup 12; need 9..20); bars 0 (mockup 1; need 1..4); icon_cards 0 (mockup 4; need 3+); big number 12px (mockup 18px; need >= 14.4); ssim 0.14 · active-problems: icon_cards 0 (mockup 1; need 1+); ssim 0.22

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 10px vs mockup 10px (±4)); panel-border ok (6/6 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 26px vs mockup 26px (±25%)); content-padding ok (built 20px vs mockup 16px (±8)); brand-colours ok (page bg = --color-bg)

## Page 02 — مرکز کنترل سریال — تب سفارش

| Width | score | presence | layout | in place | extra_above | form checks | structure | style |
|---|---|---|---|---|---|---|---|---|
| 1440 | 81.9% | 100.0% | 83.3% | 83.3% | 0 | 58.3% | 44.0% | 100.0% |
| 1180 | 81.5% | 100.0% | 83.3% | 83.3% | 0 | 58.3% | 39.9% | 100.0% |
| 768 | 81.1% | 100.0% | 87.5% | 87.5% | 0 | 62.4% | 17.7% | 100.0% |
| 390 | 84.2% | 100.0% | 88.9% | 88.9% | 0 | 72.1% | 25.5% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

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

Form failures per width (region: failed checks; ssim when below full):

- 1440: topbar: form ok; ssim 0.31 · topbar-search: form ok; ssim 0.57 · topbar-date: icons 0 (mockup 1; need 1+); ssim -0.10 · topbar-user: form ok; ssim 0.08 · serial-header: pills 2 (mockup 4; need 3..8); image slot none (mockup 0.069x0.070); ssim 0.25 · header-actions: form ok; ssim 0.23 · date-cards: cards 0 (mockup 3; need 2+); icon_cards 0 (mockup 3; need 2+); big number -px (mockup 18px; need >= 14.4); ssim 0.13 · stage-flow: circles 0 (mockup 8; need 6+); icons 0 (mockup 8; need 6+); ssim 0.09 · side-panel: circles 0 (mockup 2; need 2+); buttons 0 (mockup 3; need 2+); icon_cards 0 (mockup 4; need 3+); ssim 0.23 · order-tab: icon_cards 2 (mockup 6; need 5+); ssim 0.09
- 1180: side-menu: form ok; ssim 0.58 · topbar: form ok; ssim 0.32 · topbar-search: form ok; ssim 0.36 · topbar-date: icons 0 (mockup 1; need 1+); ssim -0.10 · topbar-user: form ok; ssim 0.08 · serial-header: pills 1 (mockup 4; need 3..8); image slot none (mockup 0.069x0.070); ssim 0.24 · header-actions: form ok; ssim 0.18 · date-cards: cards 0 (mockup 3; need 2+); icon_cards 0 (mockup 3; need 2+); big number -px (mockup 18px; need >= 14.4); ssim 0.03 · stage-flow: circles 0 (mockup 8; need 6+); icons 0 (mockup 8; need 6+); ssim 0.12 · side-panel: circles 0 (mockup 2; need 2+); buttons 0 (mockup 3; need 2+); icon_cards 0 (mockup 4; need 3+); ssim 0.26 · order-tab: icon_cards 2 (mockup 6; need 5+); ssim 0.11
- 768: serial-header: pills 2 (mockup 4; need 3..8); cards 1 (mockup 2; need 2+); icons 1 (mockup 2; need 2+); image slot none (mockup 0.185x0.170); ssim 0.11 · stage-flow: circles 0 (mockup 7; need 5+); icons 0 (mockup 7; need 5+); ssim -0.06 · side-panel: circles 0 (mockup 2; need 2+); icon_cards 0 (mockup 3; need 2+); ssim 0.22 · order-tab: icon_cards 2 (mockup 6; need 5+); ssim 0.10
- 390: serial-header: pills 1 (mockup 4; need 3..8); image slot none (mockup 0.185x0.170); ssim 0.06 · stage-flow: circles 0 (mockup 7; need 5+); icons 0 (mockup 7; need 5+); ssim 0.32 · side-panel: circles 0 (mockup 2; need 2+); icon_cards 0 (mockup 3; need 2+); ssim 0.16 · order-tab: icon_cards 2 (mockup 6; need 5+); ssim 0.06

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 10px vs mockup 10px (±4)); panel-border ok (4/4 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 26px vs mockup 26px (±25%)); content-padding ok (built 20px vs mockup 16px (±8)); brand-colours ok (page bg = --color-bg)

## Page 04 — ردیابی محصولات و استایل‌ها

| Width | score | presence | layout | in place | extra_above | form checks | structure | style |
|---|---|---|---|---|---|---|---|---|
| 1440 | 91.5% | 100.0% | 100.0% | 100.0% | 0 | 75.7% | 64.1% | 100.0% |
| 1180 | 91.3% | 100.0% | 100.0% | 100.0% | 0 | 75.7% | 61.8% | 100.0% |
| 768 | 85.4% | 100.0% | 92.3% | 92.3% | 0 | 70.7% | 31.9% | 100.0% |
| 390 | 88.5% | 100.0% | 90.9% | 90.9% | 0 | 75.0% | 58.0% | 100.0% |

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
| stage-distribution (نمودار توزیع سریال‌ها در چرخه تولید) [PHASE_07] | ok | 0.97 | later phase: honest «در دست ساخت» in place |
| events (آخرین رخدادهای مرتبط) [PHASE_07] | ok | 0.97 | later phase: honest «در دست ساخت» in place |

Form failures per width (region: failed checks; ssim when below full):

- 1440: topbar-date: form ok; ssim 0.10 · kpis: bars 0 (mockup 5; need 4..10); ssim 0.20 · filters: form ok; ssim 0.06 · product-card: image slot none (mockup 0.101x0.093); ssim 0.41 · product-styles: form ok; ssim 0.21 · serial-table: dots 0 (mockup 7; need 1+); bars 0 (mockup 7; need 1+); buttons 0 (mockup 6; need 1+); ssim 0.14 · stage-distribution: bars 0 (mockup 5; need 4..10); ssim 0.20 · events: icons 0 (mockup 3; need 1+); ssim 0.46
- 1180: topbar-date: form ok; ssim 0.10 · kpis: bars 0 (mockup 5; need 4..10); ssim 0.19 · filters: form ok; ssim -0.01 · product-card: image slot none (mockup 0.124x0.114); ssim 0.36 · product-styles: form ok; ssim 0.14 · serial-table: dots 0 (mockup 7; need 1+); bars 0 (mockup 7; need 1+); buttons 0 (mockup 6; need 1+); ssim 0.13 · stage-distribution: bars 0 (mockup 5; need 4..10); ssim 0.07 · events: icons 0 (mockup 3; need 1+); ssim 0.61
- 768: side-menu: buttons 0 (mockup 1; need 1+); ssim 0.63 · topbar: form ok; ssim 0.25 · topbar-date: form ok; ssim 0.00 · topbar-user: form ok; ssim 0.00 · page-header: form ok; ssim -0.09 · header-actions: form ok; ssim 0.01 · kpis: bars 0 (mockup 5; need 4..10); ssim 0.04 · filters: form ok; ssim 0.06 · product-card: image slot none (mockup 0.197x0.181); ssim 0.35 · product-styles: form ok; ssim 0.33 · serial-table: dots 0 (mockup 7; need 1+); bars 0 (mockup 7; need 1+); buttons 0 (mockup 5; need 1+); ssim 0.10 · stage-distribution: bars 0 (mockup 5; need 4..10); ssim 0.35 · events: icons 0 (mockup 3; need 1+); ssim 0.39
- 390: topbar: form ok; ssim 0.41 · menu-toggle: form ok; ssim 0.57 · header-actions: form ok; ssim 0.29 · kpis: bars 0 (mockup 5; need 4..10); ssim 0.30 · product-card: image slot none (mockup 0.354x0.326); ssim 0.38 · product-styles: form ok; ssim 0.17 · serial-table: buttons 0 (mockup 6; need 1+); table yes (mockup cards / no table); ssim 0.10 · stage-distribution: bars 0 (mockup 5; need 4..10); ssim 0.24 · events: icons 0 (mockup 3; need 1+); ssim 0.18

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 12px vs mockup 11px (±4)); panel-border ok (7/7 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 21px vs mockup 21px (±25%)); content-padding ok (built 20px vs mockup 22px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

## Page 29 — ثبت سفارش و کدگذاری

| Width | score | presence | layout | in place | extra_above | form checks | structure | style |
|---|---|---|---|---|---|---|---|---|
| 1440 | 93.8% | 100.0% | 100.0% | 100.0% | 0 | 76.7% | 84.6% | 100.0% |
| 1180 | 94.3% | 100.0% | 100.0% | 100.0% | 0 | 76.7% | 89.6% | 100.0% |
| 768 | 94.6% | 100.0% | 100.0% | 100.0% | 0 | 81.7% | 82.7% | 100.0% |
| 390 | 90.5% | 100.0% | 91.7% | 91.7% | 0 | 76.7% | 72.7% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

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

Form failures per width (region: failed checks; ssim when below full):

- 1440: side-menu: dots 0 (mockup 1; need 1..4); ssim 0.75 · topbar: form ok; ssim 0.41 · topbar-date: form ok; ssim 0.18 · page-header: form ok; ssim 0.59 · order-wizard: buttons 3 (mockup 6; need 5+); ssim 0.55 · wizard-steps: buttons 0 (mockup 4; need 3+); row_controls 0 (mockup 4; need 3+); ssim 0.71 · coding-validation: big number 13px (mockup 25px; need >= 20); ssim 0.27 · similar-styles: form ok; ssim 0.41
- 1180: side-menu: dots 0 (mockup 1; need 1..4); ssim 0.78 · topbar: form ok; ssim 0.49 · page-header: form ok; ssim 0.51 · order-wizard: buttons 3 (mockup 6; need 5+); ssim 0.57 · wizard-steps: buttons 0 (mockup 4; need 3+); row_controls 0 (mockup 4; need 3+); ssim 0.62 · coding-validation: big number 13px (mockup 25px; need >= 20); ssim 0.33 · similar-styles: form ok; ssim 0.36
- 768: topbar-search: form ok; ssim 0.56 · page-header: form ok; ssim 0.51 · order-wizard: buttons 3 (mockup 6; need 5+); ssim 0.49 · wizard-steps: buttons 0 (mockup 4; need 3+); row_controls 0 (mockup 4; need 3+); ssim 0.44 · coding-validation: big number 13px (mockup 25px; need >= 20); ssim 0.32 · similar-styles: form ok; ssim 0.04
- 390: topbar: buttons 1 (mockup 2; need 2+); ssim 0.31 · topbar-search: form ok; ssim 0.23 · page-header: form ok; ssim 0.52 · order-wizard: buttons 3 (mockup 6; need 5+); ssim 0.45 · wizard-steps: buttons 0 (mockup 4; need 3+); row_controls 0 (mockup 3; need 2+); ssim 0.30 · coding-validation: big number 13px (mockup 25px; need >= 20); ssim 0.32 · similar-styles: form ok; ssim 0.13 · pre-checks: form ok; ssim 0.58

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 13px vs mockup 13px (±4)); panel-border ok (5/5 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 23px (±25%)); content-padding ok (built 20px vs mockup 20px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

## Page 33 — تغییرات سفارش

| Width | score | presence | layout | in place | extra_above | form checks | structure | style |
|---|---|---|---|---|---|---|---|---|
| 1440 | 93.0% | 100.0% | 100.0% | 100.0% | 0 | 75.0% | 79.6% | 100.0% |
| 1180 | 93.3% | 100.0% | 100.0% | 100.0% | 0 | 75.0% | 82.9% | 100.0% |
| 768 | 92.8% | 100.0% | 100.0% | 100.0% | 0 | 75.0% | 78.0% | 100.0% |
| 390 | 86.5% | 100.0% | 90.0% | 90.0% | 0 | 68.8% | 52.9% | 100.0% |

To-do for the restyle (regions at 1440; widths where a region differs are listed after it):

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

Form failures per width (region: failed checks; ssim when below full):

- 1440: side-menu: dots 0 (mockup 1; need 1..4); ssim 0.72 · topbar: form ok; ssim 0.45 · topbar-date: form ok; ssim 0.18 · page-header: form ok; ssim 0.27 · change-list: table yes (mockup cards / no table); ssim 0.50 · change-compare: buttons 0 (mockup 1; need 1+); big number 14px (mockup 24px; need >= 19.2); ssim 0.26 · revision-effectivity: pills 0 (mockup 3; need 2..7); ssim 0.66
- 1180: side-menu: dots 0 (mockup 1; need 1..4); ssim 0.78 · topbar: form ok; ssim 0.51 · page-header: form ok; ssim 0.17 · change-list: table yes (mockup cards / no table); ssim 0.46 · change-compare: buttons 0 (mockup 1; need 1+); big number 14px (mockup 24px; need >= 19.2); ssim 0.23 · revision-effectivity: pills 0 (mockup 3; need 2..7); ssim 0.80
- 768: topbar-search: form ok; ssim 0.56 · page-header: form ok; ssim 0.25 · kpis: form ok; ssim 0.60 · change-list: table yes (mockup cards / no table); ssim 0.13 · change-compare: buttons 0 (mockup 1; need 1+); big number 14px (mockup 24px; need >= 19.2); ssim 0.27 · revision-effectivity: pills 0 (mockup 3; need 2..7); cards 1 (mockup 2; need 2+); ssim 0.47
- 390: topbar: buttons 1 (mockup 2; need 2+); ssim 0.26 · topbar-search: form ok; ssim 0.12 · topbar-user: form ok; ssim 0.54 · menu-toggle: form ok; ssim 0.44 · page-header: form ok; ssim 0.22 · kpis: form ok; ssim 0.53 · change-list: table yes (mockup cards / no table); ssim 0.14 · change-compare: buttons 0 (mockup 1; need 1+); big number 14px (mockup 22px; need >= 17.6); ssim 0.17 · revision-effectivity: pills 0 (mockup 3; need 2..7); cards 1 (mockup 2; need 2+); ssim 0.17

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 13px vs mockup 13px (±4)); panel-border ok (4/4 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 23px vs mockup 23px (±25%)); content-padding ok (built 20px vs mockup 20px (±8)); brand-colours ok (page bg = --color-bg, primary button = --color-primary)

