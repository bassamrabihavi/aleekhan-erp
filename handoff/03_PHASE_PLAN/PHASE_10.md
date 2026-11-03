# PHASE_10 — Cost, HR & BI

**عنوان فارسی:** بهای تمام‌شده، منابع انسانی و داشبورد
**وضعیت:** NOT STARTED / کار Codex/Claude Code؛ فقط با فرمان رسمی مجاز به شروع.
**وابستگی‌ها:** PHASE_04, PHASE_05, PHASE_07, PHASE_09
**صفحات در محدوده (نسخه DRAFT):** 34, 35, 37, 38

## مرز فاز، دامنه DB و داده
CostRateRevision, MaterialCostSnapshot, PayrollConfidential, StandardCost, ActualCost, Skill, SWU, MetricDefinition. داده جدید با Source Provenance و Commit/Migration/Backward compatibility ثبت شود.

## Backend، API، موتور و UI اختصاصی
Pricing/variance, HR skills/payroll restricted views, management KPI with drilldown and data freshness.

## موتور کسب‌وکار/پردازش و قوانین
Cost time/material machine separation, versioned rates, SWU approved scale, no employee pay exposure. هر قانون مستند دارای Golden Test و مالک تصمیم باشد؛ موارد نامعلوم باید Block شود.

## توالی اجرایی اجباری (هر گام گزارش جدا)
- **10.1 — Discovery & Contract:** تعارض‌ها، جدول داده، state transitions، OpenAPI draft، mock/UI binding و خطرات را ثبت کن؛ برای P0 تصمیم بگیر، هنوز داده واقعی mutate نکن.
- **10.2 — Database:** نسخه Migration، PK/FK/unique/check/index، audit, outbox، rollback و seed غیرحساس؛ تست migrate-up/down و schema diff.
- **10.3 — Domain Engine:** منطق محاسبه/State/Conflict/Idempotency و Error Codes؛ unit/property/golden tests قبل از UI.
- **10.4 — Backend/API:** permission scoped + rate limit + ETag/version + pagination + request-id + OpenAPI و test واقعی.
- **10.5 — UI:** صفحات مربوط، Farsi RTL responsive، state loading/error/empty/stale، keyboard, screenshots چهار سایز و تست E2E.
- **10.6 — Integration:** فقط Source/Events مربوط؛ staging, retries, backoff, compensation, freshness and conflict queue؛ بدون تغییر مستقیم ماژول دیگر.
- **10.7 — Security & Ops:** secret scan, dependency scan, privacy/permissions tests, perf, backup/rollback & job monitoring؛ security checklist امضا شود.
- **10.8 — Report & Review:** Template گزارش، git commit hash، migrations، نتایج Test، UI snapshots، Trace Map و مشکلات؛ **STOP** و انتظار PASS/REWORK/BLOCKED.

## الزامات عرضی اجباری
- DB: migration + FK/check/index + audit/outbox + rollback.
- API: OpenAPI & schema compatibility + idempotency + auth + errors.
- UI: RTL desktop/laptop/tablet/mobile, a11y, role-sensitive, real screenshots.
- ENGINE: deterministic contract + sample & golden tests + traceability.
- SEC: RBAC/ABAC, threat analysis, redaction, secure logs, scan.
- QA: unit/integration/E2E/race/property/migration/security + independent evidence.

## Gate پذیرش
داشبورد قابل ردیابی به Ledger؛ پیش‌فرض SWU غیرمصوب مردود؛ salary RBAC/ABAC؛ source-to-number reproducibility.
شرط عمومی: هیچ Critical/P0 شناخته‌شده باز، هیچ تست اجباری Fail/Skipped بی‌دلیل، Migration برگشت‌پذیر یا دارای طرح جبران مصوب، Permission Matrix مصوب، گزارش CI با Commit مرتبط، UI واقعی غیرنمایشی، تمام Scope این فاز traceable؛ پذیرش کارفرما و ممیز.

## محدوده ممنوع
اجرای فاز وابسته قبل از تأیید گیت، استفاده از Mock به‌عنوان واقعیت ERP، ساخت داده فرضی بی‌برچسب، Auto-approve، شکستن قرارداد API و تغییر مستقیم منابع Legacy.

## خروجی‌های اجباری برای گزارش
`CHANGELOG`, migration IDs, updated ERD/OpenAPI, diff, tests.xml/logs, security artifacts, UI screenshots, recorded conflicts, evidence links, signed checklist, new decisions, rollback instructions.
