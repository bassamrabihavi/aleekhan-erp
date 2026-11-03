---
description: آماده‌سازی بسته Gate برای تصمیم کارفرما (مثال: /gate PHASE_00)
argument-hint: "PHASE_XX"
---
For $ARGUMENTS (must be GATE_PENDING): write `reports/<phase>/GATE_PACKET_FA.md` in Persian containing: what was built (per step, with commit + REVIEW verdict links), UAT checklist the employer must perform (exact steps, test users, URLs), screenshots list, open decisions/risks, Gate criteria from the phase file with ✔/✘ evidence, rollback instructions. Then present a short summary and ask for: ACCEPT / REJECT with notes. Do not accept on the employer's behalf.
