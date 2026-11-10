"""DEC-056 extension (employer 2026-11-10, REV-0125): permission matrix v1.2 (reversible, additive seed).

The owner role ``owner_admin`` (TECHNICAL) now also holds, directly:

* ``platform.document.approve`` (``SCOPE``; documents carry no org unit in PHASE_01, the owner's assignment is
  GLOBAL) - decides document revision approval requests (approve / reject);
* ``platform.config.parameter.publish`` (``SCOPE``) - publishes / rejects proposed values of **BUSINESS_RULE**
  parameters only. The engine refuses the owner's grant for TECHNICAL values (``params.service``): the
  employer extended DEC-056 to BUSINESS_RULE publish, not to TECHNICAL values (DEC-032 asks maker-checker only
  for BUSINESS_RULE, so an owner publishing his own TECHNICAL proposal would be a self-approval in effect).

Unchanged: maker != checker - the owner never decides his own request / upload / proposal (``_check_decider``,
document ``_on_approved``, the BUSINESS_RULE publisher != proposer trigger), except the DEC-055 bootstrap
approval. ``it_ops`` and ``security_auditor`` still hold no business-approval permission.

DB guards (0014): the single owner_admin exception of ``ck_role_technical_no_business_approval`` is widened from
one pair to exactly three pairs (role ``owner_admin`` with ``platform.workflow.approval.decide``,
``platform.document.approve``, ``platform.config.parameter.publish``) in ``platform_role_permission_guard``,
``platform_role_kind_guard`` and ``platform_permission_ba_guard``. The role assignment guard (0014) is unchanged
(an in-app grant of ``owner_admin`` already needs a second approver).

Same owner-only bypass as 0014 / the reverse of 0010 (grants and ``matrix_version`` of an ACTIVE role are
frozen): the schema owner disables the guard trigger for one statement inside the migration transaction; the
runtime DB role cannot (roles_check.sh).

Reverse: removes the two grants, ``owner_admin.matrix_version`` back to 1.1, restores the 0014 guard bodies
(byte-identical, so a round trip leaves an empty schema diff). Decisions the owner already took stay (audit is
append-only).
Frozen data: this file must not import application code.
"""

from typing import Any

from django.db import migrations

MATRIX_VERSION = "1.2"
PREVIOUS_MATRIX_VERSION = "1.1"
DECISION = "DEC-056"
OWNER = "owner_admin"

# action -> {role_code: grant_mode}  (cells added by matrix v1.2; v1.1 cells = 0014 ADDED_GRANTS)
ADDED_GRANTS: dict[str, dict[str, str]] = {
    "platform.document.approve": {OWNER: "SCOPE"},
    "platform.config.parameter.publish": {OWNER: "SCOPE"},
}

# The owner_admin exception of ck_role_technical_no_business_approval (v1.1 -> v1.2).
OWNER_BA_ACTIONS = (
    "platform.workflow.approval.decide",
    "platform.document.approve",
    "platform.config.parameter.publish",
)

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
    -- DEC-003; explicit exception DEC-056 (matrix v1.2): owner_admin holds exactly these three permissions
    IF r.kind = 'TECHNICAL' AND is_ba
       AND NOT (r.code = 'owner_admin' AND NEW.permission_action IN (
           'platform.workflow.approval.decide', 'platform.document.approve', 'platform.config.parameter.publish')) THEN
        RAISE EXCEPTION 'ck_role_technical_no_business_approval: TECHNICAL role cannot hold %', NEW.permission_action
            USING ERRCODE = 'check_violation',
                  HINT = 'DEC-003: admin rights are not business approval (DEC-056 v1.2: owner decide, document approve, parameter publish only).';
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
           AND NOT (NEW.code = 'owner_admin' AND p.action IN (
               'platform.workflow.approval.decide', 'platform.document.approve', 'platform.config.parameter.publish'))) THEN
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
           AND NOT (r.code = 'owner_admin' AND NEW.action IN (
               'platform.workflow.approval.decide', 'platform.document.approve', 'platform.config.parameter.publish'))) THEN
        RAISE EXCEPTION 'ck_role_technical_no_business_approval: % is held by a TECHNICAL role', NEW.action
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;
"""

# ------------------------------------------------------------------------------------------ reverse SQL
# The three guard bodies of 0014 (byte-identical copy; the role assignment guard is not touched by 0015).
REVERSE_SQL = r"""
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
"""


def _set_grants(apps: Any, schema_editor: Any, *, add: bool) -> None:
    db = schema_editor.connection.alias
    role = apps.get_model("platform_core", "Role")
    role_permission = apps.get_model("platform_core", "RolePermission")
    if not role.objects.using(db).filter(code=OWNER).exists():  # catalogue not seeded (keeps it total)
        return
    schema_editor.execute("ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard")
    for action, cells in ADDED_GRANTS.items():
        for code, mode in cells.items():
            if add:
                role_permission.objects.using(db).get_or_create(
                    role=role.objects.using(db).get(code=code),
                    permission_id=action,
                    defaults={"grant_mode": mode, "max_sensitivity": ""},
                )
            else:
                role_permission.objects.using(db).filter(role__code=code, permission_id=action).delete()
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # flush deferred FK checks before ALTER
    schema_editor.execute("ALTER TABLE platform_role_permission ENABLE TRIGGER trg_role_permission_guard")
    schema_editor.execute("ALTER TABLE platform_role DISABLE TRIGGER trg_role_kind_guard")
    role.objects.using(db).filter(code=OWNER).update(
        matrix_version=MATRIX_VERSION if add else PREVIOUS_MATRIX_VERSION
    )
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    schema_editor.execute("ALTER TABLE platform_role ENABLE TRIGGER trg_role_kind_guard")


def grant(apps: Any, schema_editor: Any) -> None:
    _set_grants(apps, schema_editor, add=True)


def ungrant(apps: Any, schema_editor: Any) -> None:
    _set_grants(apps, schema_editor, add=False)


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0014_dec056_owner_approval_rights"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
        migrations.RunPython(grant, ungrant),
    ]
