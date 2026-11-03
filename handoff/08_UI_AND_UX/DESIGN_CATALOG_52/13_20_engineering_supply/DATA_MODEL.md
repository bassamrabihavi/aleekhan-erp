# مدل داده و مالکیت صفحات ۱۳ تا ۲۰

## مرزهای مالکیت
- مهندسی: مقر/جیگ، لیویس، BOM، OPC، بسته فنی و Revision، زمان استاندارد/الگوی تأییدشده؛ بدون تغییر موجودی فیزیکی.
- انبار: Lot، موجودی واقعی، رزرو، جداسازی، تحویل، GAP فیزیکی، تأیید دریافت؛ تأمین نمی‌تواند GAP را تنها با اعلام وصول ببندد.
- تأمین: Supplier، قیمت رسمی/تاریخ اعتبار، پیگیری، ETA و درخواست خرید؛ موجودی ERP از Import/سند رسمی راهکاران خوانده می‌شود.
- Planning: مالک تاریخ تعهد، Release و سیاست اولویت؛ مهندسی نباید خط فیزیکی تعیین کند.

## Entityهای اصلی
- `engineering.jig`, `engineering.jig_revision`, `engineering.jig_pattern_relation`, `warehouse.tool_instance`.
- `engineering.skiving_region` (piece_revision_id, region_geometry_ref, skiving_type, target_f, width_mm, seq, reason, status).
- `engineering.bom_revision`, `engineering.bom_piece_line`, `engineering.bom_material_line`, `engineering.bom_alternative`.
- `engineering.opc_revision`, `engineering.operation`, `engineering.operation_dependency`, `engineering.operation_resource_requirement`.
- `engineering.release_package`, `engineering.package_item`, `engineering.release_effectivity`.
- `warehouse.separation`, `warehouse.reservation`, `warehouse.stock_ledger`, `warehouse.gap_case`, `warehouse.material_lot`.
- `supply.purchase_request`, `supply.supplier_promise_history`, `planning.forecast_consumption`, `planning.mrp_snapshot`.
- `audit.audit_event`, `outbox.outbox_event`, `workflow.task`.

## قواعد یکپارچگی
1. نسخه تأییدشده Engineering immutable است؛ تغییر نسخه جدید و Impact Analysis ایجاد می‌کند.
2. BOM Line باید به Material Master دارای Code، Unit و Canonical Name مربوط شود؛ Alias خام حفظ می‌شود.
3. `net_quantity`, `unit`, `waste_standard` در هر ماده مستقل و Decimal هستند. نقش متریال نامحدود و ردیفی است.
4. OPC به Operation Master متصل است و DAG بدون چرخه دارد؛ زمان آماده‌سازی، کار، انتظار و انتقال مستقل هستند.
5. Engineering Release Package باید Compatibility BOM/OPC/Pattern/Skiving/Tooling را قبل از Released شدن بررسی کند.
6. رزرو انبار با Lot، Grade، Stock Ownership، Quality Hold و Available Quantity بررسی تراکنشی می‌شود؛ نه صرفاً تغییر عدد در UI.
7. GAP تا تأیید رسید فیزیکی انبار Close نمی‌شود؛ ETA تأمین versioned است.
8. Forecast Consumption با Firm Order، Aggregation دوباره‌شماری ندارد؛ MRP Grade/Owner-aware است و Timestamp Snapshot را نشان می‌دهد.
9. هر Command یک Idempotency Key، Actor و Audit/Outbox اتمیک دارد.
10. پروجکشن‌ها احتمال Lag دارند؛ صفحات بحرانی بعد از Command از پاسخ Authoritative استفاده می‌کنند.

## کد و هویت
- کد ۱۴رقمی محصول و تیغه از نظر فرمت ثابت، اما الگوریتم تولیدشان مستقل است.
- در صفحات ۱۳ تا ۲۰ هیچ کد راهکاران به‌صورت خودکار صادر نمی‌شود.
- رقم‌های ۲۲۸۸، ۰۲۷۹، ۲۴۵۱ صرفاً مثال تصویری و از نظر مرجع ERP تأیید نشده‌اند.
