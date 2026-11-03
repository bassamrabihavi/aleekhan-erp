# فهرست اولیه Query/Command — صفحات ۴۵–۵۲

نام‌ها قرارداد مفهومی هستند. OpenAPI واقعی هنوز ساخته نشده و نیازمند Type Safety و Perm/Scope و Idempotency است.

## 45 — دستیار هوشمند سازمانی
- Query: GetAIConversation, GetAITrace, GetAIUsage
- Command: AskWithScopedContext, CreateAIActionProposal

## 46 — مدیریت کاربران، نقش‌ها و امنیت
- Query: ListUsers, GetEffectivePermissions, GetSecurityEvents
- Command: RequestRoleChange, ExpireTemporaryAccess, RequestBreakGlass

## 47 — داده‌های پایه و موتور قوانین
- Query: ListRules, GetEffectiveRule, SimulateRuleImpact
- Command: DraftRuleRevision, SubmitRuleForApproval, PublishRuleRevision

## 48 — تابلوی زنده عملکرد سالن تولید
- Query: GetPublicLineScoreboard, GetShiftSummary
- Command: RequestFullscreenMode

## 49 — موجودی، شمارش دوره‌ای و مرجوعی مواد
- Query: GetWarehouseAvailability, GetCycleCountQueue, GetRemnantLedger
- Command: StartCycleCount, ConfirmMaterialReturn, CreateInventoryDiscrepancy

## 50 — عدم انطباق، CAPA و مجوز انحراف
- Query: GetNCRCase, GetCAPAQueue, GetDeviationEffectivity
- Command: CreateNCR, ApplyQualityHold, SubmitCAPA, ApproveDeviation, VerifyCAPAEffectiveness

## 51 — نگهداری ماشین‌ها و کالیبراسیون
- Query: GetMaintenanceQueue, GetMachineCalendar, GetCalibrationAlerts
- Command: OpenMaintenanceOrder, RecordMachineDowntime, ReleaseMachineToProduction

## 52 — مدیریت پایلوت، خطاها و انتشار نسخه
- Query: GetPilotStatus, GetReleaseGate, ListOpenCriticalDefects
- Command: CreateDefectTicket, RunRegressionSuite, ApprovePilotSignoff, RequestGoLive

## الزامات مشترک
- `correlation_id`, `request_id`, `row_version`, `idempotency_key` و `actor/scope` برای Commandهای حساس.
- Response داده محرمانه برای نقش غیرمجاز **نباید داشته باشد**، نه اینکه صرفاً در UI مخفی شود.
- خروجی محاسبات شامل Definition Revision و Source IDs و Data Freshness باشد.
- بررسی خطاهای قابل Retry و غیرقابل Retry از هم جدا باشد.
