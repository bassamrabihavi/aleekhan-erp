# Event catalogue — PHASE_00 + PHASE_01 platform events (PHASE_01 / 01.6)

Source of truth: `backend/platform_core/engine/events.py` (`CATALOGUE`); reviewed golden copy:
`backend/platform_core/tests/golden/event_catalogue.golden.json` (JSON Schema per version). This table is
generated from the code and must be regenerated with it. Status: DRAFT (part of PHASE_01, not a Gate).

Envelope (every event, `platform_outbox_event`): `event_id` (consumer dedupe key), `event_type`, `schema_version`,
`aggregate_type`, `aggregate_id`, `aggregate_version`, `occurred_at` (UTC), `actor_type` / `actor_id`, `request_id`,
`correlation_id`, `causation_id`, `payload`, and the provenance of the producing code (migration `0016`):
`producer` (owning module), `build_commit` (`ALEEKHAN_BUILD_COMMIT`), `schema_migration` (`platform_core.0018_outbox_discard_and_orphan_job`
in this build). Source system: `aleekhan-erp`. Rows written before migration 0016 carry `''` (unknown).

Rules: producers emit only catalogued types, the matching aggregate type and the **current** version, with an exact
payload (no unknown key, no missing key, typed values) - otherwise the whole unit of work is rolled back
(`EngineContractError`). Consumers accept versions **N and N-1** (N-1 upcast to N; handlers see N only); older or
invalid payloads are dead-lettered at once (`SCHEMA_VERSION_UNSUPPORTED`, `SCHEMA_INVALID`), a newer version waits
with backoff (`SCHEMA_VERSION_AHEAD`). Sensitivity of every payload: **S1** - surrogate ids, status codes, system keys,
hashes and counts only; never names, free text, secrets or personal data.

Field kinds: `uuid` (canonical lower-case), `ref` (id of another resource, `[A-Za-z0-9_.:-]{1,64}`), `key` (system key
`[a-z][a-z0-9_]*`), `name` (dotted machine name), `code` (status/state/outcome `[A-Z][A-Z0-9_]*`), `sha256`, `count`
(integer >= 0). `?` = may be null.

| Event type | v | Producer | Aggregate | Payload | Meaning |
|---|---|---|---|---|---|
| `platform.config.field.changed` | 1 | `platform_core.params` | `platform.dynamic_field` | `key`:key, `status`:code | dynamic field definition created/changed |
| `platform.config.parameter.defined` | 1 | `platform_core.params` | `platform.parameter_definition` | `key`:key | parameter definition created |
| `platform.config.parameter.proposed` | 1 | `platform_core.params` | `platform.parameter_value` | `id`:uuid, `parameter_key`:key, `status`:code | parameter value proposed |
| `platform.config.parameter.published` | 1 | `platform_core.params` | `platform.parameter_value` | `id`:uuid, `parameter_key`:key, `status`:code | parameter value published |
| `platform.config.parameter.rejected` | 1 | `platform_core.params` | `platform.parameter_value` | `id`:uuid, `parameter_key`:key, `status`:code | parameter value rejected |
| `platform.document.created` | 1 | `platform_core.documents` | `platform.document` | `id`:uuid | document registered |
| `platform.document.object.purged` | 1 | `platform_core.documents` | `platform.stored_object` | `sha256`:sha256 | bytes of a rejected upload purged (DEC-053); hash kept |
| `platform.document.revision.changed` | 1 | `platform_core.documents` | `platform.document_revision` | `id`:uuid, `document_id`:uuid, `status`:code, `scan_status`:code | revision uploaded/scanned/submitted/approved/rejected/superseded |
| `platform.document.updated` | 1 | `platform_core.documents` | `platform.document` | `id`:uuid | document metadata changed |
| `platform.identity.assignment.changed` | 1 | `platform_core.identity` | `platform.role_assignment` | `id`:uuid, `status`:code | role assignment granted/approved/revoked |
| `platform.identity.mfa.enrolled` | 1 | `platform_core.identity` | `platform.mfa_factor` | `id`:uuid, `user_id`:uuid, `status`:code | TOTP factor confirmed |
| `platform.identity.mfa.enrolment_failed` | 1 | `platform_core.identity` | `platform.mfa_factor` | `id`:uuid | wrong enrolment code |
| `platform.identity.mfa.enrolment_started` | 1 | `platform_core.identity` | `platform.mfa_factor` | `id`:uuid, `user_id`:uuid, `status`:code | TOTP enrolment started |
| `platform.identity.mfa.revoked` | 1 | `platform_core.identity` | `platform.mfa_factor` | `id`:uuid, `user_id`:uuid, `status`:code | factor revoked |
| `platform.identity.owner.bootstrapped` | 1 | `platform_core.identity` | `platform.user` | `id`:uuid, `status`:code | console owner bootstrap |
| `platform.identity.owner.recovered` | 1 | `platform_core.identity` | `platform.user` | `id`:uuid, `status`:code | console owner recovery |
| `platform.identity.role.changed` | 1 | `platform_core.identity` | `platform.role` | `id`:uuid, `status`:code | role created/changed/activated/retired |
| `platform.identity.session.activated` | 1 | `platform_core.identity` | `platform.session` | `id`:uuid, `user_id`:uuid, `state`:code | session activated |
| `platform.identity.session.created` | 1 | `platform_core.identity` | `platform.session` | `id`:uuid, `user_id`:uuid, `state`:code | session created |
| `platform.identity.session.expired` | 1 | `platform_core.identity` | `platform.session` | `id`:uuid, `user_id`:uuid, `state`:code | session expired |
| `platform.identity.session.logged_out` | 1 | `platform_core.identity` | `platform.session` | `id`:uuid, `user_id`:uuid, `state`:code | session logged out |
| `platform.identity.session.revoked` | 1 | `platform_core.identity` | `platform.session` | `id`:uuid, `user_id`:uuid, `state`:code | session revoked |
| `platform.identity.session.stepped_up` | 1 | `platform_core.identity` | `platform.session` | `id`:uuid, `user_id`:uuid | MFA step-up recorded on the session |
| `platform.identity.user.created` | 1 | `platform_core.identity` | `platform.user` | `id`:uuid, `status`:code | user created in-app (DEC-003) |
| `platform.identity.user.mfa_reset` | 1 | `platform_core.identity` | `platform.user` | `id`:uuid, `revoked_factors`:count | admin MFA reset (factors revoked, sessions ended) |
| `platform.identity.user.password_reset` | 1 | `platform_core.identity` | `platform.user` | `id`:uuid, `status`:code | admin password reset |
| `platform.identity.user.status_changed` | 1 | `platform_core.identity` | `platform.user` | `id`:uuid, `status`:code | lock/unlock/disable/enable |
| `platform.identity.user.updated` | 1 | `platform_core.identity` | `platform.user` | `id`:uuid, `status`:code | user profile fields changed |
| `platform.integration.batch_received` | 1 | `platform_core.integration` | `platform.import_batch` | `batch_id`:uuid, `source_code`:key, `sha256`:sha256, `byte_size`:count | file received (hash only, no content) |
| `platform.integration.batch_rejected` | 1 | `platform_core.integration` | `platform.import_batch` | `batch_id`:uuid, `source_code`:key | batch rejected |
| `platform.integration.batch_staged` | 1 | `platform_core.integration` | `platform.import_batch` | `batch_id`:uuid, `source_code`:key, `row_count`:count | rows staged |
| `platform.integration.batch_validated` | 1 | `platform_core.integration` | `platform.import_batch` | `batch_id`:uuid, `source_code`:key, `row_count`:count, `error_row_count`:count | rows validated |
| `platform.integration.compensation_recorded` | 1 | `platform_core.integration` | `platform.compensation_record` | `compensation_id`:uuid, `event_id`:uuid, `consumer`:name, `outcome`:code | compensation recorded for a dead-lettered event |
| `platform.integration.conflict_raised` | 1 | `platform_core.integration` | `platform.conflict_item` | `conflict_id`:uuid, `source_code`:key, `kind`:key, `batch_id`:uuid? | conflict queue item opened |
| `platform.integration.conflict_resolved` | 1 | `platform_core.integration` | `platform.conflict_item` | `conflict_id`:uuid, `source_code`:key, `status`:code | conflict queue item resolved / dismissed |
| `platform.ops.job.changed` | 1 | `platform_core.jobs` | `platform.job_run` | `id`:uuid, `job_type`:key, `state`:code | job run queued/started/cancel requested/finished |
| `platform.org.position.created` | 1 | `platform_core.org` | `platform.position` | `id`:uuid | position created |
| `platform.org.position.updated` | 1 | `platform_core.org` | `platform.position` | `id`:uuid | position changed |
| `platform.org.position_assignment.created` | 1 | `platform_core.org` | `platform.position_assignment` | `id`:uuid | person assigned to a position |
| `platform.org.position_assignment.ended` | 1 | `platform_core.org` | `platform.position_assignment` | `id`:uuid | position assignment ended |
| `platform.org.unit.created` | 1 | `platform_core.org` | `platform.org_unit` | `id`:uuid | org unit created |
| `platform.org.unit.deactivated` | 1 | `platform_core.org` | `platform.org_unit` | `id`:uuid | org unit deactivated |
| `platform.org.unit.moved` | 1 | `platform_core.org` | `platform.org_unit` | `id`:uuid | org unit moved in the tree |
| `platform.org.unit.updated` | 1 | `platform_core.org` | `platform.org_unit` | `id`:uuid | org unit renamed / changed |
| `platform.workflow.approval.approved` | 1 | `platform_core.workflow` | `platform.approval_request` | `id`:uuid, `status`:code, `resource_type`:name, `resource_id`:ref | approval request approved (DEC-032) |
| `platform.workflow.approval.expired` | 1 | `platform_core.workflow` | `platform.approval_request` | `id`:uuid, `status`:code, `resource_type`:name, `resource_id`:ref | approval request expired (DEC-032) |
| `platform.workflow.approval.raised` | 1 | `platform_core.workflow` | `platform.approval_request` | `id`:uuid, `status`:code, `resource_type`:name, `resource_id`:ref | approval request raised (DEC-032) |
| `platform.workflow.approval.rejected` | 1 | `platform_core.workflow` | `platform.approval_request` | `id`:uuid, `status`:code, `resource_type`:name, `resource_id`:ref | approval request rejected (DEC-032) |
| `platform.workflow.approval.superseded` | 1 | `platform_core.workflow` | `platform.approval_request` | `id`:uuid, `status`:code, `resource_type`:name, `resource_id`:ref | approval request superseded (DEC-032) |
| `platform.workflow.approval.withdrawn` | 1 | `platform_core.workflow` | `platform.approval_request` | `id`:uuid, `status`:code, `resource_type`:name, `resource_id`:ref | approval request withdrawn (DEC-032) |
| `platform.workflow.instance.changed` | 1 | `platform_core.workflow` | `platform.workflow_instance` | `id`:uuid, `status`:code | workflow instance started/advanced/finished |
| `platform.workflow.task.changed` | 1 | `platform_core.workflow` | `platform.work_task` | `id`:uuid, `status`:code, `verb`:key | work task state changed (verb = transition) |

52 event types. Adding or changing one = edit `events.py` + regenerate the golden and this
table + reviewed commit; a payload change that is not additive-compatible needs a new version with an upcaster from
the previous one (consumers keep accepting N-1 for one release).
