# ERD - PHASE_00 platform tables (all migrations 0001-0006)

Status: as of step 00.8 (code identical to commit `d6b6de96784d8d4d715e5978a2552c3531798faa` for the schema; no
migration was added after 00.6). Source of every column, constraint and index below: the schema dump of the
migration round-trip `reports/phase-00/step-7/logs/ci/migration/schema_up_1.sql` (diff against the re-applied
schema is empty: `reports/phase-00/step-7/logs/ci/migration/schema_diff.txt`). Conventions and rollback:
`docs/db/README.md`; integration behaviour: `docs/integration/README.md`.

PHASE_00 has no business tables, no user table and no 14-digit code column (code issuing is BLOCKED,
DEC-005 / DEC-008). `actor_id`, `raised_by_id`, `resolved_by` are UUIDs without FK; the FK to the user table
comes in PHASE_01.

## 1. Migration IDs (app `platform_core`)

| ID | Step | Kind | Content | Reverse |
|---|---|---|---|---|
| `0001_initial` | 00.2 | schema | `platform_audit_event`, `platform_outbox_event`, `platform_idempotency_record`, `platform_schema_meta` | drop the 4 tables |
| `0002_db_triggers` | 00.2 | `RunSQL` | append-only + no-truncate triggers on audit, `platform_touch_row` on outbox / idempotency | drop triggers + functions |
| `0003_seed_schema_meta` | 00.2 | seed | singleton row `platform_schema_meta(id=1)` | delete that row |
| `0004_integration` | 00.6 | schema | `platform_integration_source`, `platform_import_batch`, `platform_import_staging_row`, `platform_conflict_item`, `platform_inbox_event`, `platform_compensation_record` | drop the 6 tables |
| `0005_integration_triggers` | 00.6 | `RunSQL` | touch triggers (source, batch, staging row, conflict), `platform_import_batch_provenance_guard`, `platform_staging_row_payload_guard`, compensation append-only, inbox no-update | drop triggers + functions |
| `0006_seed_integration_sources` | 00.6 | seed | 3 READ-ONLY source rows (`rahkaran_excel` -> DEC-016, `legacy_planning_xlsm` / `legacy_wh_xlsm` -> DEC-025), thresholds TECHNICAL DEFAULT | delete the seeded rows only if they have no batches/conflicts |

Round-trip evidence (up -> zero -> up, schema diff empty): 00.2 `reports/phase-00/step-2/logs/schema/`, 00.6
`reports/phase-00/step-6/logs/migrations/`, 00.7 `reports/phase-00/step-7/logs/ci/05_migration.log`.

## 2. Diagram

Solid lines are real foreign keys (all `ON DELETE PROTECT` in Django, except staging rows: `CASCADE` from their
batch). Dotted lines are logical correlations (no FK).

```mermaid
erDiagram
    platform_audit_event {
        uuid id PK
        timestamptz occurred_at
        varchar actor_type "ck USER|SYSTEM|ANONYMOUS"
        uuid actor_id "no FK until PHASE_01"
        uuid request_id "ix"
        uuid correlation_id
        varchar action
        varchar outcome "ck SUCCESS|DENIED|FAILED"
        varchar resource_type
        varchar resource_id
        bigint resource_version
        jsonb scope
        text reason
        jsonb before "redacted"
        jsonb after "redacted"
    }
    platform_outbox_event {
        bigint id PK "internal"
        uuid event_id UK
        varchar event_type
        int schema_version
        varchar aggregate_type
        varchar aggregate_id
        bigint aggregate_version
        uuid correlation_id "ix"
        uuid causation_id
        jsonb payload
        varchar delivery_status "ck PENDING|DISPATCHED|ACKED|FAILED|DEAD_LETTER"
        int attempts
        timestamptz next_attempt_at "partial ix"
        bigint row_version "trigger"
    }
    platform_idempotency_record {
        uuid id PK
        uuid actor_id "uq with key"
        uuid key
        varchar method
        varchar endpoint
        varchar request_hash "sha256"
        varchar state "ck IN_PROGRESS|COMPLETED|FAILED_RETRYABLE"
        smallint response_status
        timestamptz expires_at "ix"
        bigint row_version "trigger"
    }
    platform_schema_meta {
        smallint id PK "ck = 1"
        varchar schema_contract
        varchar seeded_by_migration
    }
    platform_integration_source {
        smallint id PK
        varchar code UK "ck ^[a-z][a-z0-9_]{2,63}$"
        varchar name_fa
        varchar kind "ck EXCEL_FILE|XLSM_FILE|..."
        varchar direction "ck = READ_ONLY"
        varchar policy_decision_id "ck ^DEC-[0-9]{3}$"
        interval staleness_threshold "ck > 0"
        varchar threshold_basis "TECHNICAL_DEFAULT until decided"
        boolean is_enabled
        timestamptz last_success_at
        timestamptz last_as_of
        uuid last_success_batch_id FK
        bigint row_version "trigger"
    }
    platform_import_batch {
        uuid id PK
        smallint source_id FK
        varchar file_sha256 "ck sha256 hex; uq with source"
        bigint byte_size "ck > 0"
        varchar original_name
        varchar actor_type
        uuid actor_id
        uuid request_id
        uuid correlation_id
        varchar status "ck RECEIVED|STAGED|VALIDATED|..."
        timestamptz source_as_of
        int row_count
        int error_row_count "ck <= row_count"
        timestamptz received_at
        timestamptz staged_at
        timestamptz validated_at
        timestamptz closed_at
        varchar close_reason
        bigint row_version "trigger; provenance guard"
    }
    platform_import_staging_row {
        bigint id PK
        uuid batch_id FK
        varchar sheet_name "uq batch+sheet+row"
        int row_number "ck >= 1"
        jsonb payload "ck object; payload guard"
        varchar payload_sha256
        varchar validation_status "ck NEW|..."
        jsonb error_codes "ck array"
        bigint row_version "trigger"
    }
    platform_conflict_item {
        bigint id PK
        uuid conflict_id UK
        smallint source_id FK
        uuid batch_id FK "nullable"
        varchar conflict_key "partial uq source+kind+key WHERE OPEN"
        varchar kind
        jsonb details
        varchar status "ck OPEN|RESOLVED|..."
        varchar raised_by_type
        uuid raised_by_id
        uuid resolved_by
        timestamptz resolved_at
        varchar resolution_note
        bigint row_version "trigger"
    }
    platform_inbox_event {
        bigint id PK
        varchar consumer "uq with event_id"
        uuid event_id "ix"
        varchar event_type
        int attempt "ck >= 1"
        timestamptz processed_at "no-update trigger"
    }
    platform_compensation_record {
        uuid id PK
        uuid event_id "ix; uq with consumer"
        varchar event_type
        varchar consumer
        varchar aggregate_type
        varchar aggregate_id
        varchar trigger "ck = DEAD_LETTER"
        varchar failure_code
        varchar outcome "ck MANUAL_REQUIRED|HOOK_FAILED|..."
        varchar hook_error
        timestamptz recorded_at "append-only trigger"
    }

    platform_integration_source ||--o{ platform_import_batch : "source_id"
    platform_import_batch ||--o{ platform_import_staging_row : "batch_id (CASCADE)"
    platform_integration_source ||--o{ platform_conflict_item : "source_id"
    platform_import_batch |o--o{ platform_conflict_item : "batch_id (nullable)"
    platform_import_batch |o--o| platform_integration_source : "last_success_batch_id"
    platform_outbox_event ||..o{ platform_inbox_event : "event_id (logical)"
    platform_outbox_event ||..o| platform_compensation_record : "event_id (logical, dead letter)"
    platform_audit_event }o..o{ platform_outbox_event : "request_id / correlation_id (logical)"
```

## 3. Keys and indexes of the 00.6 tables (from the schema dump)

| Table | Unique | Indexes |
|---|---|---|
| `platform_integration_source` | `uq_integration_source_code (code)` | FK index on `last_success_batch_id` |
| `platform_import_batch` | `uq_import_batch_source_sha256 (source_id, file_sha256)` (idempotent receive) | `ix_import_batch_source_recv (source_id, received_at)`, `ix_import_batch_status (status, received_at)`, FK index |
| `platform_import_staging_row` | `uq_staging_row_position (batch_id, sheet_name, row_number)` | `ix_staging_row_batch_status (batch_id, validation_status)`, FK index |
| `platform_conflict_item` | `uq_conflict_item_conflict_id (conflict_id)`; partial `uq_conflict_item_open_key (source_id, kind, conflict_key) WHERE status = 'OPEN'` | `ix_conflict_item_batch`, `ix_conflict_item_status (status, id)`, FK indexes |
| `platform_inbox_event` | `uq_inbox_event_consumer_event (consumer, event_id)` (dedup) | `ix_inbox_event_event` |
| `platform_compensation_record` | `uq_compensation_record_consumer_event (consumer, event_id)` | `ix_compensation_record_event`, `ix_compensation_record_outcome (outcome, recorded_at)` |

Indexes of the 00.2 tables: `docs/db/README.md` section 5. Every CHECK is named `ck_<table>_<rule>` (test
`test_all_check_constraints_are_explicitly_named`). DB roles: `ops/db/grants.sql` (app role: audit and
compensation INSERT+SELECT only), `docs/ops/DB_ROLES.md`.
