# مدل داده مقدماتی — صفحات ۲۹ تا ۳۶

> طراحی قابل بازبینی؛ جداول فیزیکی هنوز ERD نهایی/مهاجرت اجرای واقعی نیستند.

| محدوده | موجودیت‌ها | یکپارچگی داده |
|---|---|---|
| سفارش و کدگذاری | CustomerOrderHeader, CustomerOrderLine, Serial, Product, Style, ExternalReference, ProductCodingRuleVersion | یک ردیف سفارش تولید → یک سریال، کد ۱۴رقمی رشته‌ای و یکتا در Scope معتبر |
| برنامه فصل/ماه/هفته | OrderProgram, ProgramPeriod, ProgramMembership, DemandForecast, ForecastConsumption | Forecast مصرف‌شده دوباره به تقاضا اضافه نشود؛ نسخه‌ها و Snapshots محفوظ |
| زمان‌بندی | Schedule, ScheduleVersion, OperationAllocation, CommitmentHistory, FastTrack | OPC معتبر، عدم Double-Booking، Freeze Zone و Operation Effectivity |
| ظرفیت و سناریو | ResourcePool, EmployeeSkill, Attendance, MachineCalendar, CapacityScenario, ScenarioResult | ظرفیت خط جدید از منابع موجود ایجاد می‌شود نه از نام خط |
| تغییرات | OrderChangeRequest, ECR, ECO, ChangeImpact, WIPDisposition, SerialRevisionEffectivity | Snapshot قدیمی/جدید؛ عدم ویرایش مستقیم برنامه/بچ‌های تکمیل‌شده |
| هزینه و قیمت | CostingSnapshot, CostLine, MaterialPriceVersion, LaborRateVersion, QuoteRevision | Quote صادرشده Immutable؛ همه مقادیر Decimal و ارزی مشخص |
| BI | MetricDefinition, FactProduction, FactQuality, FactCost, DataLineage | یک فرمول رسمی Versioned؛ منشأ، Freshness و سطح دسترسی |
| Admin | SystemJob, JobCheckpoint, JobIncident, AuditEvent, HealthMetric, SystemAlert | توقف اجباری باعث RecoveryRequired؛ Audit Append-only |

## شناسه‌های کد
ساختار نمونه مشاهده‌شده در فایل Planning: `02` (ماهیت) + نوع محصول ۲ رقم + دسته ۲ رقم + کد محصول ۴ رقم + استایل ۴ رقم = ۱۴ رقم. کد با صفر پیشرو به‌صورت TEXT/CHAR(14) ذخیره شود نه عدد اعشاری؛ قواعد سایر دسته‌بندی‌ها و کد تیغه مستقلاً از فایل‌های اصلی تأیید شوند.

## دقت و تاریخ
تعداد، مصرف، پول: Decimal. زمان ثبت/رخداد: UTC و زمان کاری Shift مستقل؛ نمایش تاریخ شمسی. اطلاعات تاریخی Original + Normalized + Source + ImportBatch + VerificationState.

## Dynamic Parameter
EntityParameterDefinition / Assignment / TypedValue / LayoutZone / Version؛ پارامتر اختصاصی نباید Primary Key و فیلدهای Business Critical را جایگزین کند.
