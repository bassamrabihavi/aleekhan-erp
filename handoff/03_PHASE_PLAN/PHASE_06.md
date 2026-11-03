# PHASE_06 — Warehouse, Supply & ERP Snapshot

**عنوان فارسی:** انبار مواد، راهکاران، تفکیک و GAP
**وضعیت:** NOT STARTED / کار Codex/Claude Code؛ فقط با فرمان رسمی مجاز به شروع.
**وابستگی‌ها:** PHASE_01, PHASE_02, PHASE_04
**صفحات در محدوده (نسخه DRAFT):** 18, 19, 20, 24, 43, 44, 49

## مرز فاز، دامنه DB و داده
SourceFile/ExcelRaw, Item, Snapshot, Lot, Location, Hold, Reservation, StockLedger, GAP, SupplyOrder, ETA. داده جدید با Source Provenance و Commit/Migration/Backward compatibility ثبت شود.

## Backend، API، موتور و UI اختصاصی
Import staging, warehouse stock/QA, reservation, GAP/workflow, purchase follow-up and reconciliation UI.

## موتور کسب‌وکار/پردازش و قوانین
Read-only Rahkaran snapshot + raw Excel cell preservation; unit conversion, lot/grade availability, atomic reserve/release. هر قانون مستند دارای Golden Test و مالک تصمیم باشد؛ موارد نامعلوم باید Block شود.

## توالی اجرایی اجباری (هر گام گزارش جدا)
- **06.1 — Discovery & Contract:** تعارض‌ها، جدول داده، state transitions، OpenAPI draft، mock/UI binding و خطرات را ثبت کن؛ برای P0 تصمیم بگیر، هنوز داده واقعی mutate نکن.
- **06.2 — Database:** نسخه Migration، PK/FK/unique/check/index، audit, outbox، rollback و seed غیرحساس؛ تست migrate-up/down و schema diff.
- **06.3 — Domain Engine:** منطق محاسبه/State/Conflict/Idempotency و Error Codes؛ unit/property/golden tests قبل از UI.
- **06.4 — Backend/API:** permission scoped + rate limit + ETag/version + pagination + request-id + OpenAPI و test واقعی.
- **06.5 — UI:** صفحات مربوط، Farsi RTL responsive، state loading/error/empty/stale، keyboard, screenshots چهار سایز و تست E2E.
- **06.6 — Integration:** فقط Source/Events مربوط؛ staging, retries, backoff, compensation, freshness and conflict queue؛ بدون تغییر مستقیم ماژول دیگر.
- **06.7 — Security & Ops:** secret scan, dependency scan, privacy/permissions tests, perf, backup/rollback & job monitoring؛ security checklist امضا شود.
- **06.8 — Report & Review:** Template گزارش، git commit hash، migrations، نتایج Test، UI snapshots، Trace Map و مشکلات؛ **STOP** و انتظار PASS/REWORK/BLOCKED.

## الزامات عرضی اجباری
- DB: migration + FK/check/index + audit/outbox + rollback.
- API: OpenAPI & schema compatibility + idempotency + auth + errors.
- UI: RTL desktop/laptop/tablet/mobile, a11y, role-sensitive, real screenshots.
- ENGINE: deterministic contract + sample & golden tests + traceability.
- SEC: RBAC/ABAC, threat analysis, redaction, secure logs, scan.
- QA: unit/integration/E2E/race/property/migration/security + independent evidence.

## Gate پذیرش
سطر و فرمول خام برگشت‌پذیر؛ Snapshot stale banner؛ رزرو دوگانه و موجودی منفی مردود؛ تأیید دریافت فقط Warehouse؛ مالیات/قیمت محرمانه محفوظ.
شرط عمومی: هیچ Critical/P0 شناخته‌شده باز، هیچ تست اجباری Fail/Skipped بی‌دلیل، Migration برگشت‌پذیر یا دارای طرح جبران مصوب، Permission Matrix مصوب، گزارش CI با Commit مرتبط، UI واقعی غیرنمایشی، تمام Scope این فاز traceable؛ پذیرش کارفرما و ممیز.

## محدوده ممنوع
اجرای فاز وابسته قبل از تأیید گیت، استفاده از Mock به‌عنوان واقعیت ERP، ساخت داده فرضی بی‌برچسب، Auto-approve، شکستن قرارداد API و تغییر مستقیم منابع Legacy.

## خروجی‌های اجباری برای گزارش
`CHANGELOG`, migration IDs, updated ERD/OpenAPI, diff, tests.xml/logs, security artifacts, UI screenshots, recorded conflicts, evidence links, signed checklist, new decisions, rollback instructions.
