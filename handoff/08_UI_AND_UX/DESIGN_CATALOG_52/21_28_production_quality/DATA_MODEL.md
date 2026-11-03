# قرارداد اولیه مدل داده — صفحات ۲۱ تا ۲۸

## اصول مشترک

- Serial ID یکتا؛ Product/Style/Customer Order Line ارتباط دارند، اما WIP در چند ایستگاه هم‌زمان پخش می‌شود.
- Batch IDs دارای lineage و Engineering Release Package Revision هستند.
- Quantity Ledger append-only؛ هر تغییر موجودی/WIP از Event معتبر با transaction و idempotency key می‌آید.
- Material identity و grade از Warehouse + QA دریافت می‌شود؛ شیوه مصرف از BOM/OPC Engineering.
- Production Status مستقل از Delivery Status است؛ ارسال می‌تواند جزئی باشد.
- تمام داده‌های فردی، حقوق و Cost در Field Level Access Control محدود می‌شوند.
- اعداد پول و مصرف از نوع Decimal هستند؛ تعدادهای واحد «عدد» باید integer و غیرمنفی باشند.
- تاریخ UI شمسی و ذخیره زمان استاندارد UTC؛ Business Date متعلق به شیفت مستقل است.
- تمام Quote/Standard/OPC/Quality Plan/Engineering Package versioned snapshots هستند.

## جداول و رکوردهای محوری

### 21. مدیریت برش و تحویل دسته‌های تولید

مالک: **برش**؛ Route: `/cutting/boards`.

- `cut_batch_id` — شناسه بچ (UUID) ← `cutting.cut_batch`؛ required
- `serial_id` — سریال (FK) ← `core.serial`؛ required
- `engineering_package_id` — بسته فنی (FK) ← `engineering.release_package`؛ required
- `cut_requirement_id` — نیاز برش (FK) ← `cutting.requirement`؛ required
- `material_lot_id` — Lot چرم (FK) ← `warehouse.material_lot`؛ required
- `actual_complete_sets` — تعداد ست کامل (integer) ← `cutting.output_event`؛ required
- `transfer_qty` — تعداد تحویل‌شده (integer) ← `production.transfer`؛ required

### 22. مدیریت اجرای خطوط تولید

مالک: **تولید**؛ Route: `/production/lines`.

- `line_instance_id` — شناسه خط (FK) ← `production.line_instance`؛ required
- `shift_id` — شیفت (FK) ← `resources.shift`؛ required
- `resource_allocation_id` — تخصیص منبع (FK) ← `resources.allocation`؛ required
- `operation_id` — عملیات (FK) ← `engineering.opc_operation`؛ required
- `earned_swu` — خروجی معادل (decimal) ← `analytics.production_swu`؛ derived
- `machine_state` — وضعیت ماشین (enum) ← `resources.machine_state`؛ derived

### 23. ترمینال اپراتور — ثبت سریع عملیات

مالک: **تولید**؛ Route: `/production/operator-terminal`.

- `operator_id` — اپراتور (FK) ← `hr.employee`؛ required
- `shift_id` — شیفت (FK) ← `resources.shift`؛ required
- `operation_execution_id` — اجرای عملیات (UUID) ← `production.operation_execution`؛ required
- `device_time` — زمان دستگاه (timestamp) ← `production.offline_event`؛ required
- `server_received_at` — زمان دریافت سرور (timestamp) ← `production.offline_event`؛ required
- `good_qty` — خروجی سالم (integer) ← `production.quantity_ledger`؛ required
- `scrap_qty` — ضایعات (integer) ← `qa.scrap_event`؛ optional
- `action_token` — شناسه یکتای اقدام (string) ← `integration.idempotency`؛ required

### 24. تضمین کیفیت مواد و قرنطینه (QA)

مالک: **تضمین کیفیت**؛ Route: `/qa/incoming-inspection`.

- `inspection_id` — بازرسی (UUID) ← `qa.incoming_inspection`؛ required
- `lot_id` — Lot ماده (FK) ← `warehouse.material_lot`؛ required
- `quality_standard_revision_id` — نسخه استاندارد (FK) ← `qa.standard_revision`؛ required
- `sampling_plan_id` — برنامه نمونه‌برداری (FK) ← `qa.sampling_plan`؛ required
- `measured_values` — اندازه‌گیری‌ها (typed list) ← `qa.measurement`؛ required
- `actual_material_grade_id` — گرید واقعی ماده (FK) ← `qa.material_grade`؛ required
- `disposition` — نتیجه (enum) ← `qa.quality_disposition`؛ required

### 25. کنترل کیفیت نهایی و درجه‌بندی (QC)

مالک: **کنترل کیفیت**؛ Route: `/qc/final-inspection`.

- `qc_inspection_id` — بازرسی نهایی (UUID) ← `qc.inspection`؛ required
- `batch_id` — بچ تولید (FK) ← `production.batch`؛ required
- `required_grade` — گرید سفارش (FK) ← `core.serial_quality`؛ read-only
- `actual_grade` — گرید واقعی (FK) ← `qc.grade_result`؛ required
- `defect_code` — کد عیب (FK) ← `qa.defect_master`؛ optional
- `inspected_qty` — تعداد بازرسی‌شده (integer) ← `qc.result`؛ required
- `rework_qty` — بازکاری (integer) ← `qc.disposition`؛ optional

### 26. انبار محصول نهایی و تحویل از پروژه

مالک: **انبار محصول**؛ Route: `/finished-goods/receipts`.

- `fg_receipt_id` — شناسه دریافت (UUID) ← `finished_goods.receipt`؛ required
- `serial_id` — سریال (FK) ← `core.serial`؛ required
- `qc_batch_id` — بچ QC (FK) ← `qc.release`؛ required
- `physical_count` — شمارش فیزیکی (integer) ← `finished_goods.stock_ledger`؛ required
- `grade_id` — گرید (FK) ← `qc.grade`؛ required
- `rahkaran_doc_ref` — سند راهکاران (string) ← `integration.external_reference`؛ optional
- `bin_id` — مکان محصول (FK) ← `warehouse.bin`؛ required

### 27. ارسال، حواله و تحویل مشتری

مالک: **انبار محصول و ارسال**؛ Route: `/dispatch/shipments`.

- `shipment_id` — شناسه ارسال (UUID) ← `dispatch.shipment`؛ required
- `serial_id` — سریال (FK) ← `core.serial`؛ required
- `customer_po_line_id` — ردیف سفارش مشتری (FK) ← `commercial.order_line`؛ required
- `shipped_qty` — تعداد ارسال (integer) ← `dispatch.shipment_line`؛ required
- `grade_id` — گرید ارسالی (FK) ← `qc.grade`؛ required
- `rahkaran_issue_ref` — حواله راهکاران (string) ← `integration.external_reference`؛ required
- `proof_of_delivery` — تأیید تحویل (file ref) ← `documents.attachment`؛ optional

### 28. داشبورد سرپرست خط و تحویل شیفت

مالک: **تولید**؛ Route: `/production/supervisor`.

- `line_instance_id` — خط تولید (FK) ← `production.line_instance`؛ required
- `shift_id` — شیفت (FK) ← `resources.shift`؛ required
- `employee_id` — اپراتور (FK) ← `hr.employee`؛ required
- `initial_target_swu` — هدف اولیه (decimal) ← `planning.shift_target_version`؛ required
- `adjusted_target_swu` — هدف اصلاحی (decimal) ← `planning.shift_target_version`؛ optional
- `earned_swu` — خروجی معادل (decimal) ← `analytics.earned_minutes`؛ derived
- `excluded_downtime` — توقف خارج از کنترل (duration) ← `production.downtime`؛ derived
- `handover_event_id` — تحویل شیفت (UUID) ← `production.shift_handover`؛ optional


## درخواست‌های بین‌واحدی

- برش → برنامه‌ریزی: درخواست اضافه مواد در رخداد پرت بیش از استاندارد.
- تولید → برنامه‌ریزی: درخواست جابه‌جایی منبع/تغییر هدف؛ اجرای واقعی تولید منبع داده است.
- QA → انبار: اعلان Quality Hold و تغییر Eligibility؛ انبار تخصیص را در حد مجاز تغییر می‌دهد.
- QC → انبار محصول: اعلام بسته‌بندی و درجه‌بندی؛ انبار شمارش و ذخیره می‌کند.
- بازرگانی → انبار محصول: حواله راهکاران و درخواست ارسال؛ انبار تحویل فروش را ثبت می‌کند.

## مرز تراکنش

Material issue، batch transfer، QC grade disposition، FG receipt، shipment posting و shift-target revision هرکدام نیازمند transaction/guard/permission/audit هستند. اگر داده ERP با تأخیر برسد، رکورد Stale با زمان آخرین Sync نشان داده می‌شود. هیچ Projection به‌عنوان منبع اصلی Qty استفاده نشود.
