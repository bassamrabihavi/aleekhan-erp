"""DEC-056 (APPROVED 2026-11-06): owner approval rights - permission matrix v1.1 (reversible, additive seed).

The owner role ``owner_admin`` (TECHNICAL) now holds, directly:

* ``platform.workflow.approval.read`` (``SCOPE``; the owner's assignment is GLOBAL -> every approval request),
* ``platform.workflow.approval.decide`` (``SCOPE``; business decide right of generic approval requests).

Unchanged: nobody decides their own request (DEC-032 maker != checker; engine ``_check_decider`` and the DB
CHECK ``ck_approval_request_maker_checker``), except the one-time DEC-055 bootstrap approval. Every other
TECHNICAL role (it_ops, security_auditor) still holds no business-approval permission.

DB guards (0008/0013) are replaced with exactly one explicit exception - the pair
(role ``owner_admin``, permission ``platform.workflow.approval.decide``):

* ``platform_role_permission_guard`` / ``platform_role_kind_guard`` / ``platform_permission_ba_guard``
  (rule ``ck_role_technical_no_business_approval``) - any other TECHNICAL + business-approval pair is still
  refused.
* ``platform_role_assignment_guard`` (DEC-032 second approval): ``owner_admin`` now holds a business-approval
  permission, so an in-app grant of ``owner_admin`` waits PENDING_APPROVAL for a second person (DEC-032 read
  literally). Two technical consequences, both kept as narrow as possible:
  - the console bootstrap of the first owner (``CONSOLE_BOOTSTRAP``, DEC-049 item 4 / DEC-054 C) is not an
    in-app grant and needs no second approval (otherwise no owner could ever exist);
  - ``requires_second_approval`` is fixed when the assignment is created (an UPDATE keeps the old value), so an
    owner assignment that was ACTIVE before v1.1 stays valid.

Grants of an ACTIVE role are frozen (REV-0105) and ``matrix_version`` of an ACTIVE role is frozen. Like the
reverse of 0010, this migration runs as the schema owner and disables the guard trigger for one statement
inside the migration transaction; the runtime DB role is not the owner and cannot do this (roles_check.sh).

Reverse: removes the two grants, sets ``owner_admin.matrix_version`` back to 1.0 and restores the 0008 / 0013
guard bodies. Approval decisions already taken by the owner stay (audit is append-only).
Frozen data: this file must not import application code.
"""

from typing import Any

from django.db import migrations

MATRIX_VERSION = "1.1"
PREVIOUS_MATRIX_VERSION = "1.0"
DECISION = "DEC-056"
OWNER = "owner_admin"
DECIDE = "platform.workflow.approval.decide"

# action -> {role_code: grant_mode}  (cells added by matrix v1.1; all other cells = 0010 GRANTS)
ADDED_GRANTS: dict[str, dict[str, str]] = {
    "platform.workflow.approval.read": {OWNER: "SCOPE"},
    DECIDE: {OWNER: "SCOPE"},
}

# ------------------------------------------------------------------------------------------ forward SQL
FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION platform_role_permission_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    r record;
    is_ba boolean;
BEGIN
    SELECT kind, status, code INTO r FROM public.platform_role
     WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.role_id ELSE NEW.role_id END FOR SHARE;
    IF r.status <> 'DRAFT' OR (TG_OP = 'UPDATE' AND OLD.role_id <> NEW.role_id) THEN
        RAISE EXCEPTION 'ck_role_permission_draft_only: permissions of a % role change only as a new matrix version', r.status
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    SELECT business_approval INTO is_ba FROM public.platform_permission WHERE action = NEW.permission_action FOR SHARE;
    -- DEC-003; single explicit exception DEC-056: owner_admin holds platform.workflow.approval.decide
    IF r.kind = 'TECHNICAL' AND is_ba
       AND NOT (r.code = 'owner_admin' AND NEW.permission_action = 'platform.workflow.approval.decide') THEN
        RAISE EXCEPTION 'ck_role_technical_no_business_approval: TECHNICAL role cannot hold %', NEW.permission_action
            USING ERRCODE = 'check_violation', HINT = 'DEC-003: admin rights are not business approval (DEC-056: owner decide only).';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE OR REPLACE FUNCTION platform_role_kind_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status
       AND NOT ((OLD.status = 'DRAFT' AND NEW.status = 'ACTIVE') OR (OLD.status = 'ACTIVE' AND NEW.status = 'RETIRED')) THEN
        RAISE EXCEPTION 'ck_role_lifecycle: role % cannot go from % to %', OLD.code, OLD.status, NEW.status
            USING ERRCODE = 'check_violation', HINT = 'A changed permission set is a new role / new matrix version.';
    END IF;
    IF OLD.status <> 'DRAFT' AND (NEW.kind IS DISTINCT FROM OLD.kind
       OR NEW.matrix_version IS DISTINCT FROM OLD.matrix_version) THEN
        RAISE EXCEPTION 'ck_role_lifecycle: kind/matrix_version of a % role are frozen', OLD.status
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status = 'RETIRED' AND EXISTS (
        SELECT 1 FROM public.platform_role_assignment ra
         WHERE ra.role_id = NEW.id AND ra.status IN ('PENDING_APPROVAL', 'ACTIVE')) THEN
        RAISE EXCEPTION 'ck_role_retire_unassigned: role % still has live assignments', OLD.code
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.kind = 'TECHNICAL' AND EXISTS (
        SELECT 1 FROM public.platform_role_permission rp
          JOIN public.platform_permission p ON p.action = rp.permission_action
         WHERE rp.role_id = NEW.id AND p.business_approval
           AND NOT (NEW.code = 'owner_admin' AND p.action = 'platform.workflow.approval.decide')) THEN
        RAISE EXCEPTION 'ck_role_technical_no_business_approval: role % holds business-approval permissions', NEW.code
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.code IS DISTINCT FROM OLD.code THEN
        RAISE EXCEPTION 'immutable_column: platform_role.code cannot change' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE OR REPLACE FUNCTION platform_permission_ba_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF NEW.action IS DISTINCT FROM OLD.action THEN
        RAISE EXCEPTION 'immutable_column: platform_permission.action cannot change' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.business_approval AND EXISTS (
        SELECT 1 FROM public.platform_role_permission rp
          JOIN public.platform_role r ON r.id = rp.role_id
         WHERE rp.permission_action = NEW.action AND r.kind = 'TECHNICAL'
           AND NOT (r.code = 'owner_admin' AND NEW.action = 'platform.workflow.approval.decide')) THEN
        RAISE EXCEPTION 'ck_role_technical_no_business_approval: % is held by a TECHNICAL role', NEW.action
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE OR REPLACE FUNCTION platform_role_assignment_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    r record;
    needs_second boolean;
    a record;
BEGIN
    -- per-user serialisation before the GiST exclusion check (same reason as position assignments)
    PERFORM pg_advisory_xact_lock(hashtextextended('platform_role_assignment:' || NEW.user_id::text, 0));
    SELECT kind, status, code INTO r FROM public.platform_role WHERE id = NEW.role_id FOR SHARE;
    IF TG_OP = 'UPDATE' THEN
        IF NEW.user_id <> OLD.user_id OR NEW.role_id <> OLD.role_id OR NEW.scope_kind <> OLD.scope_kind
           OR NEW.scope_unit_id IS DISTINCT FROM OLD.scope_unit_id OR NEW.granted_by_id IS DISTINCT FROM OLD.granted_by_id
           OR NEW.granted_via <> OLD.granted_via OR NEW.reason <> OLD.reason OR NEW.valid_from <> OLD.valid_from THEN
            RAISE EXCEPTION 'immutable_column: role assignment identity cannot change (revoke and grant anew)'
                USING ERRCODE = 'restrict_violation';
        END IF;
    ELSIF r.status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'ck_role_assignment_role_active: role is %', r.status USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.granted_via = 'CONSOLE_BOOTSTRAP' AND r.kind <> 'TECHNICAL' THEN
        RAISE EXCEPTION 'ck_role_assignment_bootstrap_technical: console bootstrap grants TECHNICAL roles only'
            USING ERRCODE = 'check_violation';
    END IF;
    -- DEC-032: a role with a business-approval permission needs a second person (never self-approved).
    -- DEC-056: the requirement is fixed when the assignment is created; the console bootstrap of the owner
    -- (DEC-049 item 4 / DEC-054 C) is not an in-app grant.
    IF TG_OP = 'UPDATE' THEN
        NEW.requires_second_approval := OLD.requires_second_approval;
    ELSIF NEW.granted_via = 'CONSOLE_BOOTSTRAP' AND r.code = 'owner_admin' THEN
        NEW.requires_second_approval := false;
    ELSE
        SELECT EXISTS (SELECT 1 FROM public.platform_role_permission rp
                         JOIN public.platform_permission p ON p.action = rp.permission_action
                        WHERE rp.role_id = NEW.role_id AND p.business_approval) INTO needs_second;
        NEW.requires_second_approval := needs_second;
    END IF;
    IF NEW.requires_second_approval AND NEW.status = 'ACTIVE' THEN
        SELECT * INTO a FROM public.platform_approval_request WHERE id = NEW.approval_request_id;
        IF a.id IS NULL OR a.status <> 'APPROVED' OR a.action <> 'platform.identity.assignment.grant'
           OR a.resource_type <> 'role_assignment' OR a.resource_id <> NEW.id::text
           OR ((a.decided_by_id = NEW.granted_by_id OR a.decided_by_id = NEW.user_id)
               AND NOT a.bootstrap_self_approval) THEN
            RAISE EXCEPTION 'ck_role_assignment_second_approval: needs an APPROVED request decided by a second person'
                USING ERRCODE = 'check_violation', HINT = 'DEC-032: waits PENDING_APPROVAL until a second eligible person decides.';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$;
"""

# ------------------------------------------------------------------------------------------ reverse SQL
# Bodies of 0008 (role permission / role kind / permission BA guards) and 0013 (role assignment guard).
REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION platform_role_permission_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    r record;
    is_ba boolean;
BEGIN
    SELECT kind, status INTO r FROM public.platform_role
     WHERE id = CASE WHEN TG_OP = 'DELETE' THEN OLD.role_id ELSE NEW.role_id END FOR SHARE;
    IF r.status <> 'DRAFT' OR (TG_OP = 'UPDATE' AND OLD.role_id <> NEW.role_id) THEN
        RAISE EXCEPTION 'ck_role_permission_draft_only: permissions of a % role change only as a new matrix version', r.status
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    SELECT business_approval INTO is_ba FROM public.platform_permission WHERE action = NEW.permission_action FOR SHARE;
    IF r.kind = 'TECHNICAL' AND is_ba THEN
        RAISE EXCEPTION 'ck_role_technical_no_business_approval: TECHNICAL role cannot hold %', NEW.permission_action
            USING ERRCODE = 'check_violation', HINT = 'DEC-003: admin rights are not business approval.';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE OR REPLACE FUNCTION platform_role_kind_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status
       AND NOT ((OLD.status = 'DRAFT' AND NEW.status = 'ACTIVE') OR (OLD.status = 'ACTIVE' AND NEW.status = 'RETIRED')) THEN
        RAISE EXCEPTION 'ck_role_lifecycle: role % cannot go from % to %', OLD.code, OLD.status, NEW.status
            USING ERRCODE = 'check_violation', HINT = 'A changed permission set is a new role / new matrix version.';
    END IF;
    IF OLD.status <> 'DRAFT' AND (NEW.kind IS DISTINCT FROM OLD.kind
       OR NEW.matrix_version IS DISTINCT FROM OLD.matrix_version) THEN
        RAISE EXCEPTION 'ck_role_lifecycle: kind/matrix_version of a % role are frozen', OLD.status
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status = 'RETIRED' AND EXISTS (
        SELECT 1 FROM public.platform_role_assignment ra
         WHERE ra.role_id = NEW.id AND ra.status IN ('PENDING_APPROVAL', 'ACTIVE')) THEN
        RAISE EXCEPTION 'ck_role_retire_unassigned: role % still has live assignments', OLD.code
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.kind = 'TECHNICAL' AND EXISTS (
        SELECT 1 FROM public.platform_role_permission rp
          JOIN public.platform_permission p ON p.action = rp.permission_action
         WHERE rp.role_id = NEW.id AND p.business_approval) THEN
        RAISE EXCEPTION 'ck_role_technical_no_business_approval: role % holds business-approval permissions', NEW.code
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.code IS DISTINCT FROM OLD.code THEN
        RAISE EXCEPTION 'immutable_column: platform_role.code cannot change' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE OR REPLACE FUNCTION platform_permission_ba_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF NEW.action IS DISTINCT FROM OLD.action THEN
        RAISE EXCEPTION 'immutable_column: platform_permission.action cannot change' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.business_approval AND EXISTS (
        SELECT 1 FROM public.platform_role_permission rp
          JOIN public.platform_role r ON r.id = rp.role_id
         WHERE rp.permission_action = NEW.action AND r.kind = 'TECHNICAL') THEN
        RAISE EXCEPTION 'ck_role_technical_no_business_approval: % is held by a TECHNICAL role', NEW.action
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE OR REPLACE FUNCTION platform_role_assignment_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    r record;
    needs_second boolean;
    a record;
BEGIN
    -- per-user serialisation before the GiST exclusion check (same reason as position assignments)
    PERFORM pg_advisory_xact_lock(hashtextextended('platform_role_assignment:' || NEW.user_id::text, 0));
    SELECT kind, status INTO r FROM public.platform_role WHERE id = NEW.role_id FOR SHARE;
    IF TG_OP = 'UPDATE' THEN
        IF NEW.user_id <> OLD.user_id OR NEW.role_id <> OLD.role_id OR NEW.scope_kind <> OLD.scope_kind
           OR NEW.scope_unit_id IS DISTINCT FROM OLD.scope_unit_id OR NEW.granted_by_id IS DISTINCT FROM OLD.granted_by_id
           OR NEW.granted_via <> OLD.granted_via OR NEW.reason <> OLD.reason OR NEW.valid_from <> OLD.valid_from THEN
            RAISE EXCEPTION 'immutable_column: role assignment identity cannot change (revoke and grant anew)'
                USING ERRCODE = 'restrict_violation';
        END IF;
    ELSIF r.status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'ck_role_assignment_role_active: role is %', r.status USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.granted_via = 'CONSOLE_BOOTSTRAP' AND r.kind <> 'TECHNICAL' THEN
        RAISE EXCEPTION 'ck_role_assignment_bootstrap_technical: console bootstrap grants TECHNICAL roles only'
            USING ERRCODE = 'check_violation';
    END IF;
    -- DEC-032: a role with a business-approval permission needs a second person (never self-approved)
    SELECT EXISTS (SELECT 1 FROM public.platform_role_permission rp
                     JOIN public.platform_permission p ON p.action = rp.permission_action
                    WHERE rp.role_id = NEW.role_id AND p.business_approval) INTO needs_second;
    NEW.requires_second_approval := needs_second OR (TG_OP = 'UPDATE' AND OLD.requires_second_approval);
    IF NEW.requires_second_approval AND NEW.status = 'ACTIVE' THEN
        SELECT * INTO a FROM public.platform_approval_request WHERE id = NEW.approval_request_id;
        IF a.id IS NULL OR a.status <> 'APPROVED' OR a.action <> 'platform.identity.assignment.grant'
           OR a.resource_type <> 'role_assignment' OR a.resource_id <> NEW.id::text
           OR ((a.decided_by_id = NEW.granted_by_id OR a.decided_by_id = NEW.user_id)
               AND NOT a.bootstrap_self_approval) THEN
            RAISE EXCEPTION 'ck_role_assignment_second_approval: needs an APPROVED request decided by a second person'
                USING ERRCODE = 'check_violation', HINT = 'DEC-032: waits PENDING_APPROVAL until a second eligible person decides.';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$;
"""


def grant(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    role = apps.get_model("platform_core", "Role")
    role_permission = apps.get_model("platform_core", "RolePermission")
    owner = role.objects.using(db).filter(code=OWNER).first()
    if owner is None:  # catalogue not seeded (cannot happen after 0010; keeps the migration total)
        return
    # Owner-only bypass (same pattern as the reverse of 0010): grants and matrix_version of an ACTIVE role are
    # frozen; the schema owner adds the reviewed v1.1 cells inside the migration transaction.
    schema_editor.execute("ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard")
    for action, cells in ADDED_GRANTS.items():
        for code, mode in cells.items():
            role_permission.objects.using(db).get_or_create(
                role=role.objects.using(db).get(code=code),
                permission_id=action,
                defaults={"grant_mode": mode, "max_sensitivity": ""},
            )
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # flush deferred FK checks before ALTER
    schema_editor.execute("ALTER TABLE platform_role_permission ENABLE TRIGGER trg_role_permission_guard")
    schema_editor.execute("ALTER TABLE platform_role DISABLE TRIGGER trg_role_kind_guard")
    role.objects.using(db).filter(code=OWNER).update(matrix_version=MATRIX_VERSION)
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # flush deferred FK checks before ALTER
    schema_editor.execute("ALTER TABLE platform_role ENABLE TRIGGER trg_role_kind_guard")


def ungrant(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    role = apps.get_model("platform_core", "Role")
    role_permission = apps.get_model("platform_core", "RolePermission")
    schema_editor.execute("ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard")
    for action, cells in ADDED_GRANTS.items():
        role_permission.objects.using(db).filter(role__code__in=list(cells), permission_id=action).delete()
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # flush deferred FK checks before ALTER
    schema_editor.execute("ALTER TABLE platform_role_permission ENABLE TRIGGER trg_role_permission_guard")
    schema_editor.execute("ALTER TABLE platform_role DISABLE TRIGGER trg_role_kind_guard")
    role.objects.using(db).filter(code=OWNER).update(matrix_version=PREVIOUS_MATRIX_VERSION)
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # flush deferred FK checks before ALTER
    schema_editor.execute("ALTER TABLE platform_role ENABLE TRIGGER trg_role_kind_guard")


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0013_dec055_bootstrap_self_approval"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
        migrations.RunPython(grant, ungrant),
    ]
