# DEC-057 — ماتریس دسترسی فاز ۲ (مشتری، محصول، کد، سفارش، سریال، تغییرات)

- اولویت: P0 برای Gate فاز ۲ («roles accepted»)
- Gate: Phase-2 · حوزه: Security/Identity/Commercial · مالک: کارفرما + بازرگانی + برنامه‌ریزی · منبع: `ROLE_PERMISSION_MATRIX_FA.md` (پیشنهادی)، طراحی صفحه ۲۹، DEC-049/DEC-056
- وضعیت: OPEN — بسته تصمیم (شناسه تازه؛ ارکستریتور با `status.py add-decision` ثبت می‌کند)
- تهیه: PHASE_02 / 02.1، تاریخ 2026-11-11
- مرتبط: CONFLICTS C-62 · RISKS R-43 · DEC-005 Q-A، DEC-006 پرسش ۶، DEC-059

## چرا این تصمیم لازم است
ماتریس مصوب فاز ۱ (v1.3) هیچ نقش کسب‌وکاری برای سفارش، کد و سریال ندارد. اسناد handoff هم با هم نمی‌خوانند:
- «بازرگانی: ثبت/ویرایش/تأیید شرایط مشتری؛ برنامه‌ریزی: تأیید آزادسازی برنامه».
- «ایجاد سریال با تأیید برنامه‌ریزی».
- مالک قاعده کد: «برنامه‌ریزی + بازرگانی».

تا تصویب، هیچ نقشی این مجوزها را ندارد (همه‌چیز بسته؛ DEC-047). پس همه صفحه‌های فاز ۲ برای همه پاسخ «دسترسی ندارید» می‌دهند.

## نقش‌های پیشنهادی تازه (همه از نوع BUSINESS)
| نقش | کار |
|---|---|
| `commercial_officer` | ثبت/ویرایش مشتری، پیش‌نویس سفارش، درخواست تغییر |
| `commercial_manager` | تصمیم روی درخواست تغییر بازرگانی؛ تأیید سفارش فقط اگر DEC-006 گزینه L-B شود |
| `planning_officer` | تأیید سفارش همراه با ساخت سریال (DEC-006 گزینه L-A)، ارسال سفارش به برنامه‌ریزی، اعمال تغییر تأییدشده |
| `product_data_steward` | ثبت محصول/استایل/نسخه استایل، مرجع‌های خارجی، پیش‌نویس قاعده کد، صدور کد (پس از DEC-005) |
| `code_rule_approver` | تأیید/رد/فعال‌سازی نسخه قاعده کد (نفر دوم؛ maker≠checker) |

نقش‌های موجود:
- `management_viewer` فقط خواندن.
- `employee` هیچ دسترسی فاز ۲ ندارد.
- نقش‌های فنی (`it_ops`، `security_auditor`) هیچ حق تأیید کسب‌وکاری ندارند (DEC-003).

## مجوزهای پیشنهادی (نام‌ها در OpenAPI 0.7.0-draft)
| مجوز | نقش‌های پیشنهادی | MFA تازه |
|---|---|---|
| `identity.customer.read` | همه نقش‌های بالا + `management_viewer` | خیر |
| `identity.customer.manage` | `commercial_officer` | خیر |
| `identity.product.read` | همه نقش‌های بالا + `management_viewer` | خیر |
| `identity.product.manage` | `product_data_steward` | خیر |
| `identity.product_code.read` | همه نقش‌های بالا | خیر |
| `identity.product_code.issue` | `product_data_steward` | **بله** |
| `identity.code_rule.read` | `product_data_steward`، `code_rule_approver`، `planning_officer` | خیر |
| `identity.code_rule.manage` | `product_data_steward` | خیر |
| `identity.code_rule.approve` | `code_rule_approver` | **بله** |
| `identity.serial.read` | همه نقش‌های بالا + `management_viewer` | خیر |
| `identity.serial.allocate` | `planning_officer` | خیر |
| `identity.external_ref.read` / `.manage` | همه نقش‌های بالا / `commercial_officer` + `product_data_steward` | خیر |
| `identity.historical.read` | `planning_officer`، `product_data_steward` | خیر |
| `commercial.order.read` | همه نقش‌های بالا + `management_viewer` | خیر |
| `commercial.order.manage` | `commercial_officer` | خیر |
| `commercial.order.confirm` | `planning_officer` (اگر DEC-006 گزینه L-A؛ در L-B: `commercial_manager`) | **بله** |
| `commercial.order.release` | `planning_officer` | خیر |
| `commercial.change.read` | همه نقش‌های بالا + `management_viewer` | خیر |
| `commercial.change.request` | `commercial_officer`، `planning_officer` | خیر |
| `commercial.change.decide` | `commercial_manager` | **بله** |
| `commercial.change.apply` | `planning_officer` | خیر |

## پرسش‌ها
1. نقش‌های بالا را قبول دارید؟ نقشی کم یا زیاد است؟
2. **تأیید سفارش با کیست:** مدیر بازرگانی یا برنامه‌ریزی؟ این پرسش با DEC-006 گزینه L-A پیوند دارد: اگر سریال هنگام تأیید ساخته شود، تأییدکننده حق ساخت سریال را هم می‌گیرد.
3. **دامنه رکورد:** آیا هر کارشناس فقط مشتری‌های خودش را ببیند (دامنه `CUSTOMER`)، یا همه مشتری‌ها برای همه نقش‌های بالا؟
4. **مالک (owner_admin):** طبق DEC-056، مالک درخواست‌های تأیید را مستقیم تصمیم می‌گیرد. آیا این حق برای تأیید قاعده کد، تأیید سفارش و تصمیم درخواست تغییر هم باشد؟ خودتأییدی همچنان ممنوع است.
5. MFA تازه فقط برای چهار ردیف «بله» کافی است؟

## گزینه‌ها
- **M-A) جدول بالا همان‌طور که هست؛** دامنه همه مشتری‌ها؛ مالک حق تصمیم مستقیم دارد (ادامه DEC-056).
- **M-B) جدول بالا + دامنه مشتری** برای `commercial_officer`. پیامد: امن‌تر؛ تخصیص مشتری به هر کارشناس لازم می‌شود.
- **M-C) نقش‌ها کمتر:** یک نقش بازرگانی و یک نقش برنامه‌ریزی، و `code_rule_approver` جدا.
  - پیامد: ساده‌تر.
  - اگر یک نفر هم سفارش بسازد و هم تأیید کند، maker≠checker باید در سطح درخواست اعمال شود.

## پیشنهاد (فقط پیشنهاد)
- **M-A** برای شروع.
- بازرگانی سفارش را ثبت و اعتبارسنجی می‌کند؛ **برنامه‌ریزی (`planning_officer`) سفارش را تأیید می‌کند و سریال‌ها در همان تراکنش ساخته می‌شوند** (هم‌خوان با DEC-006 گزینه L-A و طراحی صفحه ۲۹ «ایجاد سریال با تأیید برنامه‌ریزی»). اگر DEC-006 گزینه L-B شد، تأیید سفارش با `commercial_manager` و ساخت سریال جدا با `planning_officer`.
- مالک حق تصمیم مستقیم دارد، ولی هرگز روی درخواست خودش.

## چه چیزی مسدود است
- تا تصویب، هیچ نقشی مجوزهای `identity.*` و `commercial.*` را ندارد و پاسخ همه 403 است.
- پیش‌نویس ماتریس v2.0 در گام ۰۲.۲ با seed migration ساخته می‌شود، فقط پس از تصویب.
- گام‌های ۰۲.۲ (پایگاه داده) و ۰۲.۳ (موتور) ادامه دارند.

## نحوه ثبت
`status.py decide DEC-057 APPROVED --by "<نام>" --note "M-<A/B/C> + تأیید سفارش: <نقش> + دامنه: <همه/مشتری> + مالک: <بله/خیر> + MFA: <قبول/تغییر>"`
