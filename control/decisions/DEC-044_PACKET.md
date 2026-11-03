# DEC-044 — Handoff package integrity exception (PACKAGE_MANIFEST.json + CRLF CSVs)

- Priority: P1 (affects PHASE_00 Gate criterion "همه فایل‌ها Hash و منبع دارند"; no business rule)
- Gate: Gate-0 · Domain: Governance/Source · Owner: کارفرما (package author) · Raised: 2026-11-03, step 00.1 (REV-00.1-A, REV-00.1-B)
- Status: OPEN (proposal only — not decided by the agent)

## Question
`handoff/` is immutable and verified against `handoff/SHA256SUMS.txt`. Two defects exist:
1. `PACKAGE_MANIFEST.json`: expected `e3b9ef1b0d915f036943fdfb0a98a001f3fa381ea1736533f227befebf8479a6`, actual `e20b196610e02275bef2decfbf954218b543ce3586265c11fbdc0cb1d4432eaa` (neither LF nor CRLF variant matches). Content is a 10-key summary (no business data).
2. 13 CSV files were stored in Git with LF while the package registered CRLF bytes (content identical). `.gitattributes` now has `handoff/** -text -eol`, but the committed bytes are still LF; the agent is not allowed to edit `handoff/`.

How should the Gate-0 integrity criterion treat these?

## Options
A. **Accept documented exception** — keep files as they are; `tools/verify_handoff.py` passes with `EOL_ONLY` (13) and `KNOWN_DEFECT` (1, pinned to the exact actual hash). `--strict` would still fail.
   Consequence: zero effort; integrity is content-level (not byte-level) for 13 files; manifest drift permanently documented.
B. **Restore exact bytes for the 13 CSVs** (one-time commit converting them back to CRLF, authorised by the employer as an exception to "never edit handoff/"), and accept the manifest as known defect.
   Consequence: `sha256sum -c` matches byte-exactly for all files except the manifest; small one-off commit.
C. **Package author issues v1.0.1** (regenerated SHA256SUMS including correct manifest hash), replacing `handoff/` in one commit.
   Consequence: cleanest evidence; requires the original package tool/author; new baseline hash recorded.

## Recommendation
B now (cheap, byte-exact), and C only if a new package is issued for other reasons.

## What is blocked
Nothing in development. Only the Gate-0 sign-off of the "all files hashed" criterion waits for this decision.

## How to record
`status.py decide DEC-044 APPROVED --by "<name>" --note "<option and text>"` (requires DEC-044 to exist in the decisions list — orchestrator to add it to `control/decisions/DECISIONS_ADDENDUM.csv`).
