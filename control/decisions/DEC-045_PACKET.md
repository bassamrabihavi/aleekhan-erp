# DEC-045 — Where CI runs and where the Gate-0 test environment / restore drill runs

- Priority: P0 for the PHASE_00 **Gate** (not for steps 00.2–00.6, which can proceed with local runs)
- Gate: Gate-0 · Domain: Platform/Ops · Owner: کارفرما + IT · Raised: 2026-11-03, step 00.1
- Status: OPEN (proposal only — not decided by the agent)

## Question
PHASE_00 Gate requires "CI and backup restore drill in test environment". Approved so far: code on private GitHub (DEC-041), staging + production on an in-company Ubuntu 24.04 server with Docker Compose (DEC-002/DEC-042), RPO 1h / RTO 4h with monthly restore drill (DEC-004). Not decided:
1. **CI runner**: GitHub-hosted Actions runners (third-party cloud executes our code with synthetic fixtures only), a self-hosted runner on a company machine, or no hosted CI (local scripted CI with logs committed to `reports/`).
2. **Test environment for the Gate-0 restore drill**: does the in-company staging server already exist (hardware, OS, network), or should PHASE_00 use a temporary environment (e.g. Docker on the Ubuntu home machine or the work PC) for the first drill?

## Options
A. GitHub-hosted Actions (synthetic data only, no secrets except none needed) + first restore drill on a local Docker environment; repeat drill on staging when it exists.
   Consequence: fastest; code (no data) is processed on GitHub infrastructure — consistent with DEC-041 which already stores code there.
B. Self-hosted GitHub runner on the in-company staging server + drill on that server.
   Consequence: everything inside the company; requires the server now; runner must be isolated (non-root, no access to private sources).
C. Local CI only (`make ci` / script on both machines, logs in `reports/`), drill on local Docker.
   Consequence: no third-party execution; weaker independent evidence (no CI history), more manual work each step.

## Recommendation
A for PHASE_00 (code is already on GitHub per DEC-041; fixtures are synthetic by rule), moving to B once the staging server exists; the Gate-0 restore drill on local Docker is evidence of the procedure, and the staging drill becomes a PHASE_01/12 item.

## What is blocked
Only the PHASE_00 Gate evidence (CI report linked to commit, restore drill). Steps 00.2–00.6 continue with locally run tests and saved logs; step 00.7 needs the answer to configure CI.

## How to record
`status.py decide DEC-045 APPROVED --by "<name>" --note "<option and text>"` after the orchestrator adds DEC-045 to `control/decisions/DECISIONS_ADDENDUM.csv`.
