"""Synthetic PHASE_01 builders. Every person/unit/position carries the label «محیط آزمایشی — داده ساختگی»
(DB CHECK ``ck_*_synthetic_label``); no real factory people, units or network ranges."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Any

from django.db import connection
from django.utils import timezone

from platform_core.documents.models import Document, DocumentRevision, StoredObject
from platform_core.identity.models import Permission, Role, RoleAssignment, User
from platform_core.org.models import OrgUnit, Position, PositionAssignment
from platform_core.params.models import ParameterDefinition, ParameterValue
from platform_core.schema_common import SYNTHETIC_LABEL
from platform_core.workflow.models import ApprovalRequest

SYN = f"({SYNTHETIC_LABEL})"


def _n() -> str:
    return secrets.token_hex(4)


def user(**over: Any) -> User:
    n = _n()
    data: dict[str, Any] = {
        "username": f"syn.user.{n}",
        "display_name": f"کاربر ساختگی {n} {SYN}",
        "account_kind": "PERSON",
        "network_policy": "ANY_WITH_MFA_OUTSIDE",
        "provenance": "SEED_SYNTHETIC",
    }
    data.update(over)
    return User.objects.create(**data)


def org_unit(parent: OrgUnit | None = None, **over: Any) -> OrgUnit:
    n = _n()
    data: dict[str, Any] = {
        "code": f"syn_unit_{n}",
        "name_fa": f"واحد ساختگی {n} {SYN}",
        "unit_type_id": "DEPARTMENT",
        "parent": parent,
        "provenance": "SEED_SYNTHETIC",
    }
    data.update(over)
    return OrgUnit.objects.create(**data)


def chain(depth: int) -> list[OrgUnit]:
    """A root plus ``depth - 1`` nested units (``depth`` levels)."""
    units = [org_unit(unit_type_id="COMPANY")]
    for _ in range(depth - 1):
        units.append(org_unit(parent=units[-1]))
    return units


def position(unit: OrgUnit, **over: Any) -> Position:
    n = _n()
    data: dict[str, Any] = {
        "unit": unit,
        "code": f"syn_pos_{n}",
        "title_fa": f"سمت ساختگی {n} {SYN}",
        "provenance": "SEED_SYNTHETIC",
    }
    data.update(over)
    return Position.objects.create(**data)


def position_assignment(pos: Position, who: User, **over: Any) -> PositionAssignment:
    data: dict[str, Any] = {"position": pos, "user": who, "kind": "PRIMARY", "reason": "synthetic test"}
    data.update(over)
    return PositionAssignment.objects.create(**data)


def role(code: str) -> Role:
    return Role.objects.get(code=code)


def approval(requested_by: User, **over: Any) -> ApprovalRequest:
    now = timezone.now()
    data: dict[str, Any] = {
        "action_id": "platform.document.approve",
        "resource_type": "document_revision",
        "resource_id": str(uuid.uuid4()),
        "resource_revision": 1,
        "requested_by": requested_by,
        "requested_at": now,
        "expires_at": now + timedelta(days=30),
    }
    data.update(over)
    return ApprovalRequest.objects.create(**data)


def assignment(who: User, role_code: str, granted_by: User | None, **over: Any) -> RoleAssignment:
    data: dict[str, Any] = {
        "user": who,
        "role": role(role_code),
        "scope_kind": "GLOBAL",
        "status": "ACTIVE",
        "granted_by": granted_by,
        "granted_via": "ADMIN" if granted_by else "CONSOLE_BOOTSTRAP",
        "reason": "synthetic test grant",
    }
    data.update(over)
    return RoleAssignment.objects.create(**data)


def stored_object(size: int = 1024, **over: Any) -> StoredObject:
    data: dict[str, Any] = {
        "storage_key": secrets.token_urlsafe(32)[:43],
        "volume": "syn_volume",
        "size_bytes": size,
        "sha256": hashlib.sha256(secrets.token_bytes(16)).hexdigest(),
        "encryption_scheme": "ENCRYPTED_VOLUME",
        "key_ref": "syn-key-1",
    }
    data.update(over)
    return StoredObject.objects.create(**data)


def document(created_by: User, **over: Any) -> Document:
    data: dict[str, Any] = {
        "document_type": "syn_drawing",
        "title_fa": f"سند ساختگی {SYN}",
        "sensitivity": "S1",
        "created_by": created_by,
    }
    data.update(over)
    return Document.objects.create(**data)


def revision(
    doc: Document, uploader: User, *, obj: StoredObject | None = None, **over: Any
) -> DocumentRevision:
    obj = obj or stored_object()
    data: dict[str, Any] = {
        "document": doc,
        "revision_no": 1,
        "stored_object": obj,
        "upload_type_id": "pdf",
        "sha256": obj.sha256,
        "size_bytes": obj.size_bytes,
        "original_name": "syn-drawing.pdf",
        "uploaded_by": uploader,
    }
    data.update(over)
    return DocumentRevision.objects.create(**data)


def ensure_parameters() -> None:
    """Re-create the seeded catalogue (permissions, parameters, unit types) after a transactional flush (race
    tests): same values as migration 0010."""
    from importlib import import_module

    seed = import_module("platform_core.migrations.0010_seed_phase01_catalogue")
    if ParameterDefinition.objects.exists():
        return
    for action, (desc, mfa, ba, sod) in seed.PERMISSIONS.items():
        Permission.objects.get_or_create(
            action=action,
            defaults={
                "module": action.split(".")[1],
                "description_fa": desc,
                "mfa_step_up": mfa,
                "business_approval": ba,
                "maker_checker": sod,
                "matrix_version": seed.MATRIX_VERSION,
                "decision_id": seed.MATRIX_DECISION,
            },
        )
    now = timezone.now() - timedelta(seconds=1)
    for key, (label, dtype, unit, module, dec, lo, hi, allowed, val) in seed.PARAMETERS.items():
        d = ParameterDefinition.objects.create(
            key=key,
            label_fa=label,
            datatype=dtype,
            unit=unit,
            owner_module=module,
            classification="OWNER_POLICY",
            decision_id=dec,
            min_value=lo,
            max_value=hi,
            allowed_values=allowed,
            provenance="MIGRATION_SEED",
        )
        ParameterValue.objects.create(
            definition=d,
            value=val,
            status="PUBLISHED",
            effective_from=now,
            decision_id=dec,
            provenance="MIGRATION_SEED",
            published_at=now,
        )
    with connection.cursor() as cur:  # unit types are FK targets of org units
        for code, name_fa, order in seed.UNIT_TYPES:
            cur.execute(
                "INSERT INTO platform_org_unit_type (code, name_fa, sort_order, decision_id, provenance) "
                "VALUES (%s, %s, %s, 'DEC-048', 'MIGRATION_SEED') ON CONFLICT DO NOTHING",
                [code, name_fa, order],
            )


class db_refuses:  # used like pytest.raises
    """``with db_refuses("ck_name"):`` - the DB refuses the statement, naming that constraint/rule."""

    def __init__(self, rule: str) -> None:
        self.rule = rule

    def __enter__(self) -> None:
        from django.db import transaction

        self._atomic = transaction.atomic()
        self._atomic.__enter__()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        from django.db import IntegrityError

        self._atomic.__exit__(exc_type, exc, tb)
        if exc_type is None:
            raise AssertionError(f"expected the database to refuse ({self.rule}), but it accepted")
        if not issubclass(exc_type, IntegrityError):
            return False
        assert self.rule in str(exc), f"expected {self.rule!r} in {exc}"
        return True
