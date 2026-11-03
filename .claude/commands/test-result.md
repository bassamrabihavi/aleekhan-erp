---
description: ثبت نتیجه تست کارفرما (مثال: /test-result T-003 FAIL "سریال تکراری ساخت")
argument-hint: "T-### PASS|FAIL \"note\""
---
Record: $ARGUMENTS via `python3 control/tools/status.py test-done <ID> --result <R> --note "<note>"`. On FAIL: open a REV issue (P0/P1 per impact), reproduce it, and plan the fix in the current phase. Report in Persian.
