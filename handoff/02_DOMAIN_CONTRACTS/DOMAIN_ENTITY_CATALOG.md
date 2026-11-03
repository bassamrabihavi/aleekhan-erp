# Data Domain Contract — مدل منطقی پیشنهادی (NOT physical DDL)

هر جدول فیزیکی باید در Gate-0 با Type، Key، Foreign Key، Unique/Check، Tenant/Scope، Index، Audit، Retention و Migration مشخص شود. **نام‌های زیر قرارداد منطقی هستند**، نه ادعای موجود بودن DDL نهایی.

| ماژول مالک | موجودیت‌های اصلی | قواعد و Index / Invariant اجباری |
|---|---|---|
| Identity | Customer, Product, Style, ProductCode, Serial, SerialSnapshot, ExternalIdentity | کدهای ۱۴رقمی رشته + namespace؛ Serial یکتا با sequence امن تراکنشی؛ customer external identifiers در domain خود؛ snapshot non-destructive |
| Commercial | Inquiry, QuoteVersion, CustomerPO, CustomerPOLine, OrderChange, CustomerArtworkApproval | PO Header چند line؛ line-to-serial؛ شماره سفارش مشتری خارجی لزوماً یکتا در کل سازمان نیست؛ approval version |
| Engineering | DesignRoute, PatternRevision, DXFArtifact, DieCandidate, DieRegistry, DieRevision, Cliche, ClicheApproval, Jig, SkivingPlan, ProductTechnicalPackage | DXF source hash و engine version؛ Tool physical location متعلق به انبارک؛ release فقط با referential approvals |
| BOM | AssemblyNode, Part, MaterialRole, BOMRevision, BOMItem, ConsumptionRule, WasteRule | material slots به‌صورت rows unbounded؛ unit, color, print, finish, leather grade, revision؛ no silent alias merge |
| OPC/Time | OPCRoute, OperationDefinition, OperationDependency, TimeStudyPlan, RawObservation, StandardTimeRevision, Machine/Person/WaitTime | هر استاندارد version + approval + scope؛ raw observation immutable correction-as-new-event؛ waiting ≠ person occupancy |
| Planning | ProgramSeason/Month/Week, Demand, Forecast, Commit, CapacityScenario, ScheduleRevision, ResourceAllocation, FastTrackQueue | forecast-to-commit dedup؛ per-line instance constraints؛ solver output not autonomous promise; approval of line split |
| Warehouse | MaterialMaster, UOMConversion, SourceInventorySnapshot, Lot, Location, Hold, Reservation, Issue, Receipt, Return, ShortageGAP, StockLedger | official snapshot ≠ available-to-promise؛ lot/hold/location/reserve separated؛ stock invariant per owner; no double counting |
| Supply | PurchaseRequisition, Supplier, PO, ETAHistory, DieFabricationRequest | supply issues promises; Warehouse owns receipt; engineering owns technical identity |
| Production | WorkOrder, WorkBatch, Bundle, StationActivity, OperatorShift, Downtime, Scrap, Rework, QuantityLedger | monotonic batch events, atomic qty moves; no negative; station out cannot exceed in; link to Serial and approved OPC revision |
| Quality | IncomingInspection, QualitySpecVersion, Defect, NCR, CAPA, ProductInspection, QCGrade, DeviationPermit | CustomerRequiredGrade ≠ ActualGrade; QC only controls quality releases; A+/A/B/C policy per customer |
| FG/Dispatch | FGReceipt, FGCount, Pick, Delivery, DeliveryLine, ProofOfDelivery, ReturnAuthorization | partial deliveries; cannot ship hold/unapproved grade; complete serial only with reconciled delivered qty |
| HR/Assets | Employee, SkillCertification, Assignment, Leave, PayrollConfidential, Machine, Maintenance, Calibration | salary field-level access; maintenance reduces resource availability; skill validity versioned |
| Platform | User, Role, Scope, Permission, ApprovalTask, AuditEvent, OutboxEvent, ImportBatch, SourceFile, RawRecord, DataConflict, Job, Notification, DynamicFieldDefinition | actor, request-id, UTC, resource scope, reason; secrets stored externally; idempotency key; safe cancellation |

## کنترل کلیدی identity/code
1. `product_code` and `die_code` each textual 14-character value only **in namespace corresponding to type**, not automatic shared sequence; `cliche_code` historical alphanumeric (e.g. DOR51); `serial_number` separate.
2. ۱۴رقمی بودن با داشتن الگوریتم قطعی یکی نیست: Validate Format از فاز اول، Issue New Code فقط با Golden Tests و rules approved.
3. Serial creation must be race-safe, idempotent, scoped to customer PO line and transaction; duplicated code across different serials allowed.

## رابط انبار — مصرف و رزرو
Ledger events contain type, qty (Decimal), UOM, source/target lot, location, quality hold, owner Serial/Batch, external ref, transaction id, reason. Reservation may reference snapshot but snapshot is read-only external evidence; available quantity must reconcile physical and reserved independently.

## تیم مهندسی — انتشار فنی
Release Package immutable references: PatternRev, BOMRev, OPCRev, Tool compatibility, Skiving rev, Quality Spec, sample approval. Release/withdraw/revise recorded atomically. Change after release uses ECR/ECO impact, never in-place history rewrite.

## محصول خانواده و واحد
کیف/جیبی/کمربند: معمولاً عدد؛ کفش جفت. درباره تک‌لنگه یا نیم‌جفت برای WIP تبدیل واحد باید صریح باشد. زمان‌سنجی نفر-دقیقه/ماشین-دقیقه/انتظار مستقل. UOM conversion no floating binary values for quantity/cost.
