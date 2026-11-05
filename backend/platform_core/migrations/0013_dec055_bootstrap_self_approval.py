"""DEC-055 (option B, APPROVED 2026-11-05; REV-0116): bootstrap self-approval of the FIRST holder of a
business-approval role (reversible).

DEC-032 forbids self-approval, and on day one nobody holds ``platform.workflow.approval.decide``, so the first
holder of a business-approval role could never be confirmed. DEC-055 B: the owner (ACTIVE ``owner_admin``) may
approve his own role-assignment request for the first holder of such a role, once per role, with a fresh MFA
step-up (engine), a mandatory reason and the audit flag ``bootstrap_self_approval``. From the second holder on,
DEC-032 applies unchanged.

* ``platform_approval_request.bootstrap_self_approval`` (default false). CHECK ``ck_approval_request_maker_checker``
  allows decider = requester only for an APPROVED row carrying the flag; CHECK
  ``ck_approval_request_bootstrap_scope`` limits the flag to APPROVED ``platform.identity.assignment.grant`` /
  ``role_assignment`` requests.
* Trigger ``trg_approval_request_bootstrap_guard`` (rule ``ck_approval_request_bootstrap_self_approval``): only on
  the PENDING -> APPROVED update, decider = requester = grantor of the PENDING_APPROVAL assignment, decider holds an
  ACTIVE owner_admin assignment now, the role holds a business-approval permission, the role has no ACTIVE
  assignment and no earlier bootstrap-approved request (once per role); a non-empty decision note (reason).
  Serialised per role by an advisory transaction lock: two concurrent bootstrap approvals -> exactly one wins.
* ``platform_role_assignment_guard`` (0008) accepts a decider equal to the grantor/grantee only for such a
  bootstrap-approved request.
Reverse: restores the 0008 guard body, drops the trigger, the CHECKs and the column (only while no row carries
the flag - the restored CHECK would refuse such a row).
"""

from django.db import migrations, models

GUARD_SQL = (
    r"""
CREATE FUNCTION platform_approval_request_bootstrap_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    ra record;
BEGIN
    IF NOT NEW.bootstrap_self_approval THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.bootstrap_self_approval THEN
        RETURN NEW;  -- terminal row (immutable by trg_approval_request_a_terminal anyway)
    END IF;
    IF TG_OP = 'INSERT' OR OLD.status <> 'PENDING' OR NEW.status <> 'APPROVED' THEN
        RAISE EXCEPTION 'ck_approval_request_bootstrap_self_approval: only a PENDING -> APPROVED decision (DEC-055)'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.decided_by_id IS DISTINCT FROM NEW.requested_by_id OR NOT public.platform_holds_owner_admin(NEW.decided_by_id) THEN
        RAISE EXCEPTION 'ck_approval_request_bootstrap_self_approval: only the requesting owner_admin (DEC-055)'
            USING ERRCODE = 'check_violation';
    END IF;
    IF length(btrim(NEW.decision_note)) < 3 THEN
        RAISE EXCEPTION 'ck_approval_request_bootstrap_self_approval: a reason is required (DEC-055)'
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT * INTO ra FROM public.platform_role_assignment WHERE id = NEW.resource_id::uuid;
    IF ra.id IS NULL OR ra.status <> 'PENDING_APPROVAL' OR ra.granted_by_id IS DISTINCT FROM NEW.decided_by_id THEN
        RAISE EXCEPTION 'ck_approval_request_bootstrap_self_approval: no pending assignment granted by the owner (DEC-055)'
            USING ERRCODE = 'check_violation';
    END IF;
    -- once per role, serialised: concurrent bootstrap approvals of the same role -> exactly one wins
    PERFORM pg_advisory_xact_lock(hashtextextended('platform_bootstrap_self_approval:' || ra.role_id::text, 0));
    IF NOT EXISTS (SELECT 1 FROM public.platform_role_permission rp
                     JOIN public.platform_permission p ON p.action = rp.permission_action
                    WHERE rp.role_id = ra.role_id AND p.business_approval) THEN
        RAISE EXCEPTION 'ck_approval_request_bootstrap_self_approval: role holds no business-approval permission'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM public.platform_role_assignment x
                WHERE x.role_id = ra.role_id AND x.status = 'ACTIVE')
       OR EXISTS (SELECT 1 FROM public.platform_approval_request q
                    JOIN public.platform_role_assignment y ON q.resource_type = 'role_assignment'
                                                          AND y.id::text = q.resource_id
                   WHERE q.bootstrap_self_approval AND q.id <> NEW.id AND y.role_id = ra.role_id) THEN
        RAISE EXCEPTION 'ck_approval_request_bootstrap_self_approval: the role already has a holder or a bootstrap approval (DEC-055: first holder only)'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_approval_request_bootstrap_guard BEFORE INSERT OR UPDATE ON public.platform_approval_request
    FOR EACH ROW EXECUTE FUNCTION platform_approval_request_bootstrap_guard();
"""
    r"""
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
)

REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS trg_approval_request_bootstrap_guard ON public.platform_approval_request;
DROP FUNCTION IF EXISTS platform_approval_request_bootstrap_guard();
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
           OR a.decided_by_id = NEW.granted_by_id OR a.decided_by_id = NEW.user_id THEN
            RAISE EXCEPTION 'ck_role_assignment_second_approval: needs an APPROVED request decided by a second person'
                USING ERRCODE = 'check_violation', HINT = 'DEC-032: waits PENDING_APPROVAL until a second eligible person decides.';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0012_phase01_engine_rework"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="approvalrequest",
            name="ck_approval_request_maker_checker",
        ),
        migrations.AddField(
            model_name="approvalrequest",
            name="bootstrap_self_approval",
            field=models.BooleanField(db_default=False),
        ),
        migrations.AddConstraint(
            model_name="approvalrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("decided_by__isnull", True),
                    models.Q(("decided_by", models.F("requested_by")), _negated=True),
                    models.Q(("bootstrap_self_approval", True), ("status", "APPROVED")),
                    _connector="OR",
                ),
                name="ck_approval_request_maker_checker",
            ),
        ),
        migrations.AddConstraint(
            model_name="approvalrequest",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("bootstrap_self_approval", False),
                    models.Q(
                        ("action", "platform.identity.assignment.grant"),
                        ("resource_type", "role_assignment"),
                        ("status", "APPROVED"),
                    ),
                    _connector="OR",
                ),
                name="ck_approval_request_bootstrap_scope",
            ),
        ),
        migrations.RunSQL(sql=GUARD_SQL, reverse_sql=REVERSE_SQL),
    ]
