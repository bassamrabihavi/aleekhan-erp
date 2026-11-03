# Data Model پیشنهادی صفحات ۳۷–۴۴

مدل عملیاتی پیشنهادی؛ هیچ Migration اجرا نشده است. هر Domain مالک Write است.

## صفحه 37: عملکرد کارکنان و خطوط
**مالک:** منابع انسانی و عملکرد

**Entities:** Employee, EmployeeSkill, Shift, Attendance, EmployeeTarget, TargetRevision, OperationExecution, EmployeePerformancePeriod, SWUMetricRevision

| ستون/مرجع | معنی | نوع | الزامی |
|---|---|---|---|
| `employee_id` | رابطه کارمند | EmployeeRef | بله |
| `shift_id` | شیفت | ShiftRef | بله |
| `period_from/to` | بازه گزارش | DateRange | بله |
| `original_swu_target` | هدف اولیه | Decimal | بله |
| `adjusted_swu_target` | هدف اصلاح‌شده | Decimal | بله |
| `earned_standard_minutes` | دقایق استاندارد کسب‌شده | Decimal | بله |
| `productive_minutes` | زمان مولد | Decimal | بله |
| `excluded_downtime_minutes` | توقف خارج از کنترل | Decimal | خیر/شرطی |
| `quality_acceptance_rate` | نرخ قبولی کیفیت | Decimal | بله |
| `target_revision_reason` | دلیل تغییر هدف | Enum+Text | خیر/شرطی |

## صفحه 38: مهارت‌ها، آموزش و درخواست تغییر حقوق
**مالک:** منابع انسانی

**Entities:** Employee, Skill, EmployeeSkill, Certification, TrainingRecord, SalaryHistory, SalaryChangeRequest, SalaryRecommendation, SalaryApproval

| ستون/مرجع | معنی | نوع | الزامی |
|---|---|---|---|
| `employee_id` | کارمند | EmployeeRef | بله |
| `skill_id` | نوع مهارت | SkillRef | بله |
| `skill_level` | سطح مهارت ۱ تا ۵ | SmallInt | بله |
| `valid_until` | اعتبار گواهی | Date | خیر/شرطی |
| `training_record_id` | آموزش | TrainingRef | خیر/شرطی |
| `salary_current` | حقوق فعلی | ConfidentialMoney | خیر/شرطی |
| `effective_from` | تاریخ اثر تغییر حقوق | Date | بله |
| `change_reason` | دلیل تغییر | Text | بله |
| `approver_id` | تأییدکننده | EmployeeRef | بله |

## صفحه 39: صندوق کارها و تأییدهای سازمانی
**مالک:** گردش کار و همکاری سازمانی

**Entities:** Task, TaskAssignment, TaskDependency, Approval, TaskSLA, TaskComment, Referral, Meeting, WorkflowDefinition

| ستون/مرجع | معنی | نوع | الزامی |
|---|---|---|---|
| `task_id` | شناسه تسک | UUID | بله |
| `subject` | موضوع | Text | بله |
| `entity_type/id` | موجودیت مرتبط | EntityReference | بله |
| `owner_user_or_unit` | مسئول فرد/واحد | AssignableRef | بله |
| `due_at` | سررسید | DateTime | بله |
| `status` | وضعیت | Enum | بله |
| `blocked_by_task` | وابستگی مانع | TaskRef | خیر/شرطی |
| `reason` | دلیل انسداد/ارجاع | Text | خیر/شرطی |
| `approval_requirement` | نوع تأیید | WorkflowRule | بله |

## صفحه 40: مدیریت اسناد فنی و نسخه‌ها
**مالک:** سرویس اسناد و رسانه

**Entities:** Document, DocumentRevision, FileMetadata, FileHash, DocumentRelationship, CheckOutLock, Approval

| ستون/مرجع | معنی | نوع | الزامی |
|---|---|---|---|
| `document_id` | شناسه سند | UUID | بله |
| `entity_scope` | متعلق به محصول/استایل/سریال | EntityReference | بله |
| `document_type` | نوع سند | Enum | بله |
| `revision` | نسخه | RevisionId | بله |
| `status` | وضعیت تأیید | Enum | بله |
| `unc_path` | مسیر UNC | Path | بله |
| `sha256` | هش فایل | SHA256 | بله |
| `parent_revision` | والد نسخه | RevisionRef | خیر/شرطی |
| `approved_by` | تایید کننده | UserRef | خیر/شرطی |

## صفحه 41: مرکز استانداردسازی و کیفیت داده
**مالک:** حاکمیت داده / Steward تخصصی

**Entities:** CanonicalTerm, MaterialAlias, OperationAlias, NormalizationSuggestion, DataQualityIssue, DoNotMergePair, MasterRevision

| ستون/مرجع | معنی | نوع | الزامی |
|---|---|---|---|
| `raw_value` | متن خام | UnicodeText | بله |
| `normalized_value` | نسخه نوشتاری | UnicodeText | بله |
| `canonical_id` | هویت Master پیشنهادی | MasterRef | خیر/شرطی |
| `reference_code` | کد راهکاران | Code14OrMaterialCode | خیر/شرطی |
| `confidence` | اطمینان پیشنهاد | EnumOrDecimal | خیر/شرطی |
| `context` | خانواده ماده/نقش مصرف | JSONSchema | خیر/شرطی |
| `decision` | تصمیم Steward | Enum | خیر/شرطی |
| `reason` | دلیل تصمیم | Text | خیر/شرطی |

## صفحه 42: مدیریت پارامترها و چیدمان صفحات
**مالک:** مدیریت سیستم / حاکمیت پیکربندی

**Entities:** ParameterDefinition, ParameterAssignment, TypedParameterValue, UIZone, LayoutRevision, ValidationRule, FieldAccessPolicy

| ستون/مرجع | معنی | نوع | الزامی |
|---|---|---|---|
| `system_key` | کلید فنی ثابت | Slug | بله |
| `label_fa` | برچسب فارسی | UnicodeText | بله |
| `entity_scope` | دامنه موجودیت | EntityEnum | بله |
| `datatype` | نوع داده | Enum | بله |
| `zone` | مکان فرم | UIZoneRef | بله |
| `display_order` | ترتیب نمایش | Int | بله |
| `required_if` | شرط اجباری | RuleExpression | خیر/شرطی |
| `effective_from` | تاریخ اعتبار | Date | بله |
| `security_class` | طبقه محرمانگی | Enum | بله |
| `searchable` | قابل جستجو | Boolean | بله |

## صفحه 43: مرکز ورود فایل‌های راهکاران
**مالک:** یکپارچه‌سازی داده‌ها

**Entities:** ImportProfile, ImportBatch, SourceFile, RawExcelCell, StagingRow, HeaderMapping, ValidationFinding

| ستون/مرجع | معنی | نوع | الزامی |
|---|---|---|---|
| `profile_id` | پروفایل ورود | ImportProfileRef | بله |
| `source_file_id` | شناسه فایل | UUID | بله |
| `file_sha256` | Hash فایل | SHA256 | بله |
| `source_snapshot_at` | زمان Snapshot ERP | Timestamp | بله |
| `sheet_name` | شیت منبع | UnicodeText | بله |
| `cell_address` | نشانی سلول | ExcelAddress | بله |
| `raw_value` | مقدار خام | RawText | خیر/شرطی |
| `mapped_value` | مقدار مقصد | Typed | خیر/شرطی |
| `validation_status` | وضعیت بررسی | Enum | بله |

## صفحه 44: مرکز مغایرت و تطبیق اطلاعات
**مالک:** یکپارچه‌سازی داده‌ها / امضای مالک واحد

**Entities:** ReconciliationBatch, ReconciliationFinding, ControlTotal, SourceSnapshot, Resolution, OwnerSignoff

| ستون/مرجع | معنی | نوع | الزامی |
|---|---|---|---|
| `finding_id` | کد مغایرت | UUID | بله |
| `entity_reference` | موجودیت مرتبط | EntityReference | بله |
| `erp_snapshot_id` | شناسه Snapshot رسمی | SourceRef | بله |
| `operational_value` | مقدار عملیاتی | Typed | خیر/شرطی |
| `erp_value` | مقدار رسمی ERP | Typed | خیر/شرطی |
| `uom` | واحد | UOM | خیر/شرطی |
| `difference` | مقدار اختلاف | Decimal | خیر/شرطی |
| `resolution_type` | نوع اصلاح | Enum | خیر/شرطی |
| `evidence_doc_id` | مدرک | DocumentRef | خیر/شرطی |
| `owner_signoff` | تأیید مسئول | ApprovalRef | خیر/شرطی |


### اصول مشترک دیتابیس
- BIGINT/UUID داخلی در برابر کلیدهای تجاری، کدهای ۱۴رقمی با نوع String برای حفظ صفرهای اول.
- PostgreSQL یا SQL Server؛ Decimal برای تعداد و پول، Decimal با دقت واحد، هرگز Float پول.
- Master Data نسخه‌دار + Raw Input + Canonical Reference + immutable Audit Events.
- نوشتن فقط از طریق مالک Domain. Dynamic Parameter تایپ‌دار، SystemKey ثابت و تاریخ اعتبار.
- Salary history با Field-level security و audit مشاهده حساس.
- Document path به صورت UNC + SHA-256، Approved Revision تغییرناپذیر.
- Import Raw Cell/Staging و تشخیص Idempotency؛ هرگز Merge پنهان و حذف Raw.
