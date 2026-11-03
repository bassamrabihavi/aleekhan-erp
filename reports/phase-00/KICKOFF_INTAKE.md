# Kickoff intake — 2026-11-03 (machine: work-windows)

## 1. handoff/SHA256SUMS.txt
- 287 files OK.
- 46 entries under `09_PRIVATE_FACTORY_SOURCES/` not present (excluded from repo by design) — not counted as mismatches.
- 14 mismatches on existing files:
  - 13 CSV files (PHASE_INDEX, SOURCE_REGISTRY, UI_PAGE_PHASE_MAP, DESIGN_CATALOG_52/05_06_prd_listgh/source_cell_map,
    10_REFERENCE_SPECS/time_capacity_v1/data_collection_csv/01..08, 11_PROJECT_MANAGEMENT/DECISION_REGISTER):
    content matches the registered hash exactly when line endings are CRLF. Cause: repo `.gitattributes`
    (`* text=auto eol=lf`) normalised them. Content is unchanged; only byte-level hash differs.
  - `PACKAGE_MANIFEST.json`: genuine mismatch (neither LF nor CRLF variant matches) — known issue.

### REV issues for step 00.1
- REV-00.1-A: PACKAGE_MANIFEST.json hash does not match SHA256SUMS.txt (known; regenerate manifest/sums or document).
- REV-00.1-B: hash verification must be line-ending aware (e.g. `handoff/** -text` in .gitattributes, or a
  verifier that normalises CRLF for text files). Otherwise 13 CSVs always fail on clean clones.

## 2. Private sources
`ALEEKHAN_PRIVATE_DIR` is not set on this machine → SOURCE_INTAKE.csv not produced; DEC-037 sheet diff not done.
To be run on a machine with the private folder and password env set.

## 3. Decisions
All Gate-0 decisions recorded (DEC-001/002/003/004/028/036/037/039/040/041/042/043). PHASE_00 started by employer.
