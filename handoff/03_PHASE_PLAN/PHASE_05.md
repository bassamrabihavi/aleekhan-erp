# PHASE_05 — Planning & Finite Capacity

**عنوان فارسی:** تقاضا، تعهد، سناریوی ظرفیت و زمان‌بندی
**وضعیت:** NOT STARTED / کار Codex/Claude Code؛ فقط با فرمان رسمی مجاز به شروع.
**وابستگی‌ها:** PHASE_02, PHASE_04
**صفحات در محدوده (نسخه DRAFT):** 3, 30, 31, 32, 33, 51

## مرز فاز، دامنه DB و داده
Season/Month/Week program, Demand, Forecast, Commit, Shift, Skill, Machine, Calendar, CapacityScenario, ScheduleVersion. داده جدید با Source Provenance و Commit/Migration/Backward compatibility ثبت شود.

## Backend، API، موتور و UI اختصاصی
Scenario solver API/worker, Gantt UI, resource reassignment approvals, warning unknown standards, downtime/capacity read model.

## موتور کسب‌وکار/پردازش و قوانین
Forecast dedup, finite resource constraints, OR-Tools timeouts, FastTrack anti-starvation, donor loss, schedule repair. هر قانون مستند دارای Golden Test و مالک تصمیم باشد؛ موارد نامعلوم باید Block شود.

## توالی اجرایی اجباری (هر گام گزارش جدا)
- **05.1 — Discovery & Contract:** تعارض‌ها، جدول داده، state transitions، OpenAPI draft، mock/UI binding و خطرات را ثبت کن؛ برای P0 تصمیم بگیر، هنوز داده واقعی mutate نکن.
- **05.2 — Database:** نسخه Migration، PK/FK/unique/check/index، audit, outbox، rollback و seed غیرحساس؛ تست migrate-up/down و schema diff.
- **05.3 — Domain Engine:** منطق محاسبه/State/Conflict/Idempotency و Error Codes؛ unit/property/golden tests قبل از UI.
- **05.4 — Backend/API:** permission scoped + rate limit + ETag/version + pagination + request-id + OpenAPI و test واقعی.
- **05.5 — UI:** صفحات مربوط، Farsi RTL responsive، state loading/error/empty/stale، keyboard, screenshots چهار سایز و تست E2E.
- **05.6 — Integration:** فقط Source/Events مربوط؛ staging, retries, backoff, compensation, freshness and conflict queue؛ بدون تغییر مستقیم ماژول دیگر.
- **05.7 — Security & Ops:** secret scan, dependency scan, privacy/permissions tests, perf, backup/rollback & job monitoring؛ security checklist امضا شود.
- **05.8 — Report & Review:** Template گزارش، git commit hash، migrations، نتایج Test، UI snapshots، Trace Map و مشکلات؛ **STOP** و انتظار PASS/REWORK/BLOCKED.

## الزامات عرضی اجباری
- DB: migration + FK/check/index + audit/outbox + rollback.
- API: OpenAPI & schema compatibility + idempotency + auth + errors.
- UI: RTL desktop/laptop/tablet/mobile, a11y, role-sensitive, real screenshots.
- ENGINE: deterministic contract + sample & golden tests + traceability.
- SEC: RBAC/ABAC, threat analysis, redaction, secure logs, scan.
- QA: unit/integration/E2E/race/property/migration/security + independent evidence.

## Gate پذیرش
تداخل نفر/ماشین صفر؛ خروجی WHAT_IF از Commit جدا؛ اثر انتقال منابع هر دو خط؛ timeout/cancel scenario امن؛ داده غیرمصوب تعهد قطعی نمی‌سازد.
شرط عمومی: هیچ Critical/P0 شناخته‌شده باز، هیچ تست اجباری Fail/Skipped بی‌دلیل، Migration برگشت‌پذیر یا دارای طرح جبران مصوب، Permission Matrix مصوب، گزارش CI با Commit مرتبط، UI واقعی غیرنمایشی، تمام Scope این فاز traceable؛ پذیرش کارفرما و ممیز.

## محدوده ممنوع
اجرای فاز وابسته قبل از تأیید گیت، استفاده از Mock به‌عنوان واقعیت ERP، ساخت داده فرضی بی‌برچسب، Auto-approve، شکستن قرارداد API و تغییر مستقیم منابع Legacy.

## خروجی‌های اجباری برای گزارش
`CHANGELOG`, migration IDs, updated ERD/OpenAPI, diff, tests.xml/logs, security artifacts, UI screenshots, recorded conflicts, evidence links, signed checklist, new decisions, rollback instructions.
