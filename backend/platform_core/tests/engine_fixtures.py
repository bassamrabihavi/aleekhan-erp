"""Synthetic builders for the PHASE_01 / 01.3 engine tests (labelled synthetic data only; no real people,
units or network ranges: the CIDRs below are RFC 5737 / RFC 1918 documentation-style test ranges).

* :func:`person` - a synthetic user with a policy-compliant password (ACTIVE unless stated otherwise).
* :func:`give_role` - a role assignment written directly (test setup). Business-approval roles are made
  ACTIVE through a synthetic APPROVED request decided by a separate synthetic person, which is exactly what
  the
  DB guard ``ck_role_assignment_second_approval`` demands (DEC-032).
* :func:`caller` - a :class:`Caller` with or without a fresh MFA verification.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from typing import Any

from django.db import connection
from django.utils import timezone

from platform_core.authz.policy import Caller
from platform_core.engine.context import db_now
from platform_core.identity.models import Credential, Role, RoleAssignment, RolePermission, User
from platform_core.identity.passwords import hash_password
from platform_core.workflow.models import ApprovalRequest

from .phase01_factories import SYN, ensure_parameters, user

# Synthetic test credentials (not secrets), named SYN_PW_*.
SYN_PW_MAIN = "Syn-Test-Pass-1!"
SYN_PW_NEW = "New-Pass-12!"
SYN_PW_WEAK = "weak"
SYN_PW_OWNER = "Syn-Owner-Pass-2!"
SYN_PW_ZERO = "Syn-Pass-0!"
SYN_PW_WRONG = "Wrong-Pass-123!"  # 01.4 API tests: a policy-shaped but wrong password
PASSWORD = SYN_PW_MAIN
INTERNAL_CIDRS = ("10.20.0.0/16",)
VPN_CIDRS = ("10.20.99.0/24",)
INTERNAL_IP = "10.20.1.10"
VPN_IP = "10.20.99.5"
EXTERNAL_IP = "198.51.100.7"  # RFC 5737 documentation range


def person(*, status: str = "ACTIVE", password: str = PASSWORD, one_time: bool = False, **over: Any) -> User:
    u = user(status="ACTIVE" if status == "LOCKED" else status, **over)
    now = db_now()
    Credential.objects.create(
        user=u,
        password_hash=hash_password(password),
        set_at=now - timedelta(seconds=5),
        must_change=one_time,
        is_one_time=one_time,
        one_time_expires_at=now + timedelta(hours=72) if one_time else None,
        expires_at=None if one_time else now + timedelta(days=90),
    )
    if status == "LOCKED":
        User.objects.filter(pk=u.pk).update(status="LOCKED", locked_until=now + timedelta(minutes=15))
    u.refresh_from_db()
    return u


def holds_ba(role_code: str) -> bool:
    return RolePermission.objects.filter(role__code=role_code, permission__business_approval=True).exists()


def give_role(
    who: User,
    role_code: str,
    *,
    scope_kind: str = "GLOBAL",
    scope_unit: Any = None,
    granted_by: User | None = None,
    valid_to: Any = None,
) -> RoleAssignment:
    grantor = granted_by or user()
    ra = RoleAssignment.objects.create(
        user=who,
        role=Role.objects.get(code=role_code),
        scope_kind=scope_kind,
        scope_unit=scope_unit,
        status="PENDING_APPROVAL" if holds_ba(role_code) else "ACTIVE",
        granted_by=grantor,
        reason="synthetic test grant",
        valid_to=valid_to,
    )
    if holds_ba(role_code):
        decider = user()
        now = timezone.now()
        req = ApprovalRequest.objects.create(
            action_id="platform.identity.assignment.grant",
            resource_type="role_assignment",
            resource_id=str(ra.pk),
            resource_revision=1,
            requested_by=grantor,
            requested_at=now,
            expires_at=now + timedelta(days=30),
            status="APPROVED",
            decided_by=decider,
            closed_at=now,
        )
        RoleAssignment.objects.filter(pk=ra.pk).update(status="ACTIVE", approval_request=req)
        ra.refresh_from_db()
    return ra


def caller(
    who: User, *, mfa: bool = True, zone: str = "INTERNAL", session_id: uuid.UUID | None = None
) -> Caller:
    return Caller(
        user_id=who.pk,
        session_id=session_id,
        network_zone=zone,
        mfa_verified_at=db_now() if mfa else None,
    )


def with_role(role_code: str, **kw: Any) -> tuple[User, Caller]:
    u = person()
    give_role(u, role_code, **kw)
    return u, caller(u)


def network(settings: Any) -> None:
    settings.ALEEKHAN_INTERNAL_CIDRS = INTERNAL_CIDRS
    settings.ALEEKHAN_VPN_CIDRS = VPN_CIDRS


def ensure_catalogue() -> None:
    """After a transactional flush: parameters + permissions (``ensure_parameters``) + roles/grants and job
    types
    with the frozen v1.0 / 0011 / v1.1 (0014) / v1.2 (0015) values (race tests)."""
    from importlib import import_module

    from platform_core.jobs.models import JobDefinition

    ensure_parameters()
    seed = import_module("platform_core.migrations.0010_seed_phase01_catalogue")
    eng = import_module("platform_core.migrations.0011_phase01_engine")
    v11 = import_module("platform_core.migrations.0014_dec056_owner_approval_rights")
    v12 = import_module("platform_core.migrations.0015_dec056_matrix_v12")
    if not Role.objects.exists():
        roles = {
            code: Role.objects.create(
                code=code, name_fa=name, kind=kind, status="DRAFT", provenance="MIGRATION_SEED"
            )
            for code, (kind, name) in seed.ROLES.items()
        }
        for action, cells in seed.GRANTS.items():
            for code, cell in cells.items():
                mode, max_sens = cell if isinstance(cell, tuple) else (cell, "")
                RolePermission.objects.create(
                    role=roles[code], permission_id=action, grant_mode=mode, max_sensitivity=max_sens
                )
        for added in (v11.ADDED_GRANTS, v12.ADDED_GRANTS):  # matrix v1.1 / v1.2 (DEC-056 + extension)
            for action, cells in added.items():
                for code, mode in cells.items():
                    RolePermission.objects.create(role=roles[code], permission_id=action, grant_mode=mode)
        Role.objects.exclude(code=v11.OWNER).update(status="ACTIVE", matrix_version="1.0")
        Role.objects.filter(code=v11.OWNER).update(status="ACTIVE", matrix_version=v12.MATRIX_VERSION)
    with connection.cursor() as cur:
        for job_type, name_fa in seed.JOB_TYPES:
            cur.execute(
                "INSERT INTO platform_job_definition (job_type, name_fa, cancellable, protected, "
                "decision_id, provenance) VALUES (%s, %s, false, true, '', 'MIGRATION_SEED') "
                "ON CONFLICT DO NOTHING",
                [job_type, name_fa],
            )
    for job_type, name_fa in eng.HOUSEKEEPING_JOBS.items():
        JobDefinition.objects.get_or_create(
            job_type=job_type, defaults={"name_fa": name_fa, "cancellable": True, "protected": False}
        )


def unit_code() -> str:
    return f"syn_unit_{secrets.token_hex(4)}"


SYN_LABEL = SYN
