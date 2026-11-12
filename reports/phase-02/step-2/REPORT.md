# REPORT — PHASE_02 / 02.2 Database

```
PROJECT: Aleekhan
PHASE: PHASE_02
STEP: 02.2
COMMIT SHA: c8b3dff
BRANCH/PR: main
STATUS: COMPLETE
TIME OF REPORT (UTC): 2026-11-12
IMPLEMENTER: Claude Code (aleekhan-implementer); verification re-run and report written by orchestrator on work-windows
SOURCE BASELINE: handoff v1.0; PHASE_01 Gate ACCEPTED; DEC-005/006/057/058/059/060 APPROVED 2026-11-12
```

## 1. Purpose & acceptance
This step builds the PHASE_02 database layer:
- customers and brands;
- product type/category classes, products, styles and style revisions;
- code rule revisions, golden cases and the 14-digit product code registry;
- the gapless factory serial counter, serials and serial snapshots;
- typed external references and historical order records;
- orders, order lines, order versions and change requests;
- the DEC-057 permission matrix v2.0.

There is no API or UI in this step: the API is 02.4 and the engine/use cases are 02.3.

Acceptance cases covered at DB/primitive level:
- **ID-01:** Code14 is `varchar(14)` + `^[0-9]{14}$`, with fixed-width segment columns.
- **ID-02:** the 100-confirm race test passes, with no duplicate and no gap.
- **ID-03:** each line has its own unique serial FK.
- **ID-04:** idempotent allocation, plus a race of 6 duplicate confirms where exactly one succeeds.

## 2. Actual changes
**Migrations**
- `0019_phase02_identity_commercial_schema`: 21 tables with named constraints. All FKs are PROTECT and indexed.
- `0020_phase02_db_guards`:
  - touch, no-delete, append-only, terminal-state and immutable-column triggers;
  - business guards;
  - 6 deferred commit-time checks: gapless counter, serial↔line pairing, snapshot v1, order version row, applied change request has a version, line and serial cancelled together.
- `0021_phase02_seed_catalogue`: generic seed only.
  - Units PIECE/PAIR, 4 order types and 4 external reference types (DEC-058).
  - Counter `factory_serial` starting at 63001 (DEC-006).
  - **No** type, category, code, customer or serial.
- `0022_dec057_matrix_v20`:
  - 22 identity/commercial permissions, with fresh MFA on 4 actions;
  - 5 BUSINESS roles;
  - owner business-approval exception grows from 3 to 6 pairs;
  - the reverse restores the 0015 guard bodies exactly.

**Code**
- `product_identity/{models,serials}.py`: `allocate_serial` locks the counter row FOR UPDATE and moves it +1 inside the caller's unit of work. It uses no sequence and no MAX()+1. It writes the serial, snapshot v1, the audit row and the `identity.serial.allocated` outbox event, and is idempotent per key.
- `commercial/models.py`.
- `authz/policy.py`: `OWNER_BA_ACTIONS` = 6.
- `engine/events.py`: migration head is 0022.

**Tests:** `test_phase02_schema.py` (55), `test_phase02_serial_allocation.py` (6), `phase02_factories.py` (synthetic data only), plus updated PHASE_01 tests that now expect matrix v2.0.

**Docs:** `ERD.md` §7, `DATA_TABLE.md`, `STATE_TRANSITIONS.md`, `PERMISSION_MATRIX_DRAFT.md` v2.0, `EVENT_CATALOGUE.md`, `CHANGELOG.md`.

**Ops:** `grants.sql`, `roles_check.sh` (16 new checks).

**REV-0201:** Identity owns serials. The Commercial line holds the only pairing column, a UNIQUE FK `serial_id`. The pairing is proven at commit (ERD §7.1).

**REV-0202:** blocked-by ids must exist in a register.

**REV-0203:** "one open change request per order" and "30-day expiry" are tagged PROPOSED and are not enforced.

## 3. Data integrity
- **Serials:**
  - plain integer text, CHECK `^[1-9][0-9]*$`;
  - UNIQUE on number, value and allocation key;
  - ALLOCATED → CANCELLED only, never deleted or reused.
- **Rollback safety:** a confirm that rolls back consumes no number (test).
- **Legacy serials:** stored as text history with a duplicate flag; a plain legacy value ≥ 63000 is refused.
- **Product codes:**
  - UNIQUE(namespace, code);
  - ACTIVE requires ERP_MATCHED and RESERVED requires ERP_PENDING (DEC-005 B1);
  - a system-issued code needs an ACTIVE rule revision.
- **Orders:**
  - single ON_HOLD with stored previous state;
  - cancel only before release (DEC-059 C-A);
  - after release only due-date/hold/resume change requests;
  - maker ≠ checker on confirm and decide.

## 4. Security evidence
- No real Planning value is in the repo: seeds are generic and factories are synthetic. A grep for real-looking codes and serials found only the synthetic example `02010790010001`.
- Private sources were not read in this step.
- Path/account leak grep on `reports/phase-02/step-2/`: 0 hits after `redact_paths.py --in-place`.
- `secret_scan.py`: findings=0.
- `roles_check.sh`: 66 passed, 0 failed, including the grants on new tables.

## 5. Test evidence (orchestrator re-run, logs in `logs/orch/`)
| Check | Result | Log |
|---|---|---|
| ruff check + format --check | PASS | `logs/orch/ruff.log` |
| mypy (205 files) | PASS | `logs/orch/mypy.log` |
| makemigrations --check | No changes | `logs/orch/makemigrations.log` |
| pytest -m "not perf" | 2029 passed, 1 skipped (clamd), 7 deselected | `logs/orch/pytest.log`, `logs/orch/pytest.xml` |
| race tests ×3 | 29 passed in each run | `logs/orch/race_x3.log` |
| db_roundtrip.sh | ROUNDTRIP OK, schema diff EMPTY | `logs/orch/db_roundtrip.log` |
| roles_check.sh | passed=66 failed=0 | `logs/orch/roles_check.log` |
| OpenAPI | unchanged (`git diff docs/api` empty), validator OK | this run |
| PHASE_02-only rollback to 0018 and back | OK (implementer run) | `logs/phase02_partial_rollback.log` |

**Note:** the ID-02 race test runs 100 confirms over 32 concurrent connections (`ALEEKHAN_RACE_WORKERS`), because the test server's connection limit is 100.

## 6. Demo (employer)
Nothing for the employer to test in this step; there is no UI or API yet.

## 7. Issues / decisions
1. **Owner read gap:** the owner may decide PHASE_02 items, but DEC-057 gives him no PHASE_02 read permission. This is the same gap as the v1.3 documents fix, so it needs an employer question.
2. **Due-date planning approval (DEC-059):**
   - The DB requires the approval, but the matrix has no permission for it.
   - It is open whether the approver may be the same person as the deciding manager.
3. Change-request expiry and the one-open-CR rule are PROPOSED only (REV-0203).
4. **Contract drift owed to 02.4:**
   - blocked-by markers for DEC-005/006/057/059;
   - `SerialNumber` pattern;
   - `PAUSED`/`SERIAL_ALLOCATED` enums;
   - type/category class levels;
   - `Style.category_id`;
   - order `customer_representative_name`;
   - historical record match fields.
5. The import must route legacy serials ≥ 63000 to the conflict queue (02.6), and must also check the paper and Rahkaran serials.
6. Representative-name masking and read audit belong to 02.3/02.4.
7. There is no buckle-type master table; the buckle code is a 2-digit column.
8. The number format for orders, customers and change requests is left to 02.3.
9. Golden tests with real Planning data were not run in this step (02.3+, work machine only).
10. **Proposed tooling fixes:**
    - `redact_paths.py` writes `hostname="<host>"`, which breaks junit XML well-formedness.
    - `db_roundtrip.sh` should also count `identity_%`, `commercial_%` and `phase02_%` functions after rollback.

## 8. Rollback
`migrate platform_core 0018` removes every PHASE_02 table, function and permission and restores matrix v1.3 (tested). Then `git revert c8b3dff`.

## 9. Review request
PASS requested, against R01–R14.

## 10. Next step
02.3: engine and use cases. This covers code issue/preview, order create/confirm with serial allocation, change requests, and representative-name masking and audit.
