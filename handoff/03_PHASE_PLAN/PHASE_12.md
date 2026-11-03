# PHASE_12 — Migration & Integration Dress Rehearsal

**عنوان فارسی:** مهاجرت و آزمون سرتاسری روی داده امن
**وضعیت:** NOT STARTED / کار Codex/Claude Code؛ فقط با فرمان رسمی مجاز به شروع.
**وابستگی‌ها:** PHASE_01, PHASE_02, PHASE_03, PHASE_04, PHASE_05, PHASE_06, PHASE_07, PHASE_08, PHASE_09, PHASE_10, PHASE_11
**صفحات در محدوده (نسخه DRAFT):** 40, 43, 44

## مرز فاز، دامنه DB و داده
ImportBatches, MappingVersions, Reconciliation, SourceFile chain, AnonymizedPilotFixture, BackupRestore snapshots. داده جدید با Source Provenance و Commit/Migration/Backward compatibility ثبت شود.

## Backend، API، موتور و UI اختصاصی
CSV/XLSM read-only import -> staging -> reviewed commits, error dashboard, mapping UI and reconciliation reports.

## موتور کسب‌وکار/پردازش و قوانین
Preserve exact source hash and raw cells/formulas; repeat-import idempotent; account for missing dimensions; independent batch audit. هر قانون مستند دارای Golden Test و مالک تصمیم باشد؛ موارد نامعلوم باید Block شود.

## توالی اجرایی اجباری (هر گام گزارش جدا)
- **12.1 — Discovery & Contract:** تعارض‌ها، جدول داده، state transitions، OpenAPI draft، mock/UI binding و خطرات را ثبت کن؛ برای P0 تصمیم بگیر، هنوز داده واقعی mutate نکن.
- **12.2 — Database:** نسخه Migration، PK/FK/unique/check/index، audit, outbox، rollback و seed غیرحساس؛ تست migrate-up/down و schema diff.
- **12.3 — Domain Engine:** منطق محاسبه/State/Conflict/Idempotency و Error Codes؛ unit/property/golden tests قبل از UI.
- **12.4 — Backend/API:** permission scoped + rate limit + ETag/version + pagination + request-id + OpenAPI و test واقعی.
- **12.5 — UI:** صفحات مربوط، Farsi RTL responsive، state loading/error/empty/stale، keyboard, screenshots چهار سایز و تست E2E.
- **12.6 — Integration:** فقط Source/Events مربوط؛ staging, retries, backoff, compensation, freshness and conflict queue؛ بدون تغییر مستقیم ماژول دیگر.
- **12.7 — Security & Ops:** secret scan, dependency scan, privacy/permissions tests, perf, backup/rollback & job monitoring؛ security checklist امضا شود.
- **12.8 — Report & Review:** Template گزارش، git commit hash، migrations، نتایج Test، UI snapshots، Trace Map و مشکلات؛ **STOP** و انتظار PASS/REWORK/BLOCKED.

## الزامات عرضی اجباری
- DB: migration + FK/check/index + audit/outbox + rollback.
- API: OpenAPI & schema compatibility + idempotency + auth + errors.
- UI: RTL desktop/laptop/tablet/mobile, a11y, role-sensitive, real screenshots.
- ENGINE: deterministic contract + sample & golden tests + traceability.
- SEC: RBAC/ABAC, threat analysis, redaction, secure logs, scan.
- QA: unit/integration/E2E/race/property/migration/security + independent evidence.

## Gate پذیرش
هیچ حذف تاریخچه؛ reconciliation counts by owner approved؛ restore tested; e2e serial to shipment; security/performance checks complete.
شرط عمومی: هیچ Critical/P0 شناخته‌شده باز، هیچ تست اجباری Fail/Skipped بی‌دلیل، Migration برگشت‌پذیر یا دارای طرح جبران مصوب، Permission Matrix مصوب، گزارش CI با Commit مرتبط، UI واقعی غیرنمایشی، تمام Scope این فاز traceable؛ پذیرش کارفرما و ممیز.

## محدوده ممنوع
اجرای فاز وابسته قبل از تأیید گیت، استفاده از Mock به‌عنوان واقعیت ERP، ساخت داده فرضی بی‌برچسب، Auto-approve، شکستن قرارداد API و تغییر مستقیم منابع Legacy.

## خروجی‌های اجباری برای گزارش
`CHANGELOG`, migration IDs, updated ERD/OpenAPI, diff, tests.xml/logs, security artifacts, UI screenshots, recorded conflicts, evidence links, signed checklist, new decisions, rollback instructions.
