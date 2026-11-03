# معماری منطقی محصول

## مسیر درخواست
Browser React (RTL, Accessibility, responsive) → HTTPS → Django REST/API + Session/Token auth → Domain Services → PostgreSQL transaction / Outbox → Workers → Search/BI Projection. فایل CAD/Excel/DXF به Object Storage خصوصی وارد شود و تنها Metadata و Hash در DB ثبت گردد؛ Parsing فقط در Worker ایزوله/Read-only. UI هیچ قاعده تجاری حساس را مستقل از Server تصمیم نمی‌گیرد.

## مرزهای ماژول و قواعد مالکیت
- **Commercial:** Customer, Inquiry, Quote, PO Header/Line, Product/Style request, customer approval, customer grade requirement, promised date.
- **Identity/Product Registry:** Product, Style, Code Registry, Serial, Snapshot, Product360 — تابع قانون کدگذاری تاییدشده و Identity uniqueness.
- **Engineering:** Pattern/DXF, Tool/Die/Cliche/Jig, Skiving, BOM, OPC, Time Standards, Revision Package, Release و Tool compatibility.
- **Planning:** Demand/Forecast/Commit, Schedule, Resource/Skill/Calendar constraints, Serial allocation to lines, capacity scenarios, priority FastTrack with anti-starvation.
- **Warehouse:** Source snapshots, Lot, Location, Quality Hold projection, Reservation, Issue/Return, Green stock and GAP; official ERP documents as external refs.
- **Supply:** Purchase demand, quotes, fabrication request, ETA, supplier follow-up. Receipt confirmed by Warehouse, not Supply.
- **Production:** Cutting, Batch/Bundle ledger, station entry/exit, shift, operators, downtime, scrap/rework, accepted operation completion.
- **QA/QC:** Incoming Quality, NCR/CAPA, required vs actual grade, QC release, deviations, quarantine.
- **FG/Dispatch:** FG receipt/physical count and controlled partial shipments/customer receipt.
- **HR/Performance:** Skills, training, salary-sensitive data, SWU + KPI with redacted scope and separate approvals.
- **Admin/Platform:** Identity, RBAC/ABAC, workflow, document, event, audit, import, background jobs, configuration, observability, dynamic fields, AI gateway.

## دامنه تراکنش‌ها
One transaction = write to owning tables + immutable audit record + outbox event. Consumers handle events idempotently and maintain projections; NEVER mutate other modules' authoritative data via direct table writes. Multi-system workflows use state machine and compensation, not distributed database transactions.

## سناریوی صحت هر سریال
PO header چند PO line؛ هر line حداکثر یک Serial (شماره یکتا برای واحد سفارش/پروژه) با Product/Style/Revision Snapshot؛ در همان Serial چند Batch/Bundle و خروجی/ارسال جزئی مجاز؛ پایان فقط پس از تحویل کامل و تطبیق گرید و اسناد. شماره Serial جدا از ProductCode/DieCode است.

## کیفیت داده
Staging + Source Registry با Raw Row، workbook/sheet/cell/formula/value و Hash. قواعد تبدیل نسخه‌دار. هیچ خطایی به String empty/0 تبدیل نمی‌شود؛ status `PENDING_REVIEW`, `ERROR`, `MATCHED`, `REJECTED`, `APPROVED`، و اقدام دستی با audit.

## وابستگی‌های باز
Details in `11_PROJECT_MANAGEMENT/DECISION_REGISTER.csv`: موتور کدگذاری ۱۴رقمی همه خانواده‌ها، استخراج واقعی Python تیغه تا Tracking، طرح دقیق کفش/زمان، احراز هویت محیطی، پیکربندی شیفت و SWU و سیاست انبار. برنامه‌نویسی ماژول مستقل مجاز است؛ Publish تعهد/کد/استاندارد قطعی با تصمیم باز ممنوع.
