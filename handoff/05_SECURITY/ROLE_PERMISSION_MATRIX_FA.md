# Permission Matrix — پیشنهادی، نیازمند تصویب مالکان واحد

Legend: `R` read by scope; `C` create/draft; `U` update own draft; `A` approve/release; `P` physical post; `X` prohibited. All actions auditable. Below is a **default deny** matrix requiring detailed design in Phase 1.

| Role | Order/PO | Engineering release | Stock reserve/issue | QC grade | Purchase/ETA | Payroll | Config / Jobs |
|---|---|---|---|---|---|---|---|
| Commercial | C/U/A customer terms | R, A customer artwork ONLY | R stock summary | R authorized | R supplier ETA | X | X |
| Engineering | R | C/U/A technical revision | R tool stock | R | C tool fabrication need | X | X |
| Planning | R, A plan release | R technical package | C reservation request / R | R | C demand | X | R health only |
| Warehouse | R authorized | R tool registry | P physical receipt/issue/count, U stock location | R hold | R ETA | X | X |
| Supply | R forecast | R tool specification | R shortage (NO physical receipt) | R hold | C/U vendor quote ETA, A PO per role | X | X |
| Production Operator | R assigned job | R approved OPC only | P station quantity (no stock adjustments) | C defect report | X | X | X |
| Line Supervisor | R own lines | R | R WIP | C QA request | X | R anonymized KPI | X |
| QA / QC | R required grade | R specs | A Hold/Release QA | C/A inspection and actual grade | X | X | X |
| HR | R only if assigned | X | X | X | X | C/U confidential HR; A with maker-checker | X |
| Finance/Costing | R price terms | R standard | R quantity | R grade | R purchasing | R approved payroll subset | X |
| IT Admin | Metadata R if needed | X business approval | X physical post | X grade change | X PO | X salary data by default | C/U infra; safe job cancel with MFA/audit |
| CEO/Management | R scope | R released | R aggregated | R aggregate | R | R aggregate only as approved | R health only |
| AI Copilot | R filtered user context | R filtered | R filtered | R filtered | R filtered | X unless explicit scope; no raw access | X write/kill |

**Split-of-duty:** creator cannot self-approve if approval materially changes finance, QC, warehouse balance, salary, vendor payment or technical released baseline. Approval rights bound to resource revision and one-time action. Source imports treated as PENDING until owner review.
