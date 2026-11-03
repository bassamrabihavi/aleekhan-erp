# APIهای پیشنهادی — صفحات ۳۷ تا ۴۴

APIهای نمونه با ریشه `/api/v1`. هنوز پیاده‌سازی نشده‌اند؛ Commandهای حساس به AuthZ، Validations، Audit، RowVersion و IdempotencyKey نیاز دارند.

## 37 — عملکرد کارکنان و خطوط
**Query:** GET /api/v1/منابع/GetEmployeePerformance, GET /api/v1/منابع/GetTargetHistory, GET /api/v1/منابع/GetShiftPerformance

**Command:** POST /api/v1/commands/RequestTargetRevision, POST /api/v1/commands/ApproveTargetRevision, POST /api/v1/commands/SavePerformanceReport

**Event:** EmployeeTargetRevised, OperationEarnedTimePosted

## 38 — مهارت‌ها، آموزش و درخواست تغییر حقوق
**Query:** GET /api/v1/منابع/GetEmployeeSkills, GET /api/v1/منابع/GetSalaryChangeQueue, GET /api/v1/منابع/GetSkillValidity

**Command:** POST /api/v1/commands/RequestSalaryReview, POST /api/v1/commands/SubmitHRReview, POST /api/v1/commands/ApproveSalaryChange, POST /api/v1/commands/UpdateSkillCertificate

**Event:** CertificateExpired, SalaryChangeApproved

## 39 — صندوق کارها و تأییدهای سازمانی
**Query:** GET /api/v1/گردش/ListTaskInbox, GET /api/v1/گردش/GetTaskDependencies, GET /api/v1/گردش/GetPendingApprovals

**Command:** POST /api/v1/commands/CreateTask, POST /api/v1/commands/AssignTask, POST /api/v1/commands/CompleteTask, POST /api/v1/commands/RequestReassignment, POST /api/v1/commands/ApproveTaskClosure

**Event:** TaskAssigned, TaskBlocked, TaskVerified

## 40 — مدیریت اسناد فنی و نسخه‌ها
**Query:** GET /api/v1/سرویس/SearchDocumentRegistry, GET /api/v1/سرویس/GetDocumentRevisions, GET /api/v1/سرویس/ValidateFileHash

**Command:** POST /api/v1/commands/CheckoutDocument, POST /api/v1/commands/CheckinDocument, POST /api/v1/commands/SubmitDocumentReview, POST /api/v1/commands/ApproveRevision

**Event:** DocumentRevisionApproved, ApprovedFileHashMismatch

## 41 — مرکز استانداردسازی و کیفیت داده
**Query:** GET /api/v1/حاکمیت/FindCanonicalCandidates, GET /api/v1/حاکمیت/GetMaterialCodeConflict, GET /api/v1/حاکمیت/ListQualityIssues

**Command:** POST /api/v1/commands/ProposeAlias, POST /api/v1/commands/ResolveDataQualityIssue, POST /api/v1/commands/FlagDoNotMerge, POST /api/v1/commands/RequestMasterCreation

**Event:** AliasApproved, MaterialNameConflictFound

## 42 — مدیریت پارامترها و چیدمان صفحات
**Query:** GET /api/v1/مدیریت/GetParameterCatalog, GET /api/v1/مدیریت/PreviewLayout, GET /api/v1/مدیریت/GetLayoutRevisionDiff

**Command:** POST /api/v1/commands/CreateParameterDraft, POST /api/v1/commands/ReorderLayoutFields, POST /api/v1/commands/ValidateLayout, POST /api/v1/commands/SubmitLayoutApproval, POST /api/v1/commands/PublishLayoutRevision, POST /api/v1/commands/RollbackLayout

**Event:** ParameterDefinitionCreated, UILayoutPublished

## 43 — مرکز ورود فایل‌های راهکاران
**Query:** GET /api/v1/یکپارچه‌سازی/ListImportProfiles, GET /api/v1/یکپارچه‌سازی/GetImportFindings, GET /api/v1/یکپارچه‌سازی/PreviewStagingBatch

**Command:** POST /api/v1/commands/UploadRahkaranExport, POST /api/v1/commands/ValidateImportBatch, POST /api/v1/commands/MapSourceHeader, POST /api/v1/commands/ApproveImportBatch

**Event:** ImportBatchValidated, RahkaranSnapshotReconciled

## 44 — مرکز مغایرت و تطبیق اطلاعات
**Query:** GET /api/v1/یکپارچه‌سازی/GetReconciliationBatch, GET /api/v1/یکپارچه‌سازی/CompareSourceSnapshots, GET /api/v1/یکپارچه‌سازی/GetControlTotals

**Command:** POST /api/v1/commands/CreateReconciliation, POST /api/v1/commands/RecordFindingDecision, POST /api/v1/commands/RequestERPAdjustment, POST /api/v1/commands/SignoffReconciliation

**Event:** ReconciliationFindingResolved, ImportApprovedAfterReconciliation

## قرارداد خطای عمومی
```json
{"code":"PERMISSION_OR_VALIDATION_DENIED","message_fa":"دلیل عدم انجام عملیات به فارسی","entity_id":"...","correlation_id":"...","details":{},"retryable":false}
```
- از UI فقط Intent ثبت می‌شود؛ محاسبه و تصمیم نهایی به API/Workflow منبع وابسته است.
- نمایشگر هرگز منبع حقیقت برای حقوق، موجودی، کد راهکاران، گرید یا KPI نیست.
- قبل از اتصال به Production باید DTO / OpenAPI 3.x و نسخه‌بندی Payload و Contract Test نوشته شود.
