# ADR-001 — فناوری مرجع (DESIGN DECISION / Requires Gate-0 approval)

**انتخاب پیشنهادی ثابت برای آغاز طراحی فنی:** Backend: Python 3.12+ / Django 5.2 LTS / Django REST Framework؛ UI: TypeScript strict / React / Vite / React Router / TanStack Query + جدول‌های دسترس‌پذیر؛ DB: PostgreSQL 17 با driver رسمی مناسب؛ Worker: Celery + Redis؛ Files: Object Storage خصوصی با SHA-256 + URI ذخیره‌شده در DB؛ CAD: Python `ezdxf` در محیط Sandbox، عامل Windows اختیاری برای AutoCAD؛ Solver: OR-Tools فقط برای تصمیم‌های ظرفیت محدود، با fallback و timeout مشخص؛ Observability: OpenTelemetry-compatible logs/traces/metrics. API: JSON over HTTPS, OpenAPI 3.1، قرارداد نسخه‌دار.

**علت انتخاب:** دامنه صنعتی دارای روابط و تراکنش‌های متعدد، Excel/DXF/Python و نیاز به امنیت سازمانی است؛ Django برای مدیریت داده/نقش/ORM/transaction، React برای UI پیچیده و PostgreSQL برای قیود داده و لاگ مناسب است. Microservice عمومی و دو Backend هم‌زمان در فاز اول ممنوع: **Modular Monolith** با مرز روشن Module، Event/Outbox و Worker مستقل.

**مقایسه جایگزین‌ها:** FastAPI + SQLAlchemy برای سرویس‌های مهندسی/محاسباتی مناسب است ولی اگر به‌عنوان Backend کل محصول استفاده شود، Authorization، Workflow و Admin باید با دقت بیشتر ساخته شود. .NET/SQL Server به اتوماسیون ویندوزی نزدیک است ولی در DXF/اصلاح Pythonهای موجود نیاز به Bridge دارد. تصمیم نهایی Framework در فاز ۰ با Prototype امنیت/Transactions/ORM/Integration گرفته و `ADR` امضا شود؛ کد آزمایشی FastAPI گذشته **مرجع قطعی نیست**.

**مبنا و نسخه‌گذاری:** Django 5.2 تا آوریل ۲۰۲۸ Extended Support دارد (https://www.djangoproject.com/download/). PostgreSQL 17 تا نوامبر ۲۰۲۹ پشتیبانی می‌شود (https://www.postgresql.org/support/versioning/). نسخه Minor و Node/React/TypeScript در Gate-0 به نسخه‌های Patch پشتیبانی‌شده PIN شوند؛ CI باید Software Bill of Materials و اسکن وابستگی را نگهداری کند. نسخه جدید بدون آزمون سازگاری خودکار پذیرفته نشود.

**استقرار:** وب داخلی از طریق HTTPS/Reverse Proxy، Backend/Worker/PostgreSQL/Redis/Object Store در شبکه خصوصی یا سرور مورد تأیید شرکت؛ محیط‌های dev/test/staging/prod جدا؛ Database بدون اتصال مستقیم اینترنت، پشتیبان رمزنگاری‌شده خارج از سرور اصلی، مشاهده Log، محدودسازی دسترسی فایلی و سرویس. اتصال راهکاران فاز اول **Excel import/read-only** و با تأیید اداری است؛ هر Write-back به راهکاران نیاز به ADR و مجوز مستقل دارد.

**زمان و زبان:** DB timestamp در UTC؛ نمایش Jalali با منطقه `Asia/Tehran` و تقویم اختصاصی؛ UI فارسی RTL؛ ذخیره تاریخ شمسی به‌صورت String حقیقت اصلی نباشد. کد ۱۴رقمی با `varchar(14)`, constraint regex و namespace نوع کد نگهداری شود.
