# REPORT TEMPLATE — توسعه‌دهنده باید برای هر گام پر کند

```
PROJECT: Aleekhan
PHASE: PHASE_XX
STEP: XX.Y
COMMIT SHA: <full hash>
BRANCH/PR: <link or local reference>
STATUS: COMPLETE | PARTIAL | BLOCKED
TIME OF REPORT (UTC):
IMPLEMENTER: Codex | Claude Code
SOURCE BASELINE: handoff v1.0 + commit/sha256 manifest

1. PURPOSE & ACCEPTANCE IDs
- محدوده و الزامات شماره‌دار انجام‌شده، خارج از محدوده، کار وابسته
2. ACTUAL CHANGES
- فایل/جدول/Migration تغییرکرده (path + purpose)
- API + OpenAPI changes, Domain Engine, UI pages, jobs, config
3. DATA INTEGRITY
- FK/Unique/Check, transactions, idempotency, audit, outbox
- how original Excel/DXF/raw fields, checksum and historical snapshots preserved
4. SECURITY EVIDENCE
- Auth, RBAC+record scope+field-level tests, MFA impact, secrets, scans, known risks
5. TEST EVIDENCE (do not invent)
- exact commands, environment, commit, PASS/FAIL/SKIP counts, test logs path
- migration up/down, data fixture golden, race/transaction, API, Playwright screenshots 1440/1180/768/390
6. DEMO
- how to reproduce locally, username TEST ONLY and no secrets, workflow steps, screenshot refs
7. ISSUES/DECISIONS
- P0/P1/P2 defect IDs, unresolved decisions, owner, effect and safe fallback
8. ROLLBACK
- commands/procedure, backup restore evidence, destructive change warning
9. REVIEW REQUEST
- request PASS / REWORK / BLOCKED, specify exact evidence to check
10. NEXT STEP
- proposal only; DO NOT execute until employer and reviewer approve
```

**عدم ارائه شواهد** = «ثبت نشده»، نه «قبول شد». اگر یک تست اجرا نشده، دلیل و اثرش را ذکر کن. اطلاعات واقعی مشتری و حقوق در گزارش عمومی/تصاویر حذف یا ماسک شود.
