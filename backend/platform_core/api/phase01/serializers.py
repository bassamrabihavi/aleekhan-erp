"""Response bodies of the PHASE_01 endpoints = the OpenAPI component schemas (validated by the contract
tests).

Never exposed, whoever asks: password/credential hashes, TOTP secrets, recovery-code hashes, session token
hashes, storage keys and key references (``authz.policy.NEVER_EXPOSED``); audit before/after are redacted at
write time (``engine.redaction``).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from django.db.models import F, Q

from platform_core.authz import policy as P
from platform_core.documents.models import Document, DocumentRevision
from platform_core.engine.redaction import REDACTED
from platform_core.identity.models import (
    AssignmentStatus,
    Permission,
    Role,
    RoleAssignment,
    Session,
    User,
)
from platform_core.jobs.models import JobDefinition, JobRun
from platform_core.models import AuditEvent
from platform_core.org.models import OrgUnit, Position, PositionAssignment
from platform_core.params.models import DynamicFieldDefinition, ParameterDefinition, ParameterValue
from platform_core.workflow.models import (
    ApprovalRequest,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStepEvent,
    WorkTask,
)

from .common import opt_text, sid, utc, utc_req


# ------------------------------------------------------------------------------------------- identity
def session_info(s: Session, *, current: uuid.UUID | None = None) -> dict[str, Any]:
    return {
        "session_handle": str(s.pk),
        "state": s.state,
        "user_id": str(s.user_id),
        "created_at": utc_req(s.created_at),
        "last_seen_at": utc_req(s.last_seen_at),
        "expires_at": utc_req(min(s.idle_expires_at, s.absolute_expires_at)),
        "mfa_verified_at": utc(s.mfa_verified_at),
        "network_zone": s.network_zone,
        "is_current": current is not None and s.pk == current,
    }


def user(u: User) -> dict[str, Any]:
    return {
        "user_id": str(u.pk),
        "username": u.username,
        "display_name": u.display_name,
        "status": u.status,
        "account_kind": u.account_kind,
        "network_policy": u.network_policy,
        "mfa_enrolled": bool(u.mfa_enrolled),
        "mfa_required": P.requires_login_mfa(u.pk),
        "last_login_at": utc(u.last_login_at),
        "created_at": utc_req(u.created_at),
        "created_by": sid(u.created_by_id),
        "row_version": u.row_version,
    }


def permission(p: Permission) -> dict[str, Any]:
    return {
        "action": p.action,
        "module": p.module,
        "description_fa": p.description_fa[:200],
        "sensitivity": p.sensitivity or None,
        "mfa_step_up": p.mfa_step_up,
        "business_approval": p.business_approval,
    }


def role(r: Role) -> dict[str, Any]:
    return {
        "role_id": str(r.pk),
        "code": r.code,
        "name_fa": r.name_fa,
        "status": r.status,
        "kind": r.kind,
        "permissions": sorted(r.grants.values_list("permission_id", flat=True)),
        "matrix_version": r.matrix_version or None,
        "row_version": r.row_version,
    }


def scope_of(kind: str, unit_id: uuid.UUID | None) -> dict[str, Any]:
    return {"kind": kind, "ref_id": sid(unit_id)}


def assignment(ra: RoleAssignment) -> dict[str, Any]:
    return {
        "assignment_id": str(ra.pk),
        "user_id": str(ra.user_id),
        "role_id": str(ra.role_id),
        "scope": scope_of(ra.scope_kind, ra.scope_unit_id),
        "valid_from": utc_req(ra.valid_from),
        "valid_to": utc(ra.valid_to),
        "status": ra.status,
        "granted_by": sid(ra.granted_by_id),
        "self_assignment": bool(ra.self_assignment),
        "approval_id": sid(ra.approval_request_id),
        "reason": ra.reason,
        "row_version": ra.row_version,
    }


def effective_permissions(user_id: uuid.UUID, computed_at: datetime) -> dict[str, Any]:
    flags = {p.action: p for p in Permission.objects.all()}
    grants: list[dict[str, Any]] = []
    for g in P.grants_for(user_id):
        perm = flags.get(g.action)
        if perm is None or (perm.business_approval and g.role_kind != "BUSINESS"):
            continue  # DEC-003: technical roles never carry business approval (also refused by the engine)
        grants.append(
            {
                "action": g.action,
                "scope": scope_of(g.scope_kind, g.scope_unit_id),
                "via_role": g.role_code,
                "mfa_step_up": perm.mfa_step_up,
            }
        )
    grants.sort(key=lambda x: (x["action"], x["via_role"], x["scope"]["kind"], x["scope"]["ref_id"] or ""))
    return {"user_id": str(user_id), "computed_at": utc_req(computed_at), "grants": grants[:2000]}


# ------------------------------------------------------------------------------------------------ org
def org_unit(u: OrgUnit) -> dict[str, Any]:
    return {
        "unit_id": str(u.pk),
        "code": u.code,
        "name_fa": u.name_fa,
        "unit_type": u.unit_type_id,
        "parent_unit_id": sid(u.parent_id),
        "valid_from": utc_req(u.effective_from),
        "valid_to": None,
        "status": u.status,
        "row_version": u.row_version,
    }


def position(p: Position) -> dict[str, Any]:
    return {
        "position_id": str(p.pk),
        "unit_id": str(p.unit_id),
        "code": p.code,
        "title_fa": p.title_fa,
        "reports_to_position_id": sid(p.reports_to_id),
        "is_unit_head": bool(p.is_unit_head),
        "primary_capacity": int(p.primary_capacity),
        "status": p.status,
        "row_version": p.row_version,
    }


def position_assignment(a: PositionAssignment) -> dict[str, Any]:
    return {
        "position_assignment_id": str(a.pk),
        "position_id": str(a.position_id),
        "user_id": str(a.user_id),
        "kind": a.kind,
        "valid_from": utc_req(a.valid_from),
        "valid_to": utc(a.valid_to),
        "row_version": a.row_version,
    }


# ------------------------------------------------------------------------------------------- workflow
def entity_ref(entity_type: str, entity_id: str, revision: int | None = None) -> dict[str, Any] | None:
    if not entity_type or not entity_id:
        return None
    return {"entity_type": entity_type, "entity_id": entity_id, "revision": revision}


def _blocked_by(raw: str) -> dict[str, Any] | None:
    kind, sep, ident = raw.partition(":")
    return entity_ref(kind, ident) if sep else None


def task(t: WorkTask) -> dict[str, Any]:
    ref = {"USER": t.assignee_user_id, "ORG_UNIT": t.assignee_unit_id, "POSITION": t.assignee_position_id}
    return {
        "task_id": str(t.pk),
        "subject": t.subject[:200],
        "related": entity_ref(t.related_type, t.related_id, t.related_revision),
        "status": t.status,
        "assignee": {"kind": t.assignee_kind, "ref_id": sid(ref.get(t.assignee_kind))},
        "created_by": sid(t.created_by_id),
        "created_at": utc_req(t.created_at),
        "due_at": utc(t.due_at),
        "blocked_reason": opt_text(t.blocked_reason),
        "blocked_by": _blocked_by(t.blocked_by_ref),
        "completed_by": sid(t.completed_by_id),
        "closed_by": sid(t.closed_by_id),
        "row_version": t.row_version,
    }


def approval(r: ApprovalRequest) -> dict[str, Any]:
    return {
        "approval_id": str(r.pk),
        "action": r.action_id,
        "resource": entity_ref(r.resource_type, r.resource_id, int(r.resource_revision)),
        "status": r.status,
        "requested_by": str(r.requested_by_id),
        "requested_at": utc_req(r.requested_at),
        "decided_by": sid(r.decided_by_id),
        "decided_at": utc(r.closed_at) if r.decided_by_id else None,
        "decision_note": opt_text(r.decision_note),
        "expires_at": utc(r.expires_at),
        "workflow_instance_id": sid(r.workflow_instance_id),
        "bootstrap_self_approval": bool(r.bootstrap_self_approval),
        "row_version": r.row_version,
    }


def workflow_definition(d: WorkflowDefinition) -> dict[str, Any]:
    steps = []
    for s in d.steps if isinstance(d.steps, list) else []:
        if (
            isinstance(s, dict)
            and isinstance(s.get("step_key"), str)
            and s.get("kind")
            in (
                "TASK",
                "APPROVAL",
                "SYSTEM",
            )
        ):
            rule = s.get("approver_rule")
            steps.append(
                {
                    "step_key": s["step_key"],
                    "kind": s["kind"],
                    "approver_rule": rule if isinstance(rule, str) else None,
                }
            )
    return {
        "definition_id": str(d.pk),
        "key": d.key,
        "version": d.version,
        "status": d.status,
        "decision_id": d.decision_id or None,
        "steps": steps[:50],
    }


def workflow_instance(i: WorkflowInstance) -> dict[str, Any]:
    history = []
    for e in WorkflowStepEvent.objects.filter(instance=i).order_by("seq")[:200]:
        detail = e.detail if isinstance(e.detail, dict) else {}
        history.append(
            {
                "at": utc_req(e.occurred_at),
                "from_status": str(detail.get("from_status", e.step_key))[:64],
                "to_status": str(detail.get("to_status", e.event))[:64],
                "actor_id": sid(e.actor_id),
                "reason": None,
            }
        )
    return {
        "instance_id": str(i.pk),
        "definition_id": str(i.definition_id),
        "status": i.status,
        "subject": entity_ref(i.subject_type, i.subject_id),
        "started_at": utc_req(i.started_at),
        "ended_at": utc(i.ended_at),
        "history": history,
        "row_version": i.row_version,
    }


# ---------------------------------------------------------------------------------------------- audit
def _redacted_paths(value: Any, prefix: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            out.extend(_redacted_paths(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.extend(_redacted_paths(v, f"{prefix}[{i}]"))
    elif value == REDACTED:
        out.append(prefix)
    return out


def audit_event(e: AuditEvent) -> dict[str, Any]:
    scope = json.dumps(e.scope, sort_keys=True, ensure_ascii=False) if e.scope else None
    changes = {"before": e.before, "after": e.after}
    return {
        "audit_event_id": str(e.pk),
        "occurred_at": utc_req(e.occurred_at),
        "actor_id": sid(e.actor_id),
        "request_id": sid(e.request_id),
        "action": e.action[:120],
        "resource_type": e.resource_type[:64],
        "resource_id": e.resource_id[:64],
        "scope": scope if scope is None or len(scope) <= 200 else scope[:197] + "...",
        "reason": e.reason[:500] if e.reason else None,
        "changes": changes,
        "redacted_fields": _redacted_paths(changes)[:200],
    }


# ----------------------------------------------------------------------------------------------- jobs
def job_definition(d: JobDefinition) -> dict[str, Any]:
    return {
        "job_type": d.job_type,
        "name_fa": d.name_fa,
        "cancellable": d.cancellable,
        "protected": d.protected,
    }


def job(r: JobRun) -> dict[str, Any]:
    return {
        "job_id": str(r.pk),
        "job_type": r.job_type_id,
        "state": r.state,
        "queued_at": utc_req(r.queued_at),
        "started_at": utc(r.started_at),
        "finished_at": utc(r.finished_at),
        "progress": r.progress,
        "last_checkpoint_at": utc(r.last_checkpoint_at),
        "cancel_requested_by": sid(r.cancel_requested_by_id),
        "cancel_reason": opt_text(r.cancel_reason),
        "error_code": opt_text(r.error_code),
        "row_version": r.row_version,
    }


# ------------------------------------------------------------------------------------------ documents
def document(d: Document) -> dict[str, Any]:
    return {
        "document_id": str(d.pk),
        "document_type": d.document_type,
        "title_fa": d.title_fa,
        "owner_entity": entity_ref(d.owner_entity_type, d.owner_entity_id),
        "sensitivity": d.sensitivity,
        "current_approved_revision_id": sid(d.current_approved_revision_id),
        "legacy_location_ref": opt_text(d.legacy_location_ref),
        "created_at": utc_req(d.created_at),
        "created_by": sid(d.created_by_id),
        "row_version": d.row_version,
    }


def revision(r: DocumentRevision) -> dict[str, Any]:
    approved = r.status in ("APPROVED", "SUPERSEDED") and r.decided_at is not None
    return {
        "revision_id": str(r.pk),
        "document_id": str(r.document_id),
        "revision_no": r.revision_no,
        "parent_revision_id": sid(r.parent_revision_id),
        "status": r.status,
        "scan_status": r.scan_status,
        "scan_finding": opt_text(r.scan_finding),
        "sha256": r.sha256,
        "size_bytes": r.size_bytes,
        "media_type": r.media_type_detected or "application/octet-stream",
        "original_name": r.original_name,
        "change_note": opt_text(r.change_note),
        "uploaded_by": str(r.uploaded_by_id),
        "uploaded_at": utc_req(r.uploaded_at),
        "approved_by": sid(r.decided_by_id) if approved else None,
        "approved_at": utc(r.decided_at) if approved else None,
        "row_version": r.row_version,
    }


# --------------------------------------------------------------------------------------------- config
def typed_value(datatype: str, raw: str) -> dict[str, Any]:
    if datatype == "BOOLEAN":
        return {"datatype": datatype, "value": raw.lower() == "true"}
    return {"datatype": datatype, "value": raw}


def parameter_value(pv: ParameterValue) -> dict[str, Any]:
    return {
        "value_revision_id": str(pv.pk),
        "value": typed_value(pv.definition.datatype, pv.value),
        "status": pv.status,
        "effective_from": utc_req(pv.effective_from),
        "proposed_by": sid(pv.proposed_by_id),
        "proposed_at": utc_req(pv.proposed_at),
        "published_by": sid(pv.published_by_id),
        "published_at": utc(pv.published_at),
        "approval_id": sid(pv.approval_request_id),
    }


def active_value(d: ParameterDefinition, now: datetime) -> ParameterValue | None:
    """The value in force at ``now`` - the rule of ``platform_param_value_at`` (migration 0012): PUBLISHED, or
    SUPERSEDED after it really was in force; newest ``effective_from`` not after ``now``."""
    return (
        ParameterValue.objects.select_related("definition")
        .filter(definition=d, effective_from__lte=now)
        .filter(Q(status="PUBLISHED") | Q(status="SUPERSEDED", superseded_at__gt=F("effective_from")))
        .order_by("-effective_from")
        .first()
    )


def parameter(d: ParameterDefinition, now: datetime) -> dict[str, Any]:
    current = active_value(d, now)
    return {
        "parameter_key": d.key,
        "label_fa": d.label_fa,
        "datatype": d.datatype,
        "owner_module": d.owner_module,
        "classification": d.classification,
        "decision_id": d.decision_id or None,
        "active_value": parameter_value(current) if current is not None else None,
        "row_version": d.row_version,
    }


def dynamic_field(f: DynamicFieldDefinition) -> dict[str, Any]:
    return {
        "field_key": f.field_key,
        "entity_scope": f.entity_scope,
        "label_fa": f.label_fa,
        "datatype": f.datatype,
        "status": f.status,
        "security_class": f.security_class,
        "help_fa": opt_text(f.help_fa),
        "row_version": f.row_version,
    }


def live_assignments(user_id: uuid.UUID) -> list[RoleAssignment]:
    return list(
        RoleAssignment.objects.filter(
            user_id=user_id, status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.PENDING_APPROVAL]
        ).order_by("created_at", "id")[:100]
    )
