# PHASE_07 — Cutting & Production MES

**عنوان فارسی:** برش، خطوط، بچ، اپراتور و توقف‌ها
**وضعیت:** NOT STARTED / کار Codex/Claude Code؛ فقط با فرمان رسمی مجاز به شروع.
**وابستگی‌ها:** PHASE_03, PHASE_04, PHASE_05, PHASE_06
**صفحات در محدوده (نسخه DRAFT):** 21, 22, 23, 28, 48, 51

## مرز فاز، دامنه DB و داده
WorkBatch, Bundle, StationActivity, CuttingBatch, MaterialIssue, Downtime, Scrap, Rework, OperationCompletionLedger. داده جدید با Source Provenance و Commit/Migration/Backward compatibility ثبت شود.

## Backend، API، موتور و UI اختصاصی
Cutting queue & labels, mobile operator terminal, supervisor shift board, machine downtime feed, station input-output APIs.

## موتور کسب‌وکار/پردازش و قوانین
Atomic WIP quantity ledger, split/merge genealogy, shift calendar/skills, QR integrity, real time with offline conflict strategy. هر قانون مستند دارای Golden Test و مالک تصمیم باشد؛ موارد نامعلوم باید Block شود.

## توالی اجرایی اجباری (هر گام گزارش جدا)
- **07.1 — Discovery & Contract:** تعارض‌ها، جدول داده، state transitions، OpenAPI draft، mock/UI binding و خطرات را ثبت کن؛ برای P0 تصمیم بگیر، هنوز داده واقعی mutate نکن.
- **07.2 — Database:** نسخه Migration، PK/FK/unique/check/index، audit, outbox، rollback و seed غیرحساس؛ تست migrate-up/down و schema diff.
- **07.3 — Domain Engine:** منطق محاسبه/State/Conflict/Idempotency و Error Codes؛ unit/property/golden tests قبل از UI.
- **07.4 — Backend/API:** permission scoped + rate limit + ETag/version + pagination + request-id + OpenAPI و test واقعی.
- **07.5 — UI:** صفحات مربوط، Farsi RTL responsive، state loading/error/empty/stale، keyboard, screenshots چهار سایز و تست E2E.
- **07.6 — Integration:** فقط Source/Events مربوط؛ staging, retries, backoff, compensation, freshness and conflict queue؛ بدون تغییر مستقیم ماژول دیگر.
- **07.7 — Security & Ops:** secret scan, dependency scan, privacy/permissions tests, perf, backup/rollback & job monitoring؛ security checklist امضا شود.
- **07.8 — Report & Review:** Template گزارش، git commit hash، migrations، نتایج Test، UI snapshots، Trace Map و مشکلات؛ **STOP** و انتظار PASS/REWORK/BLOCKED.

## الزامات عرضی اجباری
- DB: migration + FK/check/index + audit/outbox + rollback.
- API: OpenAPI & schema compatibility + idempotency + auth + errors.
- UI: RTL desktop/laptop/tablet/mobile, a11y, role-sensitive, real screenshots.
- ENGINE: deterministic contract + sample & golden tests + traceability.
- SEC: RBAC/ABAC, threat analysis, redaction, secure logs, scan.
- QA: unit/integration/E2E/race/property/migration/security + independent evidence.

## Gate پذیرش
هیچ خروجی بیشتر از ورودی؛ split trace دوخط با مجوز؛ rework no double credit SWU; shift handover/undo audit; offline safe.
شرط عمومی: هیچ Critical/P0 شناخته‌شده باز، هیچ تست اجباری Fail/Skipped بی‌دلیل، Migration برگشت‌پذیر یا دارای طرح جبران مصوب، Permission Matrix مصوب، گزارش CI با Commit مرتبط، UI واقعی غیرنمایشی، تمام Scope این فاز traceable؛ پذیرش کارفرما و ممیز.

## محدوده ممنوع
اجرای فاز وابسته قبل از تأیید گیت، استفاده از Mock به‌عنوان واقعیت ERP، ساخت داده فرضی بی‌برچسب، Auto-approve، شکستن قرارداد API و تغییر مستقیم منابع Legacy.

## خروجی‌های اجباری برای گزارش
`CHANGELOG`, migration IDs, updated ERD/OpenAPI, diff, tests.xml/logs, security artifacts, UI screenshots, recorded conflicts, evidence links, signed checklist, new decisions, rollback instructions.
