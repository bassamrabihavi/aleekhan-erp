# قرارداد API پیشنهادی — صفحات ۲۱ تا ۲۸

این‌ها مسیرهای پیشنهادی‌اند، نه Endpointهای پیاده‌سازی‌شده. API نهایی باید زیر `/api/v1` دارای JWT/session معتبر، Scope/Role/Action Guard، Version/ETag، Idempotency-Key، Correlation-ID و Audit باشد.

## Query

- `/cutting/boards` ← مالک برش، اطلاعات صفحه 21 و Projectionهای خواندنی مجاز
- `/production/lines` ← مالک تولید، اطلاعات صفحه 22 و Projectionهای خواندنی مجاز
- `/production/operator-terminal` ← مالک تولید، اطلاعات صفحه 23 و Projectionهای خواندنی مجاز
- `/qa/incoming-inspection` ← مالک تضمین کیفیت، اطلاعات صفحه 24 و Projectionهای خواندنی مجاز
- `/qc/final-inspection` ← مالک کنترل کیفیت، اطلاعات صفحه 25 و Projectionهای خواندنی مجاز
- `/finished-goods/receipts` ← مالک انبار محصول، اطلاعات صفحه 26 و Projectionهای خواندنی مجاز
- `/dispatch/shipments` ← مالک انبار محصول و ارسال، اطلاعات صفحه 27 و Projectionهای خواندنی مجاز
- `/production/supervisor` ← مالک تولید، اطلاعات صفحه 28 و Projectionهای خواندنی مجاز

## Command

### 21 — مدیریت برش و تحویل دسته‌های تولید

- `POST /api/v1/cutting/boards/commands/StartCut`
- `POST /api/v1/cutting/boards/commands/InspectLeather`
- `POST /api/v1/cutting/boards/commands/RegisterCompleteSets`
- `POST /api/v1/cutting/boards/commands/RequestExtraMaterial`
- `POST /api/v1/cutting/boards/commands/CreateBundle`
- `POST /api/v1/cutting/boards/commands/TransferToLine`

### 22 — مدیریت اجرای خطوط تولید

- `POST /api/v1/production/lines/commands/RequestResourceTransfer`
- `POST /api/v1/production/lines/commands/StartDowntime`
- `POST /api/v1/production/lines/commands/ResolveDowntime`
- `POST /api/v1/production/lines/commands/ViewLineWIP`

### 23 — ترمینال اپراتور — ثبت سریع عملیات

- `POST /api/v1/production/operator-terminal/commands/StartOperation`
- `POST /api/v1/production/operator-terminal/commands/RegisterOutput`
- `POST /api/v1/production/operator-terminal/commands/PauseOperation`
- `POST /api/v1/production/operator-terminal/commands/RegisterDowntime`
- `POST /api/v1/production/operator-terminal/commands/RegisterScrap`
- `POST /api/v1/production/operator-terminal/commands/CloseOperation`

### 24 — تضمین کیفیت مواد و قرنطینه (QA)

- `POST /api/v1/qa/incoming-inspection/commands/StartInspection`
- `POST /api/v1/qa/incoming-inspection/commands/RecordMeasurement`
- `POST /api/v1/qa/incoming-inspection/commands/GradeLot`
- `POST /api/v1/qa/incoming-inspection/commands/QuarantineLot`
- `POST /api/v1/qa/incoming-inspection/commands/ApproveLot`
- `POST /api/v1/qa/incoming-inspection/commands/RejectLot`
- `POST /api/v1/qa/incoming-inspection/commands/OpenNCR`

### 25 — کنترل کیفیت نهایی و درجه‌بندی (QC)

- `POST /api/v1/qc/final-inspection/commands/ReceiveBatch`
- `POST /api/v1/qc/final-inspection/commands/RecordDefect`
- `POST /api/v1/qc/final-inspection/commands/GradeUnits`
- `POST /api/v1/qc/final-inspection/commands/RequestRework`
- `POST /api/v1/qc/final-inspection/commands/ApprovePackaging`
- `POST /api/v1/qc/final-inspection/commands/OpenNCR`

### 26 — انبار محصول نهایی و تحویل از پروژه

- `POST /api/v1/finished-goods/receipts/commands/NotifyReceipt`
- `POST /api/v1/finished-goods/receipts/commands/CountPhysically`
- `POST /api/v1/finished-goods/receipts/commands/ReconcileRahkaran`
- `POST /api/v1/finished-goods/receipts/commands/PutAwayFinishedGoods`
- `POST /api/v1/finished-goods/receipts/commands/FlagDiscrepancy`

### 27 — ارسال، حواله و تحویل مشتری

- `POST /api/v1/dispatch/shipments/commands/CreateDispatchPlan`
- `POST /api/v1/dispatch/shipments/commands/VerifyEligibleStock`
- `POST /api/v1/dispatch/shipments/commands/AttachSalesIssue`
- `POST /api/v1/dispatch/shipments/commands/ShipPartial`
- `POST /api/v1/dispatch/shipments/commands/ConfirmCustomerReceipt`

### 28 — داشبورد سرپرست خط و تحویل شیفت

- `POST /api/v1/production/supervisor/commands/ViewEmployeePerformance`
- `POST /api/v1/production/supervisor/commands/RequestResourceTransfer`
- `POST /api/v1/production/supervisor/commands/RecordShiftHandover`
- `POST /api/v1/production/supervisor/commands/RegisterLineIssue`


## خطاها

```json
{
 "code":"QUALITY_GRADE_NOT_ELIGIBLE",
 "message_fa":"گرید این محموله برای سفارش انتخابی مجاز نیست.",
 "entity_id":"LOT-871",
 "correlation_id":"...",
 "retryable":false,
 "current_version":"R4"
}
```

برای Conflict و Stale Revision از HTTP 409/412 استفاده شود؛ Permission 403؛ Input Validation 422؛ Availability/Service Failure 503. پاسخ موفق ثبت خروجی باید Transaction ID و Ledger Reference برگرداند. Duplicate Action Token نباید Qty جدید ثبت کند.
