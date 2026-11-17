# PHASE_02 Gate follow-up — REV issues (2026-11-17)

Opened by the orchestrator from the employer's Gate answers and the orchestrator-run T-004 UAT.
Step 02.8 is reopened (PASS -> REWORK) only for these items. Reviewed migrations are not edited; new migrations only.

| ID | Prio | Source | Item |
|---|---|---|---|
| REV-0290 | P2 | DEC-059 amendment 2026-11-17 (REV-0203) | Enforce: at most one change request in SUBMITTED/APPROVED per order; an unanswered SUBMITTED/APPROVED change request becomes EXPIRED after 30 days (same mechanism/period as DEC-032 platform approvals). Update STATE_TRANSITIONS §5.5 (no longer PROPOSED). |
| REV-0291 | P3 | DEC-032 amendment 2026-11-17 (REV-0254) | Approval inbox and page 33 show the requester's display name (internal user display name only) next to the short id. |
| REV-0292 | P2 | DEC-005 amendment 2026-11-17 (Gate item g) | A DISMISSED disputed legacy value carries over to later Planning imports like a RESOLVED one (no new conflict item; reuse recorded in counts + audit). Replaces `test_dismissed_disputed_value_is_raised_again`. |
| REV-0293 | P2 | T-004 observation (uat02) | A style was activated and a product code issued while its product was still DRAFT; the order wizard then could not find the product (lists ACTIVE products only). Check the contract/spec; if it requires an ACTIVE product, enforce it; if the spec is silent, do not invent a rule — report it as a decision question. |
| REV-0294 | P3 | T-004 run | `reports/phase-02/UAT_HOWTO_FA.md`: steward first login must come before the golden load (`MAKER_NOT_ACTIVE`); the UAT environment needs `ALEEKHAN_INTERNAL_CIDRS` (otherwise `MFA_REQUIRED` for a user without MFA); belt (family 02) golden cases need buckle type + belt width, so only the usable belt cases count. |
