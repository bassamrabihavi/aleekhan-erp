# PHASE_02 UI fidelity — FINAL after the REV-0295 restyle (DEC-061)

Measured by `frontend/e2e/fidelity/fidelity.spec.ts` (method: `frontend/e2e/fidelity/README.md`).
Commit `e7bec06fd851` · 2026-11-18 · browser channel msedge · threshold 95.0% at every width.

Score per width = 0.5 × presence + 0.3 × layout (IoU ≥ 0.5) + 0.2 × style. Colours are checked against the approved brand tokens, not the mockup colours.

| Page | 1440 | 1180 | 768 | 390 | min | ≥ 95%? |
|---|---|---|---|---|---|---|
| 01 مرکز کنترل سریال — نمای خلاصه (hand spec) | 95.4% | 95.4% | 76.7% | 100.0% | 76.7% | no |
| 02 مرکز کنترل سریال — تب سفارش (hand spec) | 95.0% | 95.0% | 85.0% | 96.7% | 85.0% | no |
| 04 ردیابی محصولات و استایل‌ها | 100.0% | 100.0% | 97.7% | 97.3% | 97.3% | yes |
| 29 ثبت سفارش و کدگذاری | 100.0% | 100.0% | 100.0% | 97.5% | 97.5% | yes |
| 33 تغییرات سفارش | 100.0% | 100.0% | 100.0% | 97.0% | 97.0% | yes |

## What this run measures (REV-0295)

- Same harness, same frozen specs / scorer / measurement (`FROZEN_SHA256.txt` unchanged), run with
  `FIDELITY_ENFORCE=1`. The page list, widths, weights and threshold are those of `config.ts`.
- One measurement condition changed, and only in the (not frozen) seed of `fidelity.spec.ts`: the synthetic style now
  has **seven** confirmed orders / serials instead of one (the page-4 catalogue sample shows seven). With a single
  serial the serial table of page 4 cannot occupy the mockup's space without fake rows. Every record is synthetic and
  created through the same confirm harness as before; no mock number is shown on any page.
- Regions marked later-phase in a spec show the honest «در دست ساخت — به داده واقعی متصل نیست» (or «در دست ساخت ·
  PHASE_xx») in place; no sample number of a mockup is shown anywhere.

## Pages 1 and 2 at 768 px: not reachable with one shared shell

The 768 targets of the hand-authored specs of pages 1 and 2 are the phone concept scaled to 768 px (README: "used for
768, which is an assumption: there is no tablet concept"). At 768 they conflict with the extracted 768 targets of
pages 29 / 33 in three shell regions that are one element of the shared top bar:

| Region | pages 29 / 33 at 768 (px) | pages 1 / 2 at 768 (px) | best IoU possible for both |
|---|---|---|---|
| menu-toggle | 33 x 33 at (724, 13) | 46 x 41 at (702, 25) | < 0.46 (the intersection box alone) |
| topbar-search | input 330 x 36 at (201, 12) | icon 40 x 40 at (222, 25) | < 0.15 |
| topbar-user | avatar 32 x 32 at (11, 14) | 71 x 68 at (25, 13) | < 0.12 |

The shell follows the extracted targets (pages 4 / 29 / 33). Pages 1 and 2 therefore lose these three regions at 768,
and also carry the 1.8x-scaled phone heights of the concept; their 768 score stays below 95 % by construction
(maximum with three lost regions of nine: 0.5 + 0.3 x 6/9 + 0.2 = 90 %). Making them pass would need a different
top bar on the serial pages only. That was not done (one shared shell); the employer / orchestrator decides whether
the 768 hand targets of pages 1 / 2 are re-authored.

Other known region losses that are inside the 95 % budget are listed per page below (state ≠ ok).

## Page 01 — مرکز کنترل سریال — نمای خلاصه

| Width | score | presence | layout | style |
|---|---|---|---|---|
| 1440 | 95.4% | 100.0% | 84.6% | 100.0% |
| 1180 | 95.4% | 100.0% | 84.6% | 100.0% |
| 768 | 76.7% | 100.0% | 22.2% | 100.0% |
| 390 | 100.0% | 100.0% | 100.0% | 100.0% |

Regions at 1440 (widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 0.87 |  |
| topbar (نوار بالا) | ok | 0.90 |  |
| topbar-search (جستجوی سراسری) | ok | 0.53 | 768: misplaced |
| topbar-date (تاریخ امروز) | misplaced | 0.00 | 1180: misplaced |
| topbar-user (کاربر) | misplaced | 0.01 | 1180: misplaced, 768: misplaced |
| serial-header (سربرگ سریال (شماره، محصول، کد، مشتری، وضعیت، تعداد)) | ok | 0.78 |  |
| header-actions (دکمه‌های اقدام سریال (تصمیم برنامه‌ریزی، تغییر اولویت، Fast Track، سناریو، بیشتر)) [PHASE_05] | ok | 0.82 | later phase: honest «در دست ساخت» in place |
| date-cards (کارت‌های تعهد / پیش‌بینی / اختلاف) [PHASE_05] | ok | 0.68 | later phase: honest «در دست ساخت» in place |
| stage-flow (مراحل تولید سریال) [PHASE_03 … PHASE_09] | ok | 0.71 | later phase: honest «در دست ساخت» in place · 768: misplaced |
| tabs (زبانه‌های مرکز کنترل سریال) | ok | 0.65 |  |
| side-panel (تصمیم‌ها و پیگیری‌ها / تسک‌ها / ریسک‌ها) | ok | 0.60 | 768: misplaced |
| summary-cards (کارت‌های خلاصه (پیشرفت، موقعیت، مشکلات، آمادگی مواد، کیفیت)) [PHASE_06 … PHASE_09] | ok | 0.75 | later phase: honest «در دست ساخت» in place · 768: misplaced |
| events (تاریخچه رویدادها) | ok | 0.57 |  |

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 10px vs mockup 10px (±4)); panel-border ok (6/6 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 26px vs mockup 26px (±25%)); content-padding ok (built 20px vs mockup 16px (±8)); brand-colours ok (page bg = --color-bg)

## Page 02 — مرکز کنترل سریال — تب سفارش

| Width | score | presence | layout | style |
|---|---|---|---|---|
| 1440 | 95.0% | 100.0% | 83.3% | 100.0% |
| 1180 | 95.0% | 100.0% | 83.3% | 100.0% |
| 768 | 85.0% | 100.0% | 50.0% | 100.0% |
| 390 | 96.7% | 100.0% | 88.9% | 100.0% |

Regions at 1440 (widths where a region differs are listed after it):

| Region | state | IoU | missing labels / note |
|---|---|---|---|
| side-menu (منوی کناری (آیکون‌دار)) | ok | 0.87 |  |
| topbar (نوار بالا) | ok | 0.90 |  |
| topbar-search (جستجوی سراسری) | ok | 0.53 | 768: misplaced |
| topbar-date (تاریخ امروز) | misplaced | 0.00 | 1180: misplaced |
| topbar-user (کاربر) | misplaced | 0.01 | 1180: misplaced, 768: misplaced |
| serial-header (سربرگ سریال (شماره، محصول، کد، مشتری، وضعیت، تعداد)) | ok | 0.78 |  |
| header-actions (دکمه‌های اقدام سریال (تصمیم برنامه‌ریزی، تغییر اولویت، Fast Track، سناریو، بیشتر)) [PHASE_05] | ok | 0.82 | later phase: honest «در دست ساخت» in place |
| date-cards (کارت‌های تعهد / پیش‌بینی / اختلاف) [PHASE_05] | ok | 0.68 | later phase: honest «در دست ساخت» in place |
| stage-flow (مراحل تولید سریال) [PHASE_03 … PHASE_09] | ok | 0.71 | later phase: honest «در دست ساخت» in place · 768: misplaced |
| tabs (زبانه‌های مرکز کنترل سریال) | ok | 0.65 |  |
| side-panel (تصمیم‌ها و پیگیری‌ها / تسک‌ها / ریسک‌ها) | ok | 0.66 | 390: misplaced |
| order-tab (محتوای تب سفارش (سربرگ سفارش، ردیف‌ها، Snapshot، نسخه‌ها، مرجع‌های خارجی، خط زمانی)) | ok | 0.74 |  |

Style checks at 1440: side-menu-icons ok (menu visible, 12 icons); panel-radius ok (built 10px vs mockup 10px (±4)); panel-border ok (4/4 built panels with border or shadow); font-family ok (Vazirmatn (approved token)); heading-size ok (built 26px vs mockup 26px (±25%)); content-padding ok (built 20px vs mockup 16px (±8)); brand-colours ok (page bg = --color-bg)

## Page 04 — ردیابی محصولات و استایل‌ها

| Width | score | presence | layout | style |
|---|---|---|---|---|
| 1440 | 100.0% | 100.0% | 100.0% | 100.0% |
| 1180 | 100.0% | 100.0% | 100.0% | 100.0% |
| 768 | 97.7% | 100.0% | 92.3% | 100.0% |
| 390 | 97.3% | 100.0% | 90.9% | 100.0% |

Regions at 1440 (widths where a region differs are listed after it):

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

| Width | score | presence | layout | style |
|---|---|---|---|---|
| 1440 | 100.0% | 100.0% | 100.0% | 100.0% |
| 1180 | 100.0% | 100.0% | 100.0% | 100.0% |
| 768 | 100.0% | 100.0% | 100.0% | 100.0% |
| 390 | 97.5% | 100.0% | 91.7% | 100.0% |

Regions at 1440 (widths where a region differs are listed after it):

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

| Width | score | presence | layout | style |
|---|---|---|---|---|
| 1440 | 100.0% | 100.0% | 100.0% | 100.0% |
| 1180 | 100.0% | 100.0% | 100.0% | 100.0% |
| 768 | 100.0% | 100.0% | 100.0% | 100.0% |
| 390 | 97.0% | 100.0% | 90.0% | 100.0% |

Regions at 1440 (widths where a region differs are listed after it):

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

