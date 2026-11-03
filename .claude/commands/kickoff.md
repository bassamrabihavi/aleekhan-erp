---
description: اولین اجرا — بررسی بسته، ثبت منابع جدید، آماده‌سازی فاز ۰ (فقط یک‌بار)
---
First run of the Aleekhan project. Do, in order, and report in Persian:
1. Verify `handoff/SHA256SUMS.txt` (`cd handoff && sha256sum -c SHA256SUMS.txt`); the private folder is excluded from handoff/, so only report mismatches for files that exist. Known: PACKAGE_MANIFEST.json mismatch → record as REV issue for 00.1.
2. If `ALEEKHAN_PRIVATE_DIR` is set: compute sha256 of every file there and compare with `handoff/07_SOURCE_EVIDENCE/SOURCE_REGISTRY.csv`. Write `control/SOURCE_INTAKE.csv` (path, sha256, bytes, registry_match, note). Do not copy files. If `ALEEKHAN_SRC_PASSWORD` is set and `msoffcrypto-tool` is available, list sheet names of new Planning/WH versions vs registered ones in memory only (no execution of macros) and attach the diff to DEC-037.
3. `python3 control/tools/status.py brief` and show the decisions already taken (control/decisions/DECISION_LOG.csv) in one line each, and the still-open Gate-0 decisions with the recommendation from control/decisions/DECISION_PROPOSALS_GATE0_FA.md.
4. Ask the employer (AskUserQuestion if available) to: answer any still-open Gate-0 decision (e.g. DEC-042), and give the formal start for PHASE_00. Do not start PHASE_00 without that answer.
5. On confirmation: record any new decision with `status.py decide`, then `status.py start-phase PHASE_00 --by "<name>"`, render, then continue with `/next 2`.
