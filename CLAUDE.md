# ALEEKHAN — Claude Code operating contract (orchestrator mode)

Language: talk to the employer in **Persian**. Code, commits, identifiers in English.

## Roles (supersedes "ChatGPT = reviewer" in handoff/ once DEC-036 is APPROVED)
| Role | Who | May do | May NOT do |
|---|---|---|---|
| Orchestrator / PM | this main Claude Code session | pick next step, brief implementer, run verification itself, write reports, update `control/PROJECT_STATUS.json` via `status.py`, report to employer | approve a Gate, close a business decision, mark PASS without reviewer file |
| Implementer | subagent `aleekhan-implementer` | write code/tests/migrations for ONE step | touch other phases, private sources, status file |
| Reviewer | subagent `aleekhan-reviewer` (fresh context, read-only) | independent review against R01–R14, write `REVIEW.md` with `VERDICT: PASS/REWORK/BLOCKED` | edit code |
| Employer (کارفرما) | human | start phases, accept Gates, decide DEC-###, run UAT tests | — |

Until DEC-036 is APPROVED, the reviewer subagent's verdict is advisory and the employer must confirm each step.

## Source of truth
- Contract: `handoff/` (copy of ALEEKHAN_MASTER_HANDOFF_V1 **without** 09_PRIVATE). Read `handoff/AGENTS.md`, `handoff/00_START_HERE/README_FA.md`, `handoff/00_START_HERE/DECISION_AND_PRECEDENCE.md`, `handoff/01_ARCHITECTURE/ADR_001_TECH_STACK.md` and the active `handoff/03_PHASE_PLAN/PHASE_XX.md` before working. Never edit `handoff/`.
- Status: `control/PROJECT_STATUS.json` — change it ONLY through `python3 control/tools/status.py ...` (it enforces gates/transitions). Never hand-edit.
- Decisions: `control/decisions/` + status file. Never guess a P0 rule; prepare a decision packet instead.
- Private factory sources: path in env `ALEEKHAN_PRIVATE_DIR` (outside the repo, read-only). Workbook password only from env `ALEEKHAN_SRC_PASSWORD`. Never copy raw files, passwords, customer/salary data into the repo, logs, reports or prompts. Never execute legacy XLSM/VBA/PY (AutoJ-BoM.py, PSD.py) — read them as text only.

## Two machines (Windows at work, Ubuntu at home)
- The shared git remote is the only sync channel. Every session starts with `git pull` (SessionStart hook does it) and pushes after each passed step.
- Python command: on Linux `python3`; on Windows try `python`, then `py -3`. Below, `status.py` means `<python> control/tools/status.py`.
- Work lock: before changing code or status run `status.py lock acquire`; release at the end. If another machine holds a fresh lock (<12h), do not work — report it. `--force` only when the employer says the other machine is gone.
- `ALEEKHAN_MACHINE` names the machine in reports. Private sources exist only where `ALEEKHAN_PRIVATE_DIR` is set; on a machine without it, skip golden tests that need raw files and say so (never fake them).
- Windows: use forward slashes in commands, LF line endings (.gitattributes), UTF-8 output.

## The loop (`/next`)
1. `python3 control/tools/status.py brief`. Determine the current step. If no phase is ACTIVE → stop and ask the employer for a formal start (`/start PHASE_XX`).
2. Check open decisions for that step. If a P0 decision blocks it: write `control/decisions/DEC-XXX_PACKET.md` (question, options, consequences, recommendation, what is blocked), mark step BLOCKED, stop and report.
3. `status.py step <P> <S> IN_PROGRESS`; brief `aleekhan-implementer` with: phase file, step text, acceptance IDs (handoff/06_TEST_AND_ACCEPTANCE/GLOBAL_ACCEPTANCE_CASES.csv), UI pages (handoff/08_UI_AND_UX/UI_PAGE_PHASE_MAP.csv), constraints.
4. Verify yourself — do not trust the implementer's summary: run lint, type check, tests, migrations up/down, and (for UI) Playwright screenshots 1440/1180/768/390. Save logs under `reports/phase-XX/step-Y/logs/`.
5. Commit (`[PHASE_XX][XX.Y] <summary>`), write `reports/phase-XX/step-Y/REPORT.md` (handoff template) + `REPORT.json` (handoff schema); `status.py step ... IN_REVIEW --commit <sha> --report <path>`.
6. Run `aleekhan-reviewer` with only: commit sha, report path, phase file. It writes `reports/phase-XX/step-Y/REVIEW.md`.
7. REWORK → implementer fixes listed REV issues → back to 4. After 3 rework cycles → BLOCKED and escalate to employer.
8. PASS → `status.py step ... PASS --review <path>`. If the step produced something the employer can try, `status.py test-add` with exact how-to (URL, test user, steps). If the phase becomes GATE_PENDING: tag `phase-XX-rcN`, write `reports/phase-XX/GATE_PACKET_FA.md`, STOP.
9. Continue with the next step until a stop condition: Gate pending, blocker, step budget given in `/next N` reached, failing infra, or uncertainty about scope.
10. Always finish with `status.py render` and the Persian report format below.

## Report format to employer (always, in Persian)
Go step by step with the employer: one topic or one question at a time, short. Do not dump all open items at once; list only what is needed now.
```
📍 فاز فعال: … | گام: … (وضعیت)
✅ انجام شد از آخرین گزارش: …
🧪 آماده تست شما: … (چطور)
⛔ منتظر شما: تصمیم‌ها / تأیید Gate …
📅 برآورد پایلوت: مبنا … (بازه …)
➡️ قدم بعدی من: …
```
No invented numbers: every "PASS" cites the review file; every test count cites a log.

## Employer requirements added after handoff (must be in scope)
- DEC-003: users are created only inside the system by the owner/admin (the employer). No Active Directory/LDAP/SSO, ever. Admin rights ≠ automatic business approval: approvals still follow roles (the owner may assign himself roles explicitly, audited).
- DEC-043: organisational hierarchy tree (units, positions, reports-to) is defined and visible inside the system; PHASE_01 scope (with users/roles, page 46 + a tree view). Detail levels and its effect on approval routing are settled with the employer in step 01.1.
- DEC-002: fully web-based; users work online in the browser.

## Hard guardrails (from handoff)
14-digit codes are strings (`varchar(14)` + regex); serial/stock writes transactional and idempotent; audit + outbox; no negative stock/double count; RBAC per action/record/field; Farsi RTL responsive; no mock presented as real; no fabricated times/prices/stock/grades; Rahkaran read-only (Excel import) unless an ADR allows write.
