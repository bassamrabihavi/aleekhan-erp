---
description: ثبت تصمیم Gate توسط کارفرما (مثال: /approve PHASE_00 ACCEPTED علی خان "UAT ok")
argument-hint: "PHASE_XX ACCEPTED|REJECTED <name> [note]"
---
Record the employer's Gate verdict: $ARGUMENTS
Run `python3 control/tools/status.py gate <PHASE> <VERDICT> --by "<name>" --note "<note>"`. On ACCEPTED: create git tag `phase-XX-accepted`, render status, list phases that are now startable and the decisions they need. On REJECTED: convert notes into REV issues and plan rework. Report in Persian.
