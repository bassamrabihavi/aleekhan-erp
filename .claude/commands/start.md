---
description: شروع رسمی یک فاز توسط کارفرما (مثال: /start PHASE_01 علی خان)
argument-hint: "PHASE_XX <employer name>"
---
The employer formally authorises starting a phase: $ARGUMENTS
Run `python3 control/tools/status.py start-phase <PHASE> --by "<name>"`. If refused, explain why in Persian (missing accepted Gates / open P0). On success, read the phase file, list its 8 steps, its in-scope pages and acceptance IDs and the open decisions affecting it, then ask whether to run `/next`.
