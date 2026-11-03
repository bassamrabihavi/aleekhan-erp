# Instructions for Codex / coding agents — ALEEKHAN

Read `00_START_HERE/README_FA.md` first and obey `00_START_HERE/DECISION_AND_PRECEDENCE.md`.
Do not generate all 52 pages at once. Implement **only the active authorized phase and step** from `03_PHASE_PLAN/`.
The assistant ChatGPT is architecture/QA reviewer; **you are the implementation agent**.

## Mandatory process for EVERY task
1. Inventory relevant source docs and conflicts; identify CONFIRMED vs PROPOSED vs BLOCKED.
2. Write an implementation plan: affected domain, DB, backend, engine, UI, security, imports, tests, migrations, rollback; map to phase acceptance IDs.
3. Obtain explicit employer approval for P0 ambiguous business rules. Never silently create a production standard or overwrite historical values.
4. Implement incrementally. Treat legacy XLSM, DXF, PY as untrusted inputs, never run them automatically.
5. Run formatting, static typing, unit/integration/API/permission/E2E tests, schema checks, and security checks. Capture results, including failures.
6. Send a report using `04_AGENT_WORKFLOW/DEVELOPER_REPORT_TEMPLATE.md` containing commit hash, actual evidence and locations. Update open decisions and blockers.
7. STOP. No next phase without `PASS` from reviewer and employer. On `REWORK`, fix the listed issues and resubmit the same phase.

## Guardrails
- Financial/HR/admin permissions isolated; no implicit superuser business approval.
- Database writes transactional; idempotent import/actions; audit/outbox; prevent double count/stock negative and race conditions.
- Normalized 14-digit identifiers remain strings; external IDs not assumed unique across systems without namespace.
- Farsi RTL responsive UI. Existing visual assets are DRAFT; use design system tokens, include real screenshots.
- Never fabricate a machine time, price, stock lot, quality grade, physical quantity or reservation confirmation.
- Do not upload `09_PRIVATE_FACTORY_SOURCES` to public or unapproved services; redact reports.
- Never insert credentials in code, logs, commits, ZIPs or prompts.
- Explain code changes to reviewer in Persian. Cite tests and source files/lines/commit.
