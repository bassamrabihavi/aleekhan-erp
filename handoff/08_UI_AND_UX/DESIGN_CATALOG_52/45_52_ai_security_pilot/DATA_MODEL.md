# مدل داده اولیه صفحات ۴۵ تا ۵۲

دامنه هر داده جداست، جدول‌های اصلی نسخه‌دار، Validation/Permission در Backend و Event/Audit مجزا هستند.

## صفحه 45 — دستیار هوشمند سازمانی
مالک: **AI Gateway**

Entities: AIConversation, AIRequest, AIToolCall, AIRecommendation, AISourceReference, ModelUsage, AIProviderHealth

| کلید | برچسب | نوع | اجباری |
|---|---|---|---|
| `conversation_id` | گفتگو | UUID | بله |
| `user_id` | کاربر | UserRef | بله |
| `scope` | دامنه مجاز داده | PermissionScope | بله |
| `question` | سؤال فارسی | UnicodeText | بله |
| `source_refs` | استناد داده و Revision | List[SourceRef] | بله |
| `response_confidence` | اطمینان پاسخ | Confidence | خیر |
| `action_proposal_id` | پیشنهاد اقدام | ActionProposalRef | خیر |

## صفحه 46 — مدیریت کاربران، نقش‌ها و امنیت
مالک: **مدیریت سیستم**

Entities: User, Role, Permission, Scope, Session, TemporaryAccess, EmergencyAccess, AccessAudit

| کلید | برچسب | نوع | اجباری |
|---|---|---|---|
| `user_id` | کاربر | UUID | بله |
| `role_id` | نقش | RoleRef | بله |
| `scope_id` | دامنه | ScopeRef | بله |
| `permission_id` | عملیات | PermissionRef | بله |
| `access_valid_to` | پایان اعتبار | Timestamp | خیر |
| `security_event` | رخداد امنیتی | EventType | خیر |
| `approval_id` | تأیید دسترسی | ApprovalRef | خیر |

## صفحه 47 — داده‌های پایه و موتور قوانین
مالک: **داده‌های پایه / Admin پیکربندی**

Entities: MasterData, RuleDefinition, RuleRevision, RuleScope, RuleSimulation, RuleApproval

| کلید | برچسب | نوع | اجباری |
|---|---|---|---|
| `rule_id` | قانون | UUID | بله |
| `rule_group` | خانواده قانون | Enum | بله |
| `scope` | دامنه | HierarchyScope | بله |
| `formula` | فرمول کنترل‌شده | AST/Expression | بله |
| `effective_at` | تاریخ اثر | Timestamp | بله |
| `impact_report` | گزارش اثر روی سریال‌ها | Reference | خیر |
| `status` | پیش‌نویس/فعال | Enum | بله |

## صفحه 48 — تابلوی زنده عملکرد سالن تولید
مالک: **تولید**

Entities: PublicProductionProjection, Shift, LineInstance, TargetRevision, ProductionOutput, Alert

| کلید | برچسب | نوع | اجباری |
|---|---|---|---|
| `line_instance_id` | خط | LineRef | بله |
| `business_date` | روز کاری | Date | بله |
| `shift_id` | شیفت | ShiftRef | بله |
| `swu_target` | هدف | Decimal | بله |
| `swu_actual` | خروجی واقعی | Decimal | بله |
| `achievement_rate` | درصد تحقق | Decimal | بله |
| `operational_alerts` | هشدارها | List[Alert] | خیر |

## صفحه 49 — موجودی، شمارش دوره‌ای و مرجوعی مواد
مالک: **مواد و انبار**

Entities: StockSnapshot, WarehouseLocation, MaterialLot, LeatherRoll, LeatherRemnant, CycleCount, MaterialReturn, QualityHold

| کلید | برچسب | نوع | اجباری |
|---|---|---|---|
| `material_id` | ماده | MaterialRef | بله |
| `lot_id` | Lot / Roll | LotRef | بله |
| `location_id` | Rack / Bin | LocationRef | بله |
| `on_hand_qty` | موجودی | Decimal+UOM | بله |
| `reserved_qty` | رزرو | Decimal+UOM | بله |
| `usable_footage` | سطح قابل استفاده چرم | Decimal+ft2 | خیر |
| `expiration` | انقضا | Date | خیر |
| `quality_grade` | گرید Lot | QualityGradeRef | خیر |

## صفحه 50 — عدم انطباق، CAPA و مجوز انحراف
مالک: **تضمین کیفیت QA**

Entities: NCR, NCRDefect, DefectMaster, RootCause, CAPA, CAPAEffectiveness, DeviationPermit, QualityStandardRevision

| کلید | برچسب | نوع | اجباری |
|---|---|---|---|
| `ncr_id` | پرونده عدم انطباق | UUID | بله |
| `serial_or_batch` | سریال/بچ | EntityRef | بله |
| `required_grade` | گرید موردنیاز | QualityGradeRef | بله |
| `defect_id` | نوع عیب | DefectRef | بله |
| `severity` | بحرانی/اساسی/جزئی | Enum | بله |
| `inspection_measure` | اندازه‌گیری | Decimal+UOM | خیر |
| `cause` | علت | Text | خیر |
| `deviation_qty` | مقدار مشمول مجوز انحراف | Decimal | خیر |

## صفحه 51 — نگهداری ماشین‌ها و کالیبراسیون
مالک: **نگهداری و تعمیرات**

Entities: Machine, MaintenanceOrder, MaintenanceSchedule, MachineDowntime, CalibrationRecord, SparePartRequirement

| کلید | برچسب | نوع | اجباری |
|---|---|---|---|
| `machine_id` | ماشین | MachineRef | بله |
| `maintenance_type` | نوع تعمیر | Enum | بله |
| `reported_at` | زمان اعلام خرابی | Timestamp | بله |
| `estimated_recovery` | پیش‌بینی بازگشت | Timestamp | خیر |
| `actual_recovery` | بازگشت واقعی | Timestamp | خیر |
| `capacity_impact` | اثر ظرفیت | ResourceCalendarDelta | خیر |
| `instrument_calibration_until` | اعتبار کالیبراسیون | Date | خیر |

## صفحه 52 — مدیریت پایلوت، خطاها و انتشار نسخه
مالک: **مدیریت سیستم / دفتر پروژه**

Entities: PilotPlan, PilotScenario, DefectTicket, ReproductionStep, RegressionTest, ReleaseCandidate, Signoff, RollbackPlan

| کلید | برچسب | نوع | اجباری |
|---|---|---|---|
| `pilot_id` | شناسه پایلوت | UUID | بله |
| `defect_id` | شناسه باگ | UUID | خیر |
| `severity` | شدت | Enum | بله |
| `repro_steps` | مراحل بازتولید | Text | خیر |
| `test_case_id` | سناریوی تست | TestRef | خیر |
| `owner_signoff` | تأیید واحد مالک | ApprovalRef | خیر |
| `release_version` | نسخه نامزد | SemVer | خیر |
| `rollback_plan_id` | طرح بازگشت | PlanRef | بله |


**لازم برای نسخه نهایی:** PK/FK و Index و Unique و Check Constraint و تاریخ اعتبار، Authority Matrix و API Owner جداگانه باید پس از تطبیق منبع داده دقیق‌تر شوند.
