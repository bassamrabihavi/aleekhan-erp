---
description: ثبت تصمیم کارفرما برای یک مورد DEC (مثال: /decide DEC-001 APPROVED علی خان "Django 5.2")
argument-hint: "DEC-### STATUS <name> \"decision text\""
---
Record decision: $ARGUMENTS
Run `python3 control/tools/status.py decide <ID> <STATUS> --by "<name>" --note "<text>"`. Append the decision to `control/decisions/DECISION_LOG.md` (date, id, text, decided by). If any step was BLOCKED by it, say which can resume. Report in Persian.
