# ۴. قرارداد داده و API (نیازمندی‌ها، نه پیاده‌سازی)

## مالکیت داده
مهندسی صاحب روش و زمان استاندارد؛ برنامه‌ریزی صاحب سناریو، تعهد و تخصیص مصوب خط؛ منابع انسانی صاحب صلاحیت و مرخصی و داده‌های حساس حقوق؛ تولید صاحب ثبت زمان واقعی و مقدار خروجی؛ نگهداری و تعمیرات صاحب وضعیت ماشین؛ QA/QC صاحب Hold، عیوب و گرید؛ انبار صاحب موجودی/Reservation؛ هیچ Projection نباید به جای مالک داده را ویرایش کند.

## موجودیت‌های اصلی — شناسه داخلی مستقل از کدهای راهکاران
| Entity | مهم‌ترین فیلدها | مالک |
|---|---|---|
| ProductFamily | id, code BAG/SHOE/BELT/POCKET | Master Data |
| Product, Style, Revision | PK، external code 14-char text, size, color, released version | بازرگانی/مهندسی |
| OperationTemplate | operation_code, family, route_stage, UOM, type, optional, revision | مهندسی |
| RouteRevision, RouteNode, RouteEdge | precedence, parallel, alternative, quality gate | مهندسی |
| WorkCenter, LineType, LineInstance | type, location, approved parallelism | برنامه‌ریزی/تولید |
| Resource, ResourceGroup | PERSON/MACHINE/TOOL/JIG/RACK, availability | مالک منبع |
| Skill, WorkerSkillValidity | level, authorization, start/end, expiry | منابع انسانی |
| ShiftPattern, ShiftAssignment, CalendarException | UTC timestamps, local TZ, working windows, breaks | منابع انسانی/تولید |
| TimeStudyPlan | purpose, sample plan, target precision, scope | مهندسی |
| Observation | raw time & quantities, conditions, source hash, status | مهندسی (با داده تولید) |
| ObservationCorrection | original_id, corrected payload, actor, reason | مهندسی |
| TimeStandardRevision | operation, scope predicate, person/machine/setup/wait, allowance, rating, approvals | مهندسی |
| StandardApplicability | Style, Revision, complexity, material/machine/skill qualifiers | مهندسی |
| WorkOrderOperation / OperationInstance | Serial, Batch, RouteRevision, Qty, dependencies | برنامه‌ریزی |
| ExecutionEvent | start/pause/resume/finish, person/machine/time, source | تولید |
| OperationQuantityLedger | event ID unique, completed, good, reject, rework, reversals | تولید |
| CapacityScenario / ScenarioVersion | snapshot, horizon, objectives, approvals | برنامه‌ریزی |
| ResourceAllocation | scenario version, resource, interval, concurrency, cost weight | برنامه‌ریزی |
| ScheduleConstraintViolation | severity, evidence, trace | برنامه‌ریزی |
| DowntimeEvent | machine/person state, reason, owner | نگهداری/تولید |
| AuditLog, OutboxEvent | who/when/why, old/new, correlation, delivery status | زیرساخت |

## روابط و ممنوعیت‌ها
- همه IDها داخلی، غیرقابل حدس زدن، Tenant/Scope-aware. Product code 14-character در فیلد Text؛ کد تیغه نیز Text و جداگانه؛ `SerialNumber` شناسه فرایندی مستقل.
- `TimeStandardRevision` هرگز با UPDATE بی‌سابقه جایگزین نشود؛ `SUPERSEDED` قدیمی + `PUBLISHED` جدید و EffectiveAt.
- تغییر استاندارد منتشرشده نباید برنامه تاریخی و نرخ Costing قبلاً منتشرشده را بازنویسی کند؛ هر سناریو نسخه قرارداد خود را Snapshot کند.
- تمام ExecutionEvents و Ledger با idempotency_key/unique condition؛ حذف نرم و Reverse Event، نه پاکسازی بی‌سابقه.
- `DurationValue` نوع‌دار با Unit (`s`, `person-min`, `machine-min`, `calendar-min`) و مقدار Decimal؛ از Float بدون کنترل برای حساب مالی استفاده نشود.
- `QuantityValue` و UOM با تبدیل مصوب (`shoe_piece` ↔ `pair`)؛ تبدیل بدون ضریب تعریف‌شده Block.
- `active_time` و `waiting_time` ممکن است همپوشانی داشته باشند؛ مدل بازه‌ای و resource occupancy برای جلوگیری از جمع غلط.

## APIهای قراردادی پیشنهادی
`POST /engineering/time-studies` (ایجاد طرح)
`POST /engineering/time-studies/{id}/observations` (ثبت خام؛ Idempotency)
`POST /engineering/time-studies/{id}/evaluate` (پیشنهاد آماری + provenance)
`POST /engineering/standards/{id}/review` (بررسی و ثبت دلیل)
`POST /engineering/standards/{id}/publish` (Approval role + MFA برای انتشار حساس)
`GET /engineering/standards/resolve?style&revision&operation&method` (مطابقت یا unresolved)
`GET /planning/capacity/available?from&to&family&line` (منابع واقعی)
`POST /planning/capacity/scenarios` (Snapshot inputs)
`POST /planning/capacity/scenarios/{id}/solve` (Job asynchronous, cancellable)
`GET /planning/capacity/scenarios/{id}/results` (constraints, bottleneck, evidence)
`POST /planning/capacity/scenarios/{id}/approve` (planner authorization)
`POST /production/operation-events` (واقعی، event sourced)
`GET /analytics/swu?from&to&scope` (version-aware, grade policy)

## نمونه رخدادهای Domain
`TimeStudyCreated`, `ObservationFinalized`, `TimeStandardApproved`, `TimeStandardPublished`, `TimeStandardSuperseded`, `StandardInvalidatedByECO`, `ShiftAssignmentPublished`, `MachineUnavailable`, `ProductionOperationCompleted`, `QuantityLedgerReversed`, `ScenarioCalculated`, `ScenarioApproved`, `ScheduleReleased`.

## رفتار خطا
کد استاندارد بی‌مطابقت، نمونه ناکافی، Skill منقضی، overlap تخصیص، Unit mismatch، مواد Hold، تاریخ خارج از تقویم، Solver timeout و نسخه داده تغییرکرده باید خطای قابل فهم فارسی + code ماشینی + correlation_id بدهد. Solver timeout **هرگز** به «پاسخ بهینه و قطعی» تفسیر نشود.

## امنیت قرارداد
AuthN/AuthZ در **Backend** اجباری. ورودی Excel/CSV/فایل ساعت‌گیری فقط در Staging و با ردیابی hash. Rate-limit و بودجه منابع Solver، جلوگیری از تزریق فرمول در خروجی CSV، ثبت Approval و محدودسازی Export داده فردی؛ هیچ کلید/رمز در config repo.
