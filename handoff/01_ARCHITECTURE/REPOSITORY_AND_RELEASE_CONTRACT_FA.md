# ساختار مخزن توسعه پیشنهادی (برای ایجاد توسط Codex/Claude Code)

این فایل **نقشه مخزن هدف** است؛ در بسته حاضر هیچ نرم‌افزار عملیاتی جدیدی کدنویسی نشده است.

```text
aleekhan-erp/
  backend/
    config/                    # Django configuration, ASGI, settings
    apps/
      platform/                # auth, permissions, audit, workflow, jobs
      commercial/              # inquiry, orders, pricing terms
      identity/                # products, styles, serials, code rule versions
      engineering/             # dxf, die, cliche, jig, skiving, revision
      bom_opc/                 # multilevel BOM, OPC, time standards
      planning/                # finite capacity, schedule, shifts
      warehouse/               # stock, reservation, GAP, ERP imports
      supply/                  # supplier and PO follow-up
      production/              # cutting, batch/ledger, operator terminal
      quality/                 # QA, QC, NCR/CAPA
      dispatch/                # FG, shipment, returns
      finance_hr/              # sensitive HR, costing, SWU, metrics
      ai_gateway/              # permissioned retrieval/assist only
    migrations/               # per owner module
    tests/                    # per domain + golden/contracts
  frontend/
    src/app,src/pages,src/components,src/features,src/api,src/theme/
    e2e/                      # Playwright screenshots and role tests
  workers/                    # Celery jobs with idempotent task keys
  integrations/               # strictly scoped source adapters
  infrastructure/             # provisioned by coding agent in private env
  docs/
    adr/, domain/, api/, threat-model/, acceptance/, operations/
  test-fixtures/              # synthetic/anonymized, never raw private files
  reports/                    # per Phase/Step evidence and QA
```

- Python code cannot bypass Domain Service and repository ownership: each domain has single authority over writes.
- Migration ID, model revision and API version are reviewed together; no schema destructive migration without backup/copy/verification and rollback.
- CI `lint → type → unit → integration → migration → API contracts → authorization → E2E → security scan → build/artifacts`; “skipped” requires explanation and owner approval.
- Environments: dev, test, staging, production; anonymized fixtures in CI; real sources under a separately permissioned/controlled data area outside Git.
- Release tags after approved Gate only. No automatic promotion based on agent self-report.
