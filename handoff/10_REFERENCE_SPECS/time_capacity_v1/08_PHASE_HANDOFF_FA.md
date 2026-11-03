# ۸. تحویل به Codex / Claude Code — فازهای کوتاه و Gateدار

**قانون اصلی:** توسعه‌دهنده هوش مصنوعی کد می‌نویسد؛ ChatGPT اینجا صرفاً Specification و نتیجه را ممیزی می‌کند. هیچ فاز بدون Evidence و تأیید کارفرما بسته نیست.

## Slice TC-0 — تصمیم‌ها و قرارداد (بدون کد تولید)
- نقشه OPC واقعی چهار خانواده با نشانه‌گذاری مراحل تأییدشده/پیشنهادی.
- ERD نسخه‌دار، API Schemas، وضعیت‌ها و مجوزها؛ Units و تبدیل زوج کفش.
- Threat Model و شیوه ثبت زمان/دستگاه؛ تصمیم روی Allowance و SWU.
**Gate:** هیچ مقدار پیش‌فرض استاندارد پنهان وجود ندارد، همه نقاط نامعلوم `OPEN` هستند.

## Slice TC-1 — داده و ثبت مطالعه
**DB:** زمان‌سنجی، مشاهده خام، تصحیح، منابع/شایستگی. **Backend:** API ثبت خام و Audit/Version. **UI:** Tab مطالعه زمان صفحه ۱۶ و فرم سالن صفحه ۲۳. **Engine:** اعتبارسنجی و تبدیل Unit (بدون تعیین زمان مصوب خودکار). **Security:** RBAC/Scope، input/import validation. **Tests:** TC01-04, TC20-23.
**Gate:** امکان بازسازی Raw Observations از Audit؛ تغییر بی‌سابقه مردود.

## Slice TC-2 — استاندارد و انتشار
**DB:** StandardRevision, Scope, Approval. **Backend:** اعتبارسنجی sample/method/rating/allowance, resolve. **Engine:** محاسبه استاندارد نفر/ماشین/Setup/Wait جدا و confidence. **UI:** پیش‌نویس/بررسی/انتشار. **Tests:** TC05-07, TC18-19, TC21.
**Gate:** فقط Standard Approved قابل استفاده در برنامه Commit.

## Slice TC-3 — Calendar, Skill, Resource
**DB:** Resource, Skill, LineInstance, ShiftAssignment, CalendarException, MachineDowntime. **Backend/UI:** برنامه شیفت/صلاحیت/تعمیرات؛ **Engine:** available person/machine minutes، conflicts. **Security:** داده حقوق جدا. **Tests:** TC08-12.
**Gate:** بدون شیفت/Skill/ماشین معتبر، تخصیص قطعی صورت نگیرد.

## Slice TC-4 — Capacity Planner و Solver
**DB:** Scenario/Constraint/Result/Approval. **Backend:** Job Solver، Async, cancel/retry. **Engine:** finite capacity, shared-machine, precedence, setup, stock holds, what-if. **UI:** صفحه ۳۲ و Gantt صفحه ۳۱. **Security:** protected approve/DoS limits. **Tests:** TC08-14, TC19.
**Gate:** خروجی Solver دلایل و Snapshot دارد، اثر انتقال از خط مبدأ قابل مشاهده است.

## Slice TC-5 — Production, KPI, SWU
**DB:** ExecutionEvent, QuantityLedger, Rework, KPI Snapshot. **Backend:** ingest idempotent. **Engine:** SWU, throughput, labor ratio, quality gates. **UI:** صفحات ۲۲، ۲۳، ۲۸، ۳۷، ۴۸. **Tests:** TC15-17, TC22, TC24.
**Gate:** واحدهای چهار خانواده و WIP بدون دوبارشماری.

## Slice TC-6 — E2E و Pilot
- اتصال به Product/Style/Serial/OPC/WH/QC/ERP بدون دسترسی به داده حساس بدون مجوز.
- داده واقعی فقط پس از import controlled staging و مصوبه مسئول واحد. Workload/Performance/Security، Restore Drill، آموزش و Shadow Mode.
**Gate:** QA + Planning + Engineering + Production + IT Security امضا کنند؛ قبل از Pilot هیچ عدد تخمینی به‌عنوان زمان استاندارد قطعی منتشر نشود.

## قالب اجباری گزارش توسعه‌دهنده در انتهای هر Slice
1. Git commit/tag و hash قرارداد مرجع؛ فایل‌هایی که تغییر کرده‌اند.
2. Migration UP/DOWN، مدل داده و دلیل تصمیم فنی.
3. APIهای تکمیل‌شده به‌همراه request/response مصنوعی و OpenAPI diff.
4. UI Screenshots روی 1440/1180/768/390 و Accessibility/RTL review.
5. موتور و فرمول‌ها: version, rounding, units, assumption, input/output.
6. ماتریس مجوز و شواهد تست امنیت.
7. unit/integration/E2E/contract/performance test results با دستور بازتولید.
8. نقص‌ها بر حسب severity و TODOهای باز؛ هیچ «انجام شد» بدون شواهد.
9. تصمیم‌های مبهم که **نیازمند پاسخ کارفرما** هستند؛ بدون حدس.
10. فایل `HANDOFF_REPORT.md` و `KNOWN_GAPS.md` و `REVIEW_RESPONSE.md` برای بازبین.

## فرایند بازبینی
- Codex/Claude Code -> گزارش + تست + commit -> ChatGPT ممیزی منطق/امنیت/UI -> `APPROVED | CHANGES_REQUIRED | BLOCKED` با گزارش ایراد شماره‌دار -> Codex اصلاح و گزارش diff -> تست مجدد -> تأیید صاحب فرایند.
- تأیید من به‌تنهایی جایگزین تأیید رسمی کاربران کارخانه یا ممیزی امنیت متخصص نیست.
