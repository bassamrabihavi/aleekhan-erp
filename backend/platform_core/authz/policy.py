"""Role/scope authorization engine (PHASE_01 / 01.3) over the APPROVED permission matrix v1.1
(DEC-049, DEC-056).

Inputs are only database rows written by reviewed migrations and audited services: ``platform_permission``
(catalogue + MFA/BA/SoD flags), ``platform_role`` / ``platform_role_permission`` (grant mode per role) and the
caller's ACTIVE, currently valid ``platform_role_assignment`` rows (scope GLOBAL / ORG_UNIT /
ORG_UNIT_SUBTREE). Holding an org position grants nothing (DEC-048); positions are used only to resolve the
caller's *own unit* for the matrix cells "own unit".

Rules (docs/security/PERMISSION_MATRIX_DRAFT.md section 1):

* **Deny by default**: no grant -> 403 ``ACCESS_DENIED`` (action level); a record outside every matching grant
  -> 404 ``NOT_FOUND`` (record level, SEC-01: out of scope == does not exist).
* Grant modes: ``SCOPE`` (record unit inside the assignment scope; records without a unit need a GLOBAL
  assignment), ``OWN`` (caller is an owner of the record: creator / assignee / requester / own session),
  ``OWN_UNIT`` (record unit is a unit where the caller currently holds a PRIMARY or ACTING position, inside
  the
  assignment scope), ``OWN_AND_OWN_UNIT`` (either). Document grants may cap the sensitivity
  (``max_sensitivity``).
* **Admin != business approval (DEC-003)**: grants coming from a TECHNICAL role never satisfy a permission
  flagged ``business_approval`` (the DB also refuses such grants; this is defence in depth). Single explicit
  exception (DEC-056, matrix v1.1): ``owner_admin`` holds ``platform.workflow.approval.decide``.
* **MFA step-up**: a permission flagged ``mfa_step_up`` needs an MFA verification younger than
  ``mfa_step_up_window_minutes`` (DEC-051: 15) - also inside the factory network while
  ``mfa_step_up_inside_network`` is true (DEC-049 item 5) -> 401 ``MFA_REQUIRED``.
* Self-assignment (DEC-003) is allowed only explicitly and is reported in :class:`Decision` so callers audit
  it.

Production wiring (01.4): ``platform_core.api.permissions.ACCESS_POLICY`` is :class:`RbacPolicy`; the session
authentication (``api/session_auth.py``) gives every request a principal that carries its :class:`Caller`
(session handle, network zone, last MFA verification).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from django.db import connection, models
from django.db.models import Q

from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.engine.errors import AccessDenied, MfaRequired, NotFound
from platform_core.engine.redaction import REDACTED
from platform_core.identity.models import (
    AssignmentStatus,
    GrantMode,
    Permission,
    RoleAssignment,
    RoleKind,
    RoleStatus,
    ScopeKind,
    User,
    UserStatus,
)
from platform_core.params.values import effective_bool, effective_minutes

SENSITIVITY_RANK: Final = {"S0": 0, "S1": 1, "S2": 2, "S3": 3}
DECIDE_GENERIC: Final = "platform.workflow.approval.decide"
OWNER_ROLE: Final = "owner_admin"


# ---------------------------------------------------------------------------------------------- caller
@dataclass(frozen=True)
class Caller:
    """An authenticated user acting through one session (built by ``identity.sessions.authenticate``)."""

    user_id: uuid.UUID
    session_id: uuid.UUID | None = None
    network_zone: str = "UNKNOWN"
    mfa_verified_at: datetime | None = None

    def context(self, request_id: uuid.UUID | None = None) -> RequestContext:
        return RequestContext(
            Actor.user(self.user_id),
            request_id=request_id,
            session_id=self.session_id,
            network_zone=self.network_zone,
        )


@dataclass(frozen=True)
class RecordScope:
    """What the policy needs to know about one record (built by the owning module)."""

    units: frozenset[uuid.UUID] = frozenset()
    owners: frozenset[uuid.UUID] = frozenset()
    sensitivity: str = ""


@dataclass(frozen=True)
class Grant:
    role_code: str
    role_kind: str
    action: str
    mode: str
    max_sensitivity: str
    scope_kind: str
    scope_unit_id: uuid.UUID | None
    assignment_id: uuid.UUID
    self_assignment: bool


@dataclass(frozen=True)
class Decision:
    allowed: bool
    grant: Grant | None = None

    @property
    def via_self_assignment(self) -> bool:
        return bool(self.grant and self.grant.self_assignment)


# ----------------------------------------------------------------------------------- pure decision logic
@dataclass(frozen=True)
class ScopeFacts:
    """Facts about the caller resolved from the DB (pure input of :func:`grant_allows`)."""

    caller_id: uuid.UUID
    own_units: frozenset[uuid.UUID] = frozenset()
    subtree: Mapping[uuid.UUID, frozenset[uuid.UUID]] = field(default_factory=dict)


def _in_assignment_scope(grant: Grant, units: frozenset[uuid.UUID], facts: ScopeFacts) -> bool:
    if grant.scope_kind == ScopeKind.GLOBAL:
        return True
    if grant.scope_unit_id is None or not units:
        return False
    if grant.scope_kind == ScopeKind.ORG_UNIT:
        return grant.scope_unit_id in units
    covered = facts.subtree.get(grant.scope_unit_id, frozenset({grant.scope_unit_id}))
    return bool(units & covered)


def grant_allows(grant: Grant, record: RecordScope, facts: ScopeFacts) -> bool:
    """Does one grant cover one record? (golden-tested against the approved matrix)."""
    if grant.max_sensitivity and record.sensitivity:
        if SENSITIVITY_RANK[record.sensitivity] > SENSITIVITY_RANK[grant.max_sensitivity]:
            return False
    in_scope = _in_assignment_scope(grant, record.units, facts)
    own = facts.caller_id in record.owners
    own_unit = in_scope and bool(record.units & facts.own_units)
    if grant.mode == GrantMode.SCOPE:
        return in_scope
    if grant.mode == GrantMode.OWN:
        return own
    if grant.mode == GrantMode.OWN_UNIT:
        return own_unit
    if grant.mode == GrantMode.OWN_AND_OWN_UNIT:
        return own or own_unit
    return False  # unknown mode: deny


# ------------------------------------------------------------------------------------------ DB lookups
def permission_flags(action: str) -> Permission:
    try:
        return Permission.objects.get(action=action)
    except Permission.DoesNotExist:
        raise AccessDenied(f"unknown action {action}") from None  # not in the catalogue: deny


def grants_for(user_id: uuid.UUID, action: str | None = None, *, at: datetime | None = None) -> list[Grant]:
    """Grants of the user's ACTIVE, currently valid assignments of ACTIVE roles (empty unless user ACTIVE)."""
    if not User.objects.filter(pk=user_id, status=UserStatus.ACTIVE).exists():
        return []
    now = at or db_now()
    qs = (
        RoleAssignment.objects.filter(
            user_id=user_id,
            status=AssignmentStatus.ACTIVE,
            role__status=RoleStatus.ACTIVE,
            valid_from__lte=now,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=now))
        .select_related("role")
    )
    out: list[Grant] = []
    for ra in qs:
        grants = ra.role.grants.all()
        if action is not None:
            grants = grants.filter(permission_id=action)
        for rp in grants:
            out.append(
                Grant(
                    role_code=ra.role.code,
                    role_kind=ra.role.kind,
                    action=rp.permission_id,
                    mode=rp.grant_mode,
                    max_sensitivity=rp.max_sensitivity,
                    scope_kind=ra.scope_kind,
                    scope_unit_id=ra.scope_unit_id,
                    assignment_id=ra.id,
                    self_assignment=bool(ra.self_assignment),
                )
            )
    return out


def effective_grants(user_id: uuid.UUID, action: str) -> list[Grant]:
    """Grants that count for ``action`` (TECHNICAL roles removed for business-approval permissions)."""
    return _effective_grants(user_id, action)


def _effective_grants(user_id: uuid.UUID, action: str) -> list[Grant]:
    perm = permission_flags(action)
    grants = grants_for(user_id, action)
    if perm.business_approval:  # DEC-003: technical/admin roles never approve business ...
        grants = [g for g in grants if counts_for_business_approval(g)]
    return grants


def counts_for_business_approval(g: Grant) -> bool:
    """DEC-003 + its single exception DEC-056 (matrix v1.1): a business-approval grant counts only from a
    BUSINESS role, or the owner's ``owner_admin`` grant of ``platform.workflow.approval.decide``. Maker !=
    checker is checked by the deciding use case and stays unchanged (DEC-032)."""
    return g.role_kind == RoleKind.BUSINESS or (g.role_code == OWNER_ROLE and g.action == DECIDE_GENERIC)


def own_units(user_id: uuid.UUID) -> frozenset[uuid.UUID]:
    from platform_core.org.models import PositionAssignment

    now = db_now()
    rows = (
        PositionAssignment.objects.filter(user_id=user_id, valid_from__lte=now)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=now))
        .values_list("position__unit_id", flat=True)
    )
    return frozenset(rows)


def subtree_of(unit_id: uuid.UUID) -> frozenset[uuid.UUID]:
    with connection.cursor() as cur:
        cur.execute(
            "WITH RECURSIVE t(id) AS (SELECT %s::uuid UNION SELECT u.id FROM platform_org_unit u "
            "JOIN t ON u.parent_id = t.id) SELECT id FROM t",
            [str(unit_id)],
        )
        return frozenset(row[0] for row in cur.fetchall())


def _facts(caller_id: uuid.UUID, grants: Iterable[Grant]) -> ScopeFacts:
    subtrees = {
        g.scope_unit_id: subtree_of(g.scope_unit_id)
        for g in grants
        if g.scope_kind == ScopeKind.ORG_UNIT_SUBTREE and g.scope_unit_id is not None
    }
    needs_units = any(g.mode in (GrantMode.OWN_UNIT, GrantMode.OWN_AND_OWN_UNIT) for g in grants)
    return ScopeFacts(caller_id, own_units(caller_id) if needs_units else frozenset(), subtrees)


# ------------------------------------------------------------------------------------------ public API
def decide(caller: Caller, action: str, record: RecordScope | None = None) -> Decision:
    grants = _effective_grants(caller.user_id, action)
    if record is None:
        return Decision(bool(grants), grants[0] if grants else None)
    facts = _facts(caller.user_id, grants)
    for g in grants:
        if grant_allows(g, record, facts):
            return Decision(True, g)
    return Decision(False)


def can(caller: Caller, action: str, record: RecordScope | None = None) -> bool:
    return decide(caller, action, record).allowed


def require_permission(caller: Caller, action: str) -> Decision:
    """Action level: 403 ``ACCESS_DENIED`` without any grant of the action."""
    decision = decide(caller, action)
    if not decision.allowed:
        raise AccessDenied()
    return decision


def require_record(caller: Caller, action: str, record: RecordScope) -> Decision:
    """Record level: 403 without the action at all, 404 ``NOT_FOUND`` if the record is outside every grant."""
    require_permission(caller, action)
    decision = decide(caller, action, record)
    if not decision.allowed:
        raise NotFound()
    return decision


def require_step_up(caller: Caller, action: str) -> None:
    """401 ``MFA_REQUIRED`` unless a fresh MFA verification exists (permission flagged ``mfa_step_up``)."""
    if not permission_flags(action).mfa_step_up:
        return
    if caller.network_zone == "INTERNAL" and not effective_bool("mfa_step_up_inside_network"):
        return
    window = effective_minutes("mfa_step_up_window_minutes")
    if caller.mfa_verified_at is None or caller.mfa_verified_at < db_now() - window:
        raise MfaRequired("a fresh MFA verification is required for this action")


def holds_role(user_id: uuid.UUID, role_code: str) -> bool:
    return any(True for _ in _assignments_of_role(user_id, role_code))


def _assignments_of_role(user_id: uuid.UUID, role_code: str) -> models.QuerySet[RoleAssignment]:
    now = db_now()
    return RoleAssignment.objects.filter(
        user_id=user_id,
        user__status=UserStatus.ACTIVE,
        role__code=role_code,
        role__status=RoleStatus.ACTIVE,
        status=AssignmentStatus.ACTIVE,
        valid_from__lte=now,
    ).filter(Q(valid_to__isnull=True) | Q(valid_to__gt=now))


def require_owner_admin(caller: Caller) -> None:
    if not holds_role(caller.user_id, OWNER_ROLE):
        raise AccessDenied()


def decider_permission(action: str) -> str:
    """Permission a decider of an approval request needs (DEC-032 / DEC-049).

    A request whose action is itself a business-approval permission (document approve, parameter publish) is
    decided by holders of that permission; any other request (e.g. ``platform.identity.assignment.grant`` for
    a
    business-approval role) by holders of ``platform.workflow.approval.decide``.
    """
    return action if permission_flags(action).business_approval else DECIDE_GENERIC


def requires_login_mfa(user_id: uuid.UUID) -> bool:
    """DEC-003 role list bound to the approved matrix (C-06/C-36): the user has a live (ACTIVE, currently
    valid) assignment of an ACTIVE role that contains at least one permission flagged MFA step-up or business
    approval (admins, managers, approvers). Evaluated also while the account is CREATED (first login)."""
    now = db_now()
    return (
        RoleAssignment.objects.filter(
            user_id=user_id,
            status=AssignmentStatus.ACTIVE,
            role__status=RoleStatus.ACTIVE,
            valid_from__lte=now,
        )
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=now))
        .filter(
            Q(role__grants__permission__mfa_step_up=True)
            | Q(role__grants__permission__business_approval=True)
        )
        .exists()
    )


# --------------------------------------------------------------------------------- list scoping (01.4)
MATCH_ALL: Final = ~Q(pk__in=[])  # a non-empty "true" (an empty Q() is dropped by Q.__or__, REV-0112)
MATCH_NONE: Final = Q(pk__in=[])


def grant_q(
    g: Grant,
    facts: ScopeFacts,
    caller_id: uuid.UUID,
    *,
    unit_field: str | None,
    owner_fields: Iterable[str],
    sensitivity_field: str | None = None,
) -> Q:
    """``Q`` of the records ONE grant covers - the queryset form of :func:`grant_allows` (REV-0112)."""
    if g.scope_kind == ScopeKind.GLOBAL:
        in_scope = MATCH_ALL
    elif unit_field is None or g.scope_unit_id is None:
        in_scope = MATCH_NONE
    elif g.scope_kind == ScopeKind.ORG_UNIT:
        in_scope = Q(**{unit_field: g.scope_unit_id})
    else:
        in_scope = Q(**{f"{unit_field}__in": list(facts.subtree.get(g.scope_unit_id, {g.scope_unit_id}))})
    own = MATCH_NONE
    for f in owner_fields:
        own = own | Q(**{f: caller_id})
    own_unit = (in_scope & Q(**{f"{unit_field}__in": list(facts.own_units)})) if unit_field else MATCH_NONE
    if g.mode == GrantMode.SCOPE:
        q = in_scope
    elif g.mode == GrantMode.OWN:
        q = own
    elif g.mode == GrantMode.OWN_UNIT:
        q = own_unit
    elif g.mode == GrantMode.OWN_AND_OWN_UNIT:
        q = own | own_unit
    else:
        return MATCH_NONE  # unknown mode: deny
    return q & sensitivity_q(g, sensitivity_field)


def sensitivity_q(g: Grant, sensitivity_field: str | None) -> Q:
    """The grant's sensitivity cap as a filter. No cap: match all. A capped grant used on a query without a
    sensitivity field matches nothing (fail closed: a cap is never silently ignored, REV-0112)."""
    if not g.max_sensitivity:
        return MATCH_ALL
    if not sensitivity_field:
        return MATCH_NONE
    cap = SENSITIVITY_RANK[g.max_sensitivity]
    allowed = [s for s, rank in SENSITIVITY_RANK.items() if rank <= cap]
    return Q(**{f"{sensitivity_field}__in": allowed}) | Q(**{sensitivity_field: ""})


def scope_q(
    caller: Caller,
    action: str,
    *,
    unit_field: str | None,
    owner_fields: Iterable[str],
    sensitivity_field: str | None = None,
) -> Q:
    """``Q`` restricting a queryset to the records the caller may see (deny: matches nothing).

    Equal, record for record, to :func:`decide` with the record scope built from the same fields (one unit
    field, owner fields, optional sensitivity field) - property-tested in ``test_phase01_authz_engine.py``.
    """
    grants = _effective_grants(caller.user_id, action)
    facts = _facts(caller.user_id, grants)
    fields = tuple(owner_fields)
    q = MATCH_NONE
    for g in grants:
        q = q | grant_q(
            g,
            facts,
            caller.user_id,
            unit_field=unit_field,
            owner_fields=fields,
            sensitivity_field=sensitivity_field,
        )
    return q


# ---------------------------------------------------------------------------------- field-level redaction
# Columns that never leave the server, whoever asks (hashes, ciphertexts, key material).
NEVER_EXPOSED: Final = frozenset(
    {"password_hash", "secret_ciphertext", "code_hash", "session_key_hash", "key_ref", "storage_key"}
)


def redact_fields(
    caller: Caller,
    data: Mapping[str, Any],
    field_rules: Mapping[str, str],
    *,
    record: RecordScope | None = None,
    drop: bool = False,
) -> dict[str, Any]:
    """Field-level redaction: ``field_rules`` maps a field to the permission needed to see it.

    Fields in :data:`NEVER_EXPOSED` are always removed; a field the caller may not see is replaced by
    ``[REDACTED]`` (or removed with ``drop=True``). Permission checks use the record scope when given.
    """
    out: dict[str, Any] = {}
    cache: dict[str, bool] = {}
    for key, value in data.items():
        if key in NEVER_EXPOSED:
            continue
        action = field_rules.get(key)
        if action is None:
            out[key] = value
            continue
        if action not in cache:
            cache[action] = can(caller, action, record)
        if cache[action]:
            out[key] = value
        elif not drop:
            out[key] = REDACTED
    return out


# ---------------------------------------------------------------------- AccessPolicy adapter (for 01.4)
RecordScopeOf = Callable[[Any], RecordScope]


class RbacPolicy:
    """``platform_core.api.permissions.AccessPolicy`` implementation (installed in 01.4).

    A principal from the session authentication carries its :class:`Caller`; any other principal (e.g. a
    synthetic test principal) is judged as a caller without session and without MFA verification.
    """

    def __init__(self, record_scope_of: RecordScopeOf) -> None:
        self._record_scope_of = record_scope_of

    @staticmethod
    def _caller(principal: Any) -> Caller:
        caller = getattr(principal, "caller", None)
        if isinstance(caller, Caller) and caller.user_id == principal.actor_id:
            return caller
        return Caller(user_id=principal.actor_id)

    def allows_action(self, principal: Any, action: str) -> bool:
        try:
            return can(self._caller(principal), action)
        except AccessDenied:  # action not in the permission catalogue: deny (403)
            return False

    def check_step_up(self, principal: Any, action: str) -> None:
        require_step_up(self._caller(principal), action)

    def allows_record(self, principal: Any, action: str, obj: Any) -> bool:
        return can(self._caller(principal), action, self._record_scope_of(obj))

    def scope_queryset[M: models.Model](
        self, principal: Any, action: str, queryset: models.QuerySet[M]
    ) -> models.QuerySet[M]:
        # generic fallback: GLOBAL scope grants see everything, anything finer is decided per module (01.4)
        caller = self._caller(principal)
        return queryset.filter(scope_q(caller, action, unit_field=None, owner_fields=()))
