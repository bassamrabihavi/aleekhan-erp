"""Event catalogue (PHASE_01 / 01.6): every outbox event type the platform may emit, with its payload schema.

Contract sources: handoff STATE_EVENT_AND_API_CONTRACT (event envelope, idempotent handlers, DLQ visible),
SOURCE_MAPPING_AND_IMPORT (provenance), ARCHITECTURE_OVERVIEW ("never write another module's tables" - modules
talk through these events). Human-readable copy: docs/integration/EVENT_CATALOGUE.md; golden:
``tests/golden/event_catalogue.golden.json`` (a changed catalogue is a reviewed change).

Rules enforced here:

* **Producer side** (:func:`check_emit`, called by ``UnitOfWork.emit``): the event type must be catalogued,
  the aggregate type must match, ``schema_version`` must be the catalogue's *current* version and the payload
  must match that version exactly (no unknown key, no missing required key, typed values). A violation raises
  :class:`~platform_core.engine.errors.EngineContractError` inside the transaction, so the business write is
  rolled back together with it (an undocumented event can never be published).
* **Consumer side** (:func:`admit`, called by ``RegistryPublisher``): a consumer accepts the current version
  *N* and the previous version *N-1* (upcast to *N* through the catalogue's upcaster) - backward compatible
  rolling deploys. Older versions or a payload that does not match its version are **permanent** failures
  (dead letter at once: retrying cannot help). A version newer than *N* is a **transient** failure (the event
  waits with backoff until the consumer is deployed in the newer version).
* **Sensitivity**: every PHASE_01 payload is S1 - identifiers, status codes and counts only. No names, no
  free text, no secrets, no personal data beyond surrogate ids (the sensitive-key filter of ``uow.emit`` still
  runs first).
* **Provenance** (phase rule "new data carries source provenance and commit/migration"): every outbox row
  records ``producer`` (owning module), ``build_commit`` (``settings.ALEEKHAN_BUILD_COMMIT``) and
  ``schema_migration`` (:data:`SCHEMA_MIGRATION_HEAD`, the newest platform_core migration this code expects;
  a test pins it to the migration graph's leaf).

Synthetic namespace: ALEEKHAN_ENV ``test`` / ``dev`` accept uncatalogued types under the reserved namespace
``platform.synthetic.`` (engine tests, the DB roles check, the backup drill seed; payload unchecked);
staging and prod never do (``settings.DEPLOYED``).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

from .errors import EngineContractError

SOURCE_SYSTEM: Final = "aleekhan-erp"
# Newest platform_core migration this code was written for (provenance of every outbox row). Pinned to the
# leaf of the migration graph by test_integration_events.py::test_schema_migration_head_is_the_graph_leaf.
SCHEMA_MIGRATION_HEAD: Final = "platform_core.0025_phase02_api_numbers"
SYNTHETIC_TEST_PREFIX: Final = "platform.synthetic."

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_PATTERNS: Final[Mapping[str, re.Pattern[str]]] = MappingProxyType(
    {
        "uuid": _UUID_RE,
        # surrogate id of another resource (uuid or system key), never free text
        "ref": re.compile(r"^[A-Za-z0-9_.:-]{1,64}$"),
        # system key: parameter / field key, job type, source code, conflict kind, verb
        "key": re.compile(r"^[a-z][a-z0-9_]{0,99}$"),
        # dotted machine name: consumer, resource type
        "name": re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)*$"),
        # status / state / outcome code
        "code": re.compile(r"^[A-Z][A-Z0-9_]{0,39}$"),
        "sha256": re.compile(r"^[0-9a-f]{64}$"),
    }
)
KINDS: Final = frozenset({*_PATTERNS, "count", "bool"})
SENSITIVITY: Final = "S1"


@dataclass(frozen=True)
class F:
    """A payload field: ``kind`` in :data:`KINDS`; ``nullable`` allows null; ``required`` = key present."""

    kind: str
    required: bool = True
    nullable: bool = False

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown field kind {self.kind!r}")

    def as_json_schema(self) -> dict[str, Any]:
        if self.kind == "count":
            base: dict[str, Any] = {"type": "integer", "minimum": 0}
        elif self.kind == "bool":
            base = {"type": "boolean"}
        else:
            base = {"type": "string", "pattern": _PATTERNS[self.kind].pattern}
        if self.nullable:
            return {"oneOf": [base, {"type": "null"}]}
        return base


Upcaster = Callable[[Mapping[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class EventSpec:
    event_type: str
    producer: str
    aggregate_type: str
    description: str
    versions: Mapping[int, Mapping[str, F]]
    # upcasters[v] turns a version-v payload into a version v+1 payload (consumer accepts N and N-1)
    upcasters: Mapping[int, Upcaster] = field(default_factory=dict)
    sensitivity: str = SENSITIVITY

    def __post_init__(self) -> None:
        if not self.versions or min(self.versions) < 1:
            raise ValueError(f"{self.event_type}: versions start at 1")
        if sorted(self.versions) != list(range(1, max(self.versions) + 1)):
            raise ValueError(f"{self.event_type}: versions must be contiguous")
        for v in self.upcasters:
            if v + 1 not in self.versions:
                raise ValueError(f"{self.event_type}: upcaster {v}->{v + 1} without version {v + 1}")

    @property
    def current_version(self) -> int:
        return max(self.versions)

    @property
    def accepted_versions(self) -> frozenset[int]:
        n = self.current_version
        prev = n - 1
        return frozenset({n, prev} if prev in self.upcasters else {n})

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "producer": self.producer,
            "aggregate_type": self.aggregate_type,
            "description": self.description,
            "sensitivity": self.sensitivity,
            "current_version": self.current_version,
            "accepted_versions": sorted(self.accepted_versions),
            "versions": {str(v): json_schema(fields) for v, fields in sorted(self.versions.items())},
        }


def json_schema(fields: Mapping[str, F]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(k for k, f in fields.items() if f.required),
        "properties": {k: f.as_json_schema() for k, f in sorted(fields.items())},
    }


def payload_errors(fields: Mapping[str, F], payload: Mapping[str, Any]) -> list[str]:
    """``["<field>:<CODE>", ...]`` - codes only (``UNKNOWN_FIELD``, ``MISSING``, ``TYPE``); never values."""
    errors = [f"{k}:UNKNOWN_FIELD" for k in sorted(set(payload) - set(fields))]
    for name, spec in sorted(fields.items()):
        if name not in payload:
            if spec.required:
                errors.append(f"{name}:MISSING")
            continue
        value = payload[name]
        if value is None:
            if not spec.nullable:
                errors.append(f"{name}:TYPE")
            continue
        if spec.kind == "count":
            ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        elif spec.kind == "bool":
            ok = isinstance(value, bool)
        else:
            ok = isinstance(value, str) and bool(_PATTERNS[spec.kind].fullmatch(value))
        if not ok:
            errors.append(f"{name}:TYPE")
    return errors


# ------------------------------------------------------------------------------------------------ catalogue
U, REF, KEY, NAME, CODE, SHA, N = (
    F("uuid"),
    F("ref"),
    F("key"),
    F("name"),
    F("code"),
    F("sha256"),
    F("count"),
)
_ID_STATUS = {"id": U, "status": CODE}
_ID = {"id": U}

ID: Final = "platform_core.identity"
ORG: Final = "platform_core.org"
WF: Final = "platform_core.workflow"
DOC: Final = "platform_core.documents"
CFG: Final = "platform_core.params"
OPS: Final = "platform_core.jobs"
INT: Final = "platform_core.integration"
PID: Final = "platform_core.product_identity"
COM: Final = "platform_core.commercial"


def _spec(
    event_type: str, producer: str, aggregate_type: str, description: str, fields: Mapping[str, F]
) -> EventSpec:
    return EventSpec(event_type, producer, aggregate_type, description, {1: MappingProxyType(dict(fields))})


_SPECS: tuple[EventSpec, ...] = (
    # identity: users (the payload never carries username / display name - ids and status only)
    _spec("platform.identity.user.created", ID, "platform.user", "user created in-app (DEC-003)", _ID_STATUS),
    _spec("platform.identity.user.updated", ID, "platform.user", "user profile fields changed", _ID_STATUS),
    _spec("platform.identity.user.password_reset", ID, "platform.user", "admin password reset", _ID_STATUS),
    _spec(
        "platform.identity.user.status_changed", ID, "platform.user", "lock/unlock/disable/enable", _ID_STATUS
    ),
    _spec(
        "platform.identity.user.mfa_reset",
        ID,
        "platform.user",
        "admin MFA reset (factors revoked, sessions ended)",
        {"id": U, "revoked_factors": N},
    ),
    _spec("platform.identity.owner.bootstrapped", ID, "platform.user", "console owner bootstrap", _ID_STATUS),
    _spec("platform.identity.owner.recovered", ID, "platform.user", "console owner recovery", _ID_STATUS),
    # identity: MFA factors
    _spec(
        "platform.identity.mfa.enrolment_started",
        ID,
        "platform.mfa_factor",
        "TOTP enrolment started",
        {"id": U, "user_id": U, "status": CODE},
    ),
    _spec(
        "platform.identity.mfa.enrolled",
        ID,
        "platform.mfa_factor",
        "TOTP factor confirmed",
        {"id": U, "user_id": U, "status": CODE},
    ),
    _spec("platform.identity.mfa.enrolment_failed", ID, "platform.mfa_factor", "wrong enrolment code", _ID),
    _spec(
        "platform.identity.mfa.revoked",
        ID,
        "platform.mfa_factor",
        "factor revoked",
        {"id": U, "user_id": U, "status": CODE},
    ),
    # identity: sessions
    *(
        _spec(
            f"platform.identity.session.{verb}",
            ID,
            "platform.session",
            f"session {verb.replace('_', ' ')}",
            {"id": U, "user_id": U, "state": CODE},
        )
        for verb in ("created", "activated", "expired", "logged_out", "revoked")
    ),
    _spec(
        "platform.identity.session.stepped_up",
        ID,
        "platform.session",
        "MFA step-up recorded on the session",
        {"id": U, "user_id": U},
    ),
    # identity: roles and assignments
    _spec(
        "platform.identity.role.changed",
        ID,
        "platform.role",
        "role created/changed/activated/retired",
        _ID_STATUS,
    ),
    _spec(
        "platform.identity.assignment.changed",
        ID,
        "platform.role_assignment",
        "role assignment granted/approved/revoked",
        _ID_STATUS,
    ),
    # org tree (DEC-043 / DEC-048)
    _spec("platform.org.unit.created", ORG, "platform.org_unit", "org unit created", _ID),
    _spec("platform.org.unit.updated", ORG, "platform.org_unit", "org unit renamed / changed", _ID),
    _spec("platform.org.unit.moved", ORG, "platform.org_unit", "org unit moved in the tree", _ID),
    _spec("platform.org.unit.deactivated", ORG, "platform.org_unit", "org unit deactivated", _ID),
    _spec("platform.org.position.created", ORG, "platform.position", "position created", _ID),
    _spec("platform.org.position.updated", ORG, "platform.position", "position changed", _ID),
    _spec(
        "platform.org.position_assignment.created",
        ORG,
        "platform.position_assignment",
        "person assigned to a position",
        _ID,
    ),
    _spec(
        "platform.org.position_assignment.ended",
        ORG,
        "platform.position_assignment",
        "position assignment ended",
        _ID,
    ),
    # workflow
    *(
        _spec(
            f"platform.workflow.approval.{verb}",
            WF,
            "platform.approval_request",
            f"approval request {verb} (DEC-032)",
            {"id": U, "status": CODE, "resource_type": NAME, "resource_id": REF},
        )
        for verb in ("raised", "approved", "rejected", "withdrawn", "superseded", "expired")
    ),
    _spec(
        "platform.workflow.instance.changed",
        WF,
        "platform.workflow_instance",
        "workflow instance started/advanced/finished",
        _ID_STATUS,
    ),
    _spec(
        "platform.workflow.task.changed",
        WF,
        "platform.work_task",
        "work task state changed (verb = transition)",
        {"id": U, "status": CODE, "verb": KEY},
    ),
    # documents (SEC-03)
    _spec("platform.document.created", DOC, "platform.document", "document registered", _ID),
    _spec("platform.document.updated", DOC, "platform.document", "document metadata changed", _ID),
    _spec(
        "platform.document.revision.changed",
        DOC,
        "platform.document_revision",
        "revision uploaded/scanned/submitted/approved/rejected/superseded",
        {"id": U, "document_id": U, "status": CODE, "scan_status": CODE},
    ),
    _spec(
        "platform.document.object.purged",
        DOC,
        "platform.stored_object",
        "bytes of a rejected upload purged (DEC-053); hash kept",
        {"sha256": SHA},
    ),
    # parameters / dynamic fields
    _spec(
        "platform.config.parameter.defined",
        CFG,
        "platform.parameter_definition",
        "parameter definition created",
        {"key": KEY},
    ),
    *(
        _spec(
            f"platform.config.parameter.{verb}",
            CFG,
            "platform.parameter_value",
            f"parameter value {verb}",
            {"id": U, "parameter_key": KEY, "status": CODE},
        )
        for verb in ("proposed", "published", "rejected")
    ),
    _spec(
        "platform.config.field.changed",
        CFG,
        "platform.dynamic_field",
        "dynamic field definition created/changed",
        {"key": KEY, "status": CODE},
    ),
    # jobs
    _spec(
        "platform.ops.job.changed",
        OPS,
        "platform.job_run",
        "job run queued/started/cancel requested/finished",
        {"id": U, "job_type": KEY, "state": CODE},
    ),
    # integration (PHASE_00 / 00.6 framework events)
    _spec(
        "platform.integration.batch_received",
        INT,
        "platform.import_batch",
        "file received (hash only, no content)",
        {"batch_id": U, "source_code": KEY, "sha256": SHA, "byte_size": N},
    ),
    _spec(
        "platform.integration.batch_staged",
        INT,
        "platform.import_batch",
        "rows staged",
        {"batch_id": U, "source_code": KEY, "row_count": N},
    ),
    _spec(
        "platform.integration.batch_validated",
        INT,
        "platform.import_batch",
        "rows validated",
        {"batch_id": U, "source_code": KEY, "row_count": N, "error_row_count": N},
    ),
    _spec(
        "platform.integration.batch_rejected",
        INT,
        "platform.import_batch",
        "batch rejected",
        {"batch_id": U, "source_code": KEY},
    ),
    _spec(
        "platform.integration.conflict_raised",
        INT,
        "platform.conflict_item",
        "conflict queue item opened",
        {"conflict_id": U, "source_code": KEY, "kind": KEY, "batch_id": F("uuid", nullable=True)},
    ),
    _spec(
        "platform.integration.conflict_resolved",
        INT,
        "platform.conflict_item",
        "conflict queue item resolved / dismissed",
        {"conflict_id": U, "source_code": KEY, "status": CODE},
    ),
    _spec(
        "platform.integration.compensation_recorded",
        INT,
        "platform.compensation_record",
        "compensation recorded for a dead-lettered event",
        {"compensation_id": U, "event_id": U, "consumer": NAME, "outcome": CODE},
    ),
    # PHASE_02 / 02.2 Identity: serial allocation primitive (DEC-006; handoff catalogue name
    # "SerialAllocated").
    # Identifiers and versions only: no serial number, customer or code in the payload (consumers read the
    # API).
    _spec(
        "identity.serial.allocated",
        PID,
        "identity.serial",
        "serial allocated at order confirm with its snapshot v1 (gapless counter, DEC-006)",
        {"id": U, "status": CODE, "snapshot_version": N},
    ),
    # PHASE_02 / 02.3 domain engine. Identifiers, status codes, versions and counts only: no customer,
    # brand, product or representative name, no code value, no serial number (consumers read the API).
    *(
        _spec(
            f"identity.customer.{v}",
            PID,
            "identity.customer",
            f"customer {v} (in-app master data)",
            _ID_STATUS,
        )
        for v in ("created", "updated")
    ),
    *(
        _spec(
            f"identity.customer_brand.{v}",
            PID,
            "identity.customer_brand",
            f"brand of a customer {v} (DEC-058 B-A)",
            {"id": U, "customer_id": U, "status": CODE},
        )
        for v in ("created", "updated")
    ),
    _spec(
        "identity.product.created",
        PID,
        "identity.product",
        "product created; number = max of type + 1, or buckle + width for belts (DEC-005)",
        {"id": U, "product_type_id": U, "status": CODE},
    ),
    _spec(
        "identity.product.status_changed", PID, "identity.product", "product DRAFT/ACTIVE/RETIRED", _ID_STATUS
    ),
    _spec(
        "identity.style.created",
        PID,
        "identity.style",
        "style created; number = count of the product and category + 1 (DEC-005)",
        {"id": U, "product_id": U, "category_id": U, "status": CODE},
    ),
    _spec("identity.style.status_changed", PID, "identity.style", "style DRAFT/ACTIVE/RETIRED", _ID_STATUS),
    *(
        _spec(
            f"identity.style_revision.{v}",
            PID,
            "identity.style_revision",
            f"style revision {v.replace('_', ' ')}",
            {"id": U, "style_id": U, "revision_no": N, "status": CODE},
        )
        for v in ("created", "activated", "status_changed")
    ),
    *(
        _spec(
            f"identity.code_rule.{v}",
            PID,
            "identity.code_rule_revision",
            f"code rule revision {v.replace('_', ' ')} (DEC-005)",
            {"id": U, "revision_no": N, "status": CODE},
        )
        for v in (
            "created",
            "golden_cases_added",
            "submitted",
            "approved",
            "rejected",
            "activated",
            "retired",
        )
    ),
    _spec(
        "identity.product_code.reserved",
        PID,
        "identity.product_code",
        "14-digit code issued RESERVED / ERP_PENDING under the ACTIVE rule (DEC-005 B1)",
        {"id": U, "style_id": U, "rule_revision_id": U, "status": CODE, "erp_status": CODE},
    ),
    _spec(
        "identity.product_code.erp_matched",
        PID,
        "identity.product_code",
        "reserved code seen in the Rahkaran import -> ACTIVE / ERP_MATCHED (DEC-005 B1)",
        {"id": U, "status": CODE, "erp_status": CODE, "batch_id": U},
    ),
    _spec(
        "identity.serial.cancelled",
        PID,
        "identity.serial",
        "serial cancelled with its line; the number is never re-used (DEC-059)",
        _ID_STATUS,
    ),
    _spec(
        "identity.serial.snapshot_added",
        PID,
        "identity.serial",
        "next serial snapshot written by an applied change request (DEC-059)",
        {"id": U, "snapshot_version": N, "order_version": N},
    ),
    *(
        _spec(
            f"commercial.order.{v}",
            COM,
            "commercial.customer_order",
            f"customer order {v.replace('_', ' ')}",
            {"id": U, "status": CODE, "version": N},
        )
        for v in ("drafted", "draft_changed", "validated", "reopened", "released", "cancelled")
    ),
    _spec(
        "commercial.order.confirmed",
        COM,
        "commercial.customer_order",
        "order confirmed; every line got its serial in the same transaction (DEC-006 L-A, DEC-057)",
        {"id": U, "status": CODE, "version": N, "line_count": N},
    ),
    _spec(
        "commercial.order.changed",
        COM,
        "commercial.customer_order",
        "approved change request applied: new order version (DEC-059)",
        {"id": U, "status": CODE, "version": N, "change_request_id": U, "kind": CODE},
    ),
    *(
        _spec(
            f"commercial.change_request.{v}",
            COM,
            "commercial.change_request",
            f"order change request {v.replace('_', ' ')} (DEC-059)",
            {"id": U, "order_id": U, "kind": CODE, "status": CODE},
        )
        for v in (
            "created",
            "submitted",
            "withdrawn",
            "decided",
            "planning_approved",
            "planning_rejected",
            "applied",
        )
    ),
    # PHASE_02 / 02.4: external references (DEC-058; raw value never in the payload)
    *(
        _spec(
            f"identity.external_ref.{v}",
            PID,
            "identity.external_ref",
            f"external reference {v} (DEC-058; the value is not in the payload)",
            {"id": U, "target_type": KEY, "system": CODE},
        )
        for v in ("created", "ended")
    ),
)


class Catalogue:
    """Immutable event catalogue (tests build their own with synthetic specs; production uses
    :data:`CATALOGUE`)."""

    def __init__(self, specs: tuple[EventSpec, ...]) -> None:
        by_type: dict[str, EventSpec] = {}
        for s in specs:
            if s.event_type in by_type:
                raise ValueError(f"duplicate event type {s.event_type}")
            by_type[s.event_type] = s
        self._specs: Mapping[str, EventSpec] = MappingProxyType(by_type)

    def get(self, event_type: str) -> EventSpec | None:
        return self._specs.get(event_type)

    def __contains__(self, event_type: object) -> bool:
        return event_type in self._specs

    @property
    def event_types(self) -> list[str]:
        return sorted(self._specs)

    def as_dict(self) -> dict[str, Any]:
        return {t: self._specs[t].as_dict() for t in self.event_types}


CATALOGUE: Final = Catalogue(_SPECS)


def _synthetic_allowed(event_type: str) -> bool:
    from django.conf import settings

    return event_type.startswith(SYNTHETIC_TEST_PREFIX) and getattr(settings, "ALEEKHAN_ENV", "") in {
        "dev",
        "test",
    }


# ------------------------------------------------------------------------------------------- producer side
def check_emit(
    event_type: str,
    aggregate_type: str,
    schema_version: int,
    payload: Mapping[str, Any],
    *,
    catalogue: Catalogue = CATALOGUE,
) -> EventSpec | None:
    """Producer contract (see module doc). Returns the spec (None only for a synthetic test event)."""
    spec = catalogue.get(event_type)
    if spec is None:
        if _synthetic_allowed(event_type):
            return None
        raise EngineContractError(f"EVENT_NOT_IN_CATALOGUE: {event_type!r}")
    if aggregate_type != spec.aggregate_type:
        raise EngineContractError(f"EVENT_AGGREGATE_MISMATCH: {event_type} expects {spec.aggregate_type}")
    if schema_version != spec.current_version:
        raise EngineContractError(
            f"EVENT_SCHEMA_VERSION: {event_type} is emitted as v{spec.current_version}, not v{schema_version}"
        )
    errors = payload_errors(spec.versions[schema_version], payload)
    if errors:
        raise EngineContractError(f"EVENT_PAYLOAD_INVALID: {event_type} v{schema_version} {errors}")
    return spec


def provenance(producer: str) -> dict[str, str]:
    from django.conf import settings

    return {
        "producer": producer,
        "build_commit": str(getattr(settings, "ALEEKHAN_BUILD_COMMIT", "")),
        "schema_migration": SCHEMA_MIGRATION_HEAD,
    }


# ------------------------------------------------------------------------------------------- consumer side
class IncompatibleEvent(Exception):
    """A consumer cannot use an event. ``code`` is safe (stored in ``last_error``); ``permanent`` = dead
    letter at once."""

    def __init__(self, code: str, *, permanent: bool) -> None:
        super().__init__(code)
        self.code = code
        self.permanent = permanent


def admit(
    event_type: str,
    schema_version: int,
    payload: Mapping[str, Any],
    *,
    catalogue: Catalogue = CATALOGUE,
) -> tuple[int, dict[str, Any]]:
    """Consumer contract: returns ``(version, payload)`` in the *current* version (N-1 upcast to N).

    Uncatalogued types are passed through unchanged (PHASE_00 rows written outside ``uow.emit`` in tests);
    the producer side guarantees that production rows are catalogued.
    """
    spec = catalogue.get(event_type)
    body = dict(payload)
    if spec is None:
        return schema_version, body
    n = spec.current_version
    if schema_version > n:
        raise IncompatibleEvent(f"SCHEMA_VERSION_AHEAD:v{schema_version}>v{n}", permanent=False)
    if schema_version not in spec.accepted_versions:
        raise IncompatibleEvent(f"SCHEMA_VERSION_UNSUPPORTED:v{schema_version}", permanent=True)
    if payload_errors(spec.versions[schema_version], body):
        raise IncompatibleEvent(f"SCHEMA_INVALID:v{schema_version}", permanent=True)
    if schema_version < n:
        body = spec.upcasters[schema_version](body)
        if payload_errors(spec.versions[n], body):
            raise IncompatibleEvent(f"SCHEMA_UPCAST_INVALID:v{schema_version}", permanent=True)
    return n, body
