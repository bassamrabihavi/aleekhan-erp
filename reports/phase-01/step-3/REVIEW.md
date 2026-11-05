VERDICT: REWORK
PHASE/STEP: PHASE_01 / 01.3 Domain Engine   COMMIT: 6fc3eea (status commit 182c8d4 touches only control/* and REPORT.*)
REVIEWER: aleekhan-reviewer (independent, read-only on source). Date 2026-11-05, work-windows.

## Reproduced verification (reviewer's own runs, logs kept outside the repo)
- `pytest -q` (settings_test, test DB `test_aleekhan_review_013`, PG 17 on 127.0.0.1:5433): **851 passed, 1 skipped, 1 deselected**, exit 0. The skip is the real-ClamAV contract test (`test_phase01_documents_engine.py:272`, clamd not configured). This matches `logs/orch/pytest.log`.
  - Note: a first run with the DB name `aleekhan_review_013` was correctly refused by the throw-away-DB guard (`conftest.py:23`). That was a reviewer setup error, not a defect.
- `ruff check .`: All checks passed. `ruff format --check .`: 151 files already formatted. `mypy .` (strict): Success, no issues in 151 source files.
- `backend/scripts/db_roundtrip.sh`: up, then zero, then up. Result: `schema diff: EMPTY (5963 lines compared)`, `ROUNDTRIP OK`, exit 0.
- `ops/db/roles_check.sh`: `passed=50 failed=0`, exit 0.
- Reviewer repro tests (scratch file outside the repo, run against the same test DB) found 3 defects (REV-0111..0113 below).

## CHECKS
- R01 ✘. Scope matches 01.3: services only, no views. `api.permissions.ACCESS_POLICY` is still DenyAll (`test_phase01_authz_engine.py`, DRF `DEFAULT_AUTHENTICATION_CLASSES == []`). But the claimed SEC-01 list-scoping building block (`scope_q`) does not meet its contract (REV-0112).
- R02 ✘. Decisions are traced: DEC-032 option B, so SoD on publish applies to BUSINESS_RULE only (`params/service.py:128-131`, consistent with `DEC-032_PACKET.md` option B). E-1..E-10 are documented for confirmation. However, the matrix v1.0 cell for OPT on `platform.document.read/download` ("○ approved, linked to own tasks") is not enforced at revision level (REV-0111).
- R03 ✔. Migration 0011 is reversible: the roundtrip shows an EMPTY diff. The REV-0109 trigger checks INSERT valid_from and UPDATE valid_to (`0011_phase01_engine.py:24-49`), and valid_from is already immutable (`0008_phase01_db_guards.py:744-749`). The `ck_session_end_reason` CHECK is rebuilt with CONCURRENT_LIMIT.
- R04 ✔/partial. Writes go through `unit_of_work`: audit + outbox in one transaction, and the chain lock is taken first (`engine/uow.py:139-151`). Decisions lock the request row (`workflow/approvals.py:224-227`), and the concurrency tests pass in the full run. One parameter-history defect remains (REV-0113, P2).
- R05 ✔/partial. Golden files exist: `permission_decisions.golden.json` (matrix cells), `totp_rfc6238.golden.json`, error codes. Unresolved rules are blocked: force kill gives RULE_NOT_APPROVED (`jobs/service.py:201-203`), and BUSINESS_RULE parameters are blocked by `require_approved_rule`.
- R06 ✘. No API in this step, but the per-record and list permission engine used by 01.4 has the two P1 defects REV-0111 and REV-0112. The OpenAPI conflict on QUEUED cancel is recorded (E-7).
- R07 n/a. No UI in 01.3.
- R08 ✔/partial:
  - AES-256-GCM with purpose/owner AAD (`identity/crypto.py`).
  - The session token is stored only as SHA-256 (`identity/sessions.py:78-83`).
  - No account enumeration (`identity/auth.py:270-291`).
  - Reviewer grep of the committed tree for account name, home path, host name, domain and the DB password found 0 hits each.
  - `.env.example` has placeholders only, and the test key in `settings_test.py` is synthetic.
  - The IDOR/BOLA gap is REV-0111.
- R09 ✔. Each module writes only its own tables. Cross-module effects run through registered approval handlers (`approvals.register_resource_handler`), and documents and roles own their own updates.
- R10 n/a. No integration in 01.3.
- R11 ✔/partial. Jobs have safe cancel only, and protected jobs give JOB_PROTECTED (`jobs/service.py:185-186`). The serialization cost of the single audit-chain lock is acknowledged; it is measured in 01.7.
- R12 ✔. CI-reproducible: the reviewer re-ran everything and got identical counts. The fake scanner is clearly named as a test double (`FakeScannerForTests`, test at `test_phase01_documents_engine.py:243`). The skipped real-ClamAV test is justified.
- R13 ✔. `CHANGELOG.md`, `docs/engine/PHASE01_ENGINE.md`, `ERROR_CODES.md`, `ERD.md`, `STATE_TRANSITIONS.md` §4.13, OpenAPI 0.5.2-draft, and `requirements.txt`/`.lock` are updated in the diff (`git show --stat 6fc3eea`).
- R14 n/a. Left to the employer at Gate time.

## ISSUES

### REV-0111 [P1] Operator can download unapproved and superseded revisions
- **Where:** `backend/platform_core/documents/service.py:115-124` (`document_scope`) and `:500-509` (`download`).
- **Problem:** the operator's ○ grant (matrix v1.0: "approved, linked to own tasks") is checked only at document level. If the document has any approved revision and a task linked to it is assigned to the operator, the operator can download **any** CLEAN revision of that document. This includes WORKING, IN_REVIEW, review-REJECTED and SUPERSEDED revisions. The shop floor could therefore receive draft or outdated drawings.
- **Repro:**
  1. The controller uploads r1, it is scanned and approved by the approver.
  2. A WorkTask (`related_type="document"`) is assigned to an `operator_terminal` user.
  3. The controller uploads r2. It is scanned CLEAN and stays WORKING.
  4. `service.download(operator, r2.pk)` returns the r2 bytes. Reviewer output: `OPERATOR GOT UNAPPROVED WORKING REVISION BYTES: True`.
- **Expected fix:** for grants in OWN mode coming from the task link, allow only the revision that is `current_approved_revision` (or status APPROVED). Do this for download and for revision read. Decide whether `related_revision` of the task should pin the revision.
- **Regression test required:** an operator gets NotFound for WORKING, IN_REVIEW and SUPERSEDED revisions and succeeds for the current approved one. Also add a golden or engine test for document.read with the OPT cell.

### REV-0112 [P1] `scope_q` returns nothing for GLOBAL grants and ignores the sensitivity cap
- **Where:** `backend/platform_core/authz/policy.py:338-366`.
- **Problem 1, GLOBAL grants:** for a GLOBAL assignment, `in_scope = Q()` (line 350). OR-ing an empty `Q()` into `Q(pk__in=[])` is a no-op in Django (`Q._combine` returns a copy of self when the other side is empty). As a result, every GLOBAL grant lists **nothing**. That breaks `RbacPolicy.scope_queryset` (line 432), which 01.4 will install.
- **Problem 2, sensitivity:** `scope_q` never applies `max_sensitivity`, unlike `grant_allows` (lines 138-140). So an obvious fix of problem 1 would make S3 documents visible in lists to MGR/EMP grants capped at S1/S2.
- **Repro:** `unit_manager` has a GLOBAL grant `('SCOPE','S2','GLOBAL')`, and the DB holds an S1 and an S3 document. `Document.objects.filter(scope_q(mgr, "platform.document.read", unit_field=None, owner_fields=("created_by_id",)))` returns `set()`, although `can(mgr, read, S1 doc)` is True.
- **Coverage gap:** the existing test `test_scope_q_filters_lists_like_the_record_check` covers only ORG_UNIT and OWN.
- **Expected fix:** use a true match-all expression for GLOBAL, for example `~Q(pk__in=[])`, or build the expression explicitly. Add a sensitivity filter per grant when the model has a sensitivity field, for example a `sensitivity_field` argument. Make `scope_q` provably equal to `grant_allows` for every cell.
- **Regression test required:** a property or golden test showing that, for every matrix cell, `filter(scope_q)` equals `{r : can(r)}`. It must include the GLOBAL, SUBTREE, OWN_UNIT and sensitivity-capped cases.

### REV-0113 [P2] A superseded future-dated parameter value still becomes effective later
- **Where:** `backend/platform_core/params/service.py:215-218` (`_supersede_previous`), together with `platform_param_value` (`migrations/0008_phase01_db_guards.py:188-194`, which selects PUBLISHED or SUPERSEDED ordered by `effective_from DESC`).
- **Repro:**
  1. Publish value 10 for a TECHNICAL parameter, effective now + 1 day.
  2. Publish value 20, effective now. Value 10 becomes SUPERSEDED.
  3. Evaluate the same query at now + 2 days. It returns `('10','SUPERSEDED')`: the withdrawn value silently takes effect.
- **Expected fix:** pick one of these:
  - a value that is superseded before its `effective_from` must never apply, for example by recording `superseded_at` and filtering `effective_from < superseded_at`;
  - refuse to publish when a later-dated published value exists;
  - supersede only values whose `effective_from` is at or before the new one.
- **Note:** history must stay immutable, so the fix is in selection and validation, not in rewriting rows.
- **Regression test required:** the sequence above, asserting that the effective value at now + 2 days is 20.

### REV-0114 [P3] A refused login is recorded as a successful attempt
- **Where:** `backend/platform_core/identity/auth.py:321-323`.
- **Problem:** a login from outside by a user who needs MFA but has not enrolled is refused (no session, 401 MFA_REQUIRED). It is still recorded as `LoginOutcome.OK` with audit outcome SUCCESS. This misleads the security log of page 36/46 and resets the lockout window (`_count_failure` uses the last OK attempt).
- **Expected fix:** use a distinct outcome (for example MFA_ENROLMENT_REQUIRED, or an existing denied outcome) with audit outcome DENIED.
- **Regression test required:** assert the recorded outcome and audit outcome.

### REV-0115 [P3] Purge deletes the bytes before the transaction commits
- **Where:** `backend/platform_core/documents/service.py:556`.
- **Problem:** `storage.delete(key)` runs inside the unit of work, before the commit. If the commit fails, the bytes are gone but `bytes_purged_at` is not set. This is the opposite of what the comment claims. Impact is low: the revision is REJECTED, so it can never be downloaded.
- **Expected fix:** delete after the commit (`transaction.on_commit`), and make the delete idempotent.
- **Regression test required:** none mandatory. A unit test with a forced commit failure is optional.

### REV-0116 [P2, process] No decision packet yet for the first approver
- **Problem:** the "first holder of a business-approval role cannot be confirmed" gap is a known Gate-1 blocker (REPORT §7.1, `PHASE01_ENGINE.md` §4), but no decision packet exists yet.
- **Expected fix:** before Gate-1, write `control/decisions/DEC-0xx_PACKET.md` (options such as a console confirmation in the DEC-054 style or DEC-032 D2) and record the blocked items.
- **Regression test required:** none at this step. This item does not block code.

## Rework scope
Fix REV-0111 and REV-0112 (P1), and ideally REV-0113. Add the regression tests listed above. Re-run the full suite, the roundtrip and roles_check. Then re-review the same step.

## EMPLOYER ATTENTION
- اپراتور فعلاً می‌تواند نسخه‌های تأییدنشده یا قدیمی یک سند را دانلود کند (REV-0111). اصلاح فنی است، ولی لطفاً تأیید کنید: «اپراتور فقط آخرین نسخه تأییدشده سندِ مرتبط با کار خودش را ببیند». آیا همین درست است؟
- اولین «تأییدکننده» را هیچ‌کس نمی‌تواند تأیید کند، چون خودتأییدی ممنوع است (DEC-032). پیش از Gate-1 باید بین «تأیید از کنسول سرور» و «تأیید اضطراری یک‌نفره با ثبت ویژه» تصمیم بگیرید.
- تفسیرهای موتور E-1 تا E-10 (`docs/engine/PHASE01_ENGINE.md` §3) را تأیید یا اصلاح کنید. نمونه: کاربری که MFA لازم دارد ولی ثبت‌نام MFA نکرده، داخل کارخانه وارد می‌شود ولی کارهای حساس برایش بسته است.
