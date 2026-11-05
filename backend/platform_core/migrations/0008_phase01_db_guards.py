"""PHASE_01 / 01.2 database guards (reversible RunSQL). Design: docs/db/ERD.md section "PHASE_01 guards".

Everything here is defence in depth under the 01.3 engine: the database refuses states that must never exist,
even if application code is wrong or the app role is misused. All functions run with a fixed
``search_path`` and qualify tables with ``public.``. Errors: immutability/append-only -> SQLSTATE 23001
(restrict_violation), invariant -> 23514 (check_violation), overlap -> 23P01 (exclusion_violation); all map to
django.db.IntegrityError. The constraint/rule name is always in the message.

1. ``btree_gist`` (trusted extension) + exclusion constraints (race-safe, no read-then-write):
   ``ex_role_assignment_no_overlap``, ``ex_position_assignment_one_primary`` (DEC-048: one primary position per
   person at any instant), ``ex_position_assignment_no_duplicate``, ``ex_org_unit_history_no_overlap``,
   ``ex_position_history_no_overlap``. Writers of role/position assignments take a per-user advisory
   transaction lock first, so concurrent losers get exclusion_violation instead of a deadlock; history rows
   are written under the tree locks of their unit/position triggers.
2. Row version: ``platform_touch_row`` (0002) on tables with created_at; ``platform_bump_row`` on the others.
3. Append-only: password history, workflow step events, audit integrity runs (``platform_reject_mutation``);
   login attempts (UPDATE rejected; DELETE only after the DEC-032 retention parameter); history tables and
   break-glass usage / stored objects (only NULL -> value on closing columns).
4. Terminal rows immutable (``platform_reject_terminal_update``): session, MFA factor, role assignment, approval
   request, work task, workflow instance, job run, document revision, parameter value.
5. Invariants: TECHNICAL role never holds a business-approval permission (DEC-003); role grants only while the
   role is DRAFT; DEC-032 second approval for role assignments of BA roles (decider != grantor != assignee);
   console bootstrap only for TECHNICAL roles; org tree acyclic + depth <= ``org_tree_max_depth`` (DEC-048) +
   no ACTIVE child under an INACTIVE parent, serialised by an advisory lock; reports-to acyclic; effective-dated
   history written by trigger, never back-dated; protected / non-cancellable jobs cannot be cancelled;
   document content immutable, size <= ``document_upload_max_bytes`` (DEC-053) and equal to its stored object;
   approved revision only -> SUPERSEDED; parameter values typed and bounded, published values immutable,
   BUSINESS_RULE publisher != proposer (DEC-032); TOTP replay guard (last_used_step monotonic).
6. ``platform_param_value(key)`` / ``platform_param_int(key)``: value effective now (raises if none) - the
   numbers of DEC-048/051/053/032 live in platform_parameter_value, never in this SQL. The runtime role needs
   EXECUTE on these two (ops/db/grants.sql); the history writers are SECURITY DEFINER (fixed search_path) so the
   runtime role needs no write privilege on the history tables.
"""

from django.db import migrations

NIL_UUID = "'00000000-0000-0000-0000-000000000000'::uuid"

TOUCH_WITH_CREATED = (
    "user",
    "credential",
    "mfa_factor",
    "session",
    "role",
    "role_assignment",
    "org_unit_type",
    "org_unit",
    "position",
    "position_assignment",
    "workflow_definition",
    "work_task",
    "document",
    "parameter_definition",
    "dynamic_field_definition",
    "job_definition",
)
TOUCH_WITHOUT_CREATED = (
    "workflow_instance",
    "approval_request",
    "document_revision",
    "parameter_value",
    "job_run",
)
APPEND_ONLY = ("password_history", "workflow_step_event", "audit_integrity_run")
TERMINAL = {
    "session": ("state", "EXPIRED", "REVOKED", "LOGGED_OUT"),
    "mfa_factor": ("status", "REVOKED"),
    "role_assignment": ("status", "EXPIRED", "REVOKED"),
    "approval_request": ("status", "APPROVED", "REJECTED", "WITHDRAWN", "SUPERSEDED", "EXPIRED"),
    "work_task": ("status", "CLOSED", "CANCELLED"),
    "workflow_instance": ("status", "COMPLETED", "CANCELLED", "FAILED"),
    "job_run": ("state", "CANCELLED", "SUCCEEDED", "FAILED"),
    "document_revision": ("status", "REJECTED", "SUPERSEDED"),
    "parameter_value": ("status", "SUPERSEDED", "REJECTED"),
}


def _touch_sql() -> tuple[str, str]:
    fwd, rev = [], []
    for t in TOUCH_WITH_CREATED:
        fwd.append(
            f"CREATE TRIGGER trg_{t}_touch BEFORE UPDATE ON public.platform_{t} "
            "FOR EACH ROW EXECUTE FUNCTION platform_touch_row();"
        )
        rev.append(f"DROP TRIGGER IF EXISTS trg_{t}_touch ON public.platform_{t};")
    for t in TOUCH_WITHOUT_CREATED:
        fwd.append(
            f"CREATE TRIGGER trg_{t}_touch BEFORE UPDATE ON public.platform_{t} "
            "FOR EACH ROW EXECUTE FUNCTION platform_bump_row();"
        )
        rev.append(f"DROP TRIGGER IF EXISTS trg_{t}_touch ON public.platform_{t};")
    for t in APPEND_ONLY:
        fwd.append(
            f"CREATE TRIGGER trg_{t}_append_only BEFORE UPDATE OR DELETE ON public.platform_{t} "
            "FOR EACH ROW EXECUTE FUNCTION platform_reject_mutation();"
        )
        rev.append(f"DROP TRIGGER IF EXISTS trg_{t}_append_only ON public.platform_{t};")
    for t, (col, *states) in TERMINAL.items():
        args = ", ".join(f"'{a}'" for a in (col, *states))
        # "a_" prefix: fires before the touch trigger (BEFORE triggers run in name order)
        fwd.append(
            f"CREATE TRIGGER trg_{t}_a_terminal BEFORE UPDATE ON public.platform_{t} "
            f"FOR EACH ROW EXECUTE FUNCTION platform_reject_terminal_update({args});"
        )
        rev.append(f"DROP TRIGGER IF EXISTS trg_{t}_a_terminal ON public.platform_{t};")
    return "\n".join(fwd), "\n".join(reversed(rev))


TOUCH_FWD, TOUCH_REV = _touch_sql()

FUNCTIONS_SQL = r"""
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ------------------------------------------------------------------------------------------ generic
CREATE FUNCTION platform_bump_row() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    NEW.row_version := OLD.row_version + 1;
    NEW.updated_at := statement_timestamp();
    RETURN NEW;
END;
$fn$;

-- TG_ARGV[0] = state column, TG_ARGV[1..] = terminal states: a row in a terminal state never changes.
CREATE FUNCTION platform_reject_terminal_update() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    old_state text := to_jsonb(OLD) ->> TG_ARGV[0];
BEGIN
    IF old_state = ANY (TG_ARGV[1:TG_NARGS - 1]) THEN
        RAISE EXCEPTION 'terminal_immutable: % row in terminal state % cannot change', TG_TABLE_NAME, old_state
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

-- Columns listed in TG_ARGV may only go from NULL to a value, once; every other column is immutable.
CREATE FUNCTION platform_close_once_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    o jsonb := to_jsonb(OLD);
    n jsonb := to_jsonb(NEW);
    col text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'append_only: % rows cannot be deleted', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
    END IF;
    FOREACH col IN ARRAY TG_ARGV LOOP
        IF o -> col <> 'null'::jsonb AND (n -> col) IS DISTINCT FROM (o -> col) THEN
            RAISE EXCEPTION 'append_only: %.% is already set', TG_TABLE_NAME, col USING ERRCODE = 'restrict_violation';
        END IF;
        o := o - col;
        n := n - col;
    END LOOP;
    IF o IS DISTINCT FROM n THEN
        RAISE EXCEPTION 'append_only: % rows are immutable except closing columns', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

-- TG_ARGV = immutable columns.
CREATE FUNCTION platform_immutable_columns() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    col text;
BEGIN
    FOREACH col IN ARRAY TG_ARGV LOOP
        IF (to_jsonb(NEW) -> col) IS DISTINCT FROM (to_jsonb(OLD) -> col) THEN
            RAISE EXCEPTION 'immutable_column: %.% cannot change', TG_TABLE_NAME, col
                USING ERRCODE = 'restrict_violation';
        END IF;
    END LOOP;
    RETURN NEW;
END;
$fn$;

-- ------------------------------------------------------------------------------------------ parameters
-- Value effective now: latest PUBLISHED/SUPERSEDED revision with effective_from <= now.
CREATE FUNCTION platform_param_value(p_key text) RETURNS text
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    v text;
BEGIN
    SELECT pv.value INTO v
      FROM public.platform_parameter_value pv
     WHERE pv.parameter_key = p_key
       AND pv.status IN ('PUBLISHED', 'SUPERSEDED')
       AND pv.effective_from <= statement_timestamp()
     ORDER BY pv.effective_from DESC
     LIMIT 1;
    IF v IS NULL THEN
        RAISE EXCEPTION 'parameter_missing: parameter % has no effective value', p_key
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN v;
END;
$fn$;

CREATE FUNCTION platform_param_int(p_key text) RETURNS bigint
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $fn$
    SELECT public.platform_param_value(p_key)::bigint;
$fn$;

CREATE FUNCTION platform_parameter_value_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    d record;
    num numeric;
BEGIN
    SELECT * INTO d FROM public.platform_parameter_definition WHERE key = NEW.parameter_key;
    IF TG_OP = 'UPDATE' THEN
        IF NEW.parameter_key IS DISTINCT FROM OLD.parameter_key OR NEW.provenance IS DISTINCT FROM OLD.provenance
           OR NEW.proposed_by_id IS DISTINCT FROM OLD.proposed_by_id OR NEW.proposed_at IS DISTINCT FROM OLD.proposed_at THEN
            RAISE EXCEPTION 'immutable_column: parameter value identity cannot change' USING ERRCODE = 'restrict_violation';
        END IF;
        IF OLD.status <> 'DRAFT' AND (NEW.value IS DISTINCT FROM OLD.value
           OR NEW.effective_from IS DISTINCT FROM OLD.effective_from
           OR NEW.decision_id IS DISTINCT FROM OLD.decision_id) THEN
            RAISE EXCEPTION 'immutable_column: parameter value is frozen once proposed (new revision instead)'
                USING ERRCODE = 'restrict_violation';
        END IF;
        IF OLD.status = 'PUBLISHED' AND (NEW.status NOT IN ('PUBLISHED', 'SUPERSEDED')
           OR NEW.published_by_id IS DISTINCT FROM OLD.published_by_id
           OR NEW.published_at IS DISTINCT FROM OLD.published_at) THEN
            RAISE EXCEPTION 'immutable_column: a published value can only become SUPERSEDED'
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;
    -- datatype / bounds (canonical strings; decimals never floats)
    IF d.datatype = 'INTEGER' OR d.datatype = 'DURATION' THEN
        IF NEW.value !~ '^-?[0-9]{1,18}$' THEN
            RAISE EXCEPTION 'ck_parameter_value_type: % is not an integer', NEW.parameter_key USING ERRCODE = 'check_violation';
        END IF;
        num := NEW.value::numeric;
    ELSIF d.datatype = 'DECIMAL' THEN
        IF NEW.value !~ '^-?[0-9]{1,16}(\.[0-9]{1,4})?$' THEN
            RAISE EXCEPTION 'ck_parameter_value_type: % is not a decimal', NEW.parameter_key USING ERRCODE = 'check_violation';
        END IF;
        num := NEW.value::numeric;
    ELSIF d.datatype = 'BOOLEAN' THEN
        IF NEW.value NOT IN ('true', 'false') THEN
            RAISE EXCEPTION 'ck_parameter_value_type: % is not true/false', NEW.parameter_key USING ERRCODE = 'check_violation';
        END IF;
    ELSIF d.datatype = 'DATE' THEN
        BEGIN
            IF NEW.value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' OR NEW.value::date::text <> NEW.value THEN
                RAISE EXCEPTION 'not a date';
            END IF;
        EXCEPTION WHEN others THEN
            RAISE EXCEPTION 'ck_parameter_value_type: % is not a date', NEW.parameter_key USING ERRCODE = 'check_violation';
        END;
    ELSIF d.datatype = 'ENUM' THEN
        IF NOT (d.allowed_values ? NEW.value) THEN
            RAISE EXCEPTION 'ck_parameter_value_type: % not in allowed values', NEW.parameter_key USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.value = '' THEN
        RAISE EXCEPTION 'ck_parameter_value_type: % is empty', NEW.parameter_key USING ERRCODE = 'check_violation';
    END IF;
    IF num IS NOT NULL AND ((d.min_value IS NOT NULL AND num < d.min_value) OR (d.max_value IS NOT NULL AND num > d.max_value)) THEN
        RAISE EXCEPTION 'ck_parameter_value_bounds: % out of bounds', NEW.parameter_key USING ERRCODE = 'check_violation';
    END IF;
    IF d.classification <> 'TECHNICAL' AND NEW.decision_id = '' THEN
        RAISE EXCEPTION 'ck_parameter_value_decision: % value needs a decision id', NEW.parameter_key
            USING ERRCODE = 'check_violation';
    END IF;
    -- DEC-032: BUSINESS_RULE publish is maker-checker (never self-published)
    IF d.classification = 'BUSINESS_RULE' AND NEW.status IN ('PUBLISHED', 'SUPERSEDED')
       AND (NEW.published_by_id IS NULL OR NEW.published_by_id = NEW.proposed_by_id) THEN
        RAISE EXCEPTION 'ck_parameter_value_maker_checker: business rule % needs a second person to publish', NEW.parameter_key
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_parameter_value_guard BEFORE INSERT OR UPDATE ON public.platform_parameter_value
    FOR EACH ROW EXECUTE FUNCTION platform_parameter_value_guard();
CREATE TRIGGER trg_parameter_definition_immutable BEFORE UPDATE ON public.platform_parameter_definition
    FOR EACH ROW EXECUTE FUNCTION platform_immutable_columns(
        'key', 'datatype', 'unit', 'owner_module', 'classification', 'decision_id', 'min_value', 'max_value',
        'allowed_values', 'provenance', 'created_at', 'created_by_id');
CREATE TRIGGER trg_dynamic_field_definition_immutable BEFORE UPDATE ON public.platform_dynamic_field_definition
    FOR EACH ROW EXECUTE FUNCTION platform_immutable_columns('id', 'field_key', 'entity_scope', 'created_at', 'created_by_id');

-- ------------------------------------------------------------------------------------------ roles
CREATE FUNCTION platform_role_permission_guard() RETURNS trigger
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

CREATE TRIGGER trg_role_permission_guard BEFORE INSERT OR UPDATE OR DELETE ON public.platform_role_permission
    FOR EACH ROW EXECUTE FUNCTION platform_role_permission_guard();

CREATE FUNCTION platform_role_kind_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
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

CREATE TRIGGER trg_role_kind_guard BEFORE UPDATE ON public.platform_role
    FOR EACH ROW EXECUTE FUNCTION platform_role_kind_guard();

CREATE FUNCTION platform_permission_ba_guard() RETURNS trigger
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

CREATE TRIGGER trg_permission_ba_guard BEFORE UPDATE ON public.platform_permission
    FOR EACH ROW EXECUTE FUNCTION platform_permission_ba_guard();

CREATE FUNCTION platform_role_assignment_guard() RETURNS trigger
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

CREATE TRIGGER trg_role_assignment_guard BEFORE INSERT OR UPDATE ON public.platform_role_assignment
    FOR EACH ROW EXECUTE FUNCTION platform_role_assignment_guard();

ALTER TABLE public.platform_role_assignment ADD CONSTRAINT ex_role_assignment_no_overlap
    EXCLUDE USING gist (
        user_id WITH =, role_id WITH =, scope_kind WITH =,
        (COALESCE(scope_unit_id, '00000000-0000-0000-0000-000000000000'::uuid)) WITH =,
        tstzrange(valid_from, valid_to, '[)') WITH &&
    ) WHERE (status IN ('PENDING_APPROVAL', 'ACTIVE'));

-- ------------------------------------------------------------------------------------------ identity
CREATE FUNCTION platform_mfa_factor_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF NEW.user_id <> OLD.user_id OR NEW.method <> OLD.method THEN
        RAISE EXCEPTION 'immutable_column: MFA factor owner/method cannot change' USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.last_used_step IS NOT NULL AND (NEW.last_used_step IS NULL OR NEW.last_used_step <= OLD.last_used_step)
       AND NEW.last_used_step IS DISTINCT FROM OLD.last_used_step THEN
        RAISE EXCEPTION 'ck_mfa_factor_replay: TOTP time step must increase (replay guard)' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_mfa_factor_guard BEFORE UPDATE ON public.platform_mfa_factor
    FOR EACH ROW EXECUTE FUNCTION platform_mfa_factor_guard();
CREATE TRIGGER trg_recovery_code_use_once BEFORE UPDATE ON public.platform_recovery_code
    FOR EACH ROW EXECUTE FUNCTION platform_close_once_only('used_at');
CREATE TRIGGER trg_session_immutable BEFORE UPDATE ON public.platform_session
    FOR EACH ROW EXECUTE FUNCTION platform_immutable_columns('id', 'user_id', 'created_at');
CREATE TRIGGER trg_credential_immutable BEFORE UPDATE ON public.platform_credential
    FOR EACH ROW EXECUTE FUNCTION platform_immutable_columns('user_id', 'created_at');
CREATE TRIGGER trg_user_immutable BEFORE UPDATE ON public.platform_user
    FOR EACH ROW EXECUTE FUNCTION platform_immutable_columns('id', 'is_break_glass', 'provenance', 'created_at', 'created_by_id');

-- login events: never updated; deleted only by the retention purge after DEC-032 (2 years) has passed
CREATE FUNCTION platform_login_attempt_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'append_only: platform_login_attempt rows cannot be updated' USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.occurred_at >= statement_timestamp()
           - make_interval(months => public.platform_param_int('retention_login_events_months')::int) THEN
        RAISE EXCEPTION 'append_only: login event is inside the retention period (DEC-032)'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN OLD;
END;
$fn$;

CREATE TRIGGER trg_login_attempt_guard BEFORE UPDATE OR DELETE ON public.platform_login_attempt
    FOR EACH ROW EXECUTE FUNCTION platform_login_attempt_guard();

CREATE FUNCTION platform_break_glass_usage_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.platform_user WHERE id = NEW.user_id AND is_break_glass) THEN
        RAISE EXCEPTION 'ck_break_glass_usage_account: user is not the break-glass account (DEC-054)'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_break_glass_usage_account BEFORE INSERT ON public.platform_break_glass_usage
    FOR EACH ROW EXECUTE FUNCTION platform_break_glass_usage_guard();
CREATE TRIGGER trg_break_glass_usage_append_only BEFORE UPDATE OR DELETE ON public.platform_break_glass_usage
    FOR EACH ROW EXECUTE FUNCTION platform_close_once_only('alerted_at', 'ended_at', 'password_rotated_at');

-- ------------------------------------------------------------------------------------------ org tree
CREATE FUNCTION platform_effective_from_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.effective_from = OLD.effective_from
       AND (to_jsonb(NEW) - 'effective_from' - 'updated_at' - 'updated_by_id' - 'row_version')
           IS DISTINCT FROM (to_jsonb(OLD) - 'effective_from' - 'updated_at' - 'updated_by_id' - 'row_version') THEN
        NEW.effective_from := statement_timestamp();
    END IF;
    IF NEW.effective_from > statement_timestamp() THEN
        RAISE EXCEPTION 'ck_effective_from_not_future: % changes take effect now or in the past', TG_TABLE_NAME
            USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.effective_from < OLD.effective_from THEN
        RAISE EXCEPTION 'ck_effective_from_monotonic: % history is never back-dated', TG_TABLE_NAME
            USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.code IS DISTINCT FROM OLD.code THEN
        RAISE EXCEPTION 'immutable_column: %.code cannot change', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE FUNCTION platform_org_unit_tree_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    max_depth bigint := public.platform_param_int('org_tree_max_depth');
    parent_status text;
    is_cycle boolean := false;
    parent_depth int := 0;
    below int := 0;
BEGIN
    -- serialise all tree changes: two concurrent moves can never build a cycle together
    PERFORM pg_advisory_xact_lock(hashtext('platform_org_unit_tree'));
    IF TG_OP = 'INSERT' OR NEW.unit_type_code IS DISTINCT FROM OLD.unit_type_code THEN
        IF NOT EXISTS (SELECT 1 FROM public.platform_org_unit_type WHERE code = NEW.unit_type_code AND is_active) THEN
            RAISE EXCEPTION 'ck_org_unit_type_active: unit type % is not active', NEW.unit_type_code
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF NEW.parent_id IS NOT NULL THEN
        SELECT status INTO parent_status FROM public.platform_org_unit WHERE id = NEW.parent_id;
        IF NEW.status = 'ACTIVE' AND parent_status <> 'ACTIVE' THEN
            RAISE EXCEPTION 'ck_org_unit_parent_active: an ACTIVE unit needs an ACTIVE parent' USING ERRCODE = 'check_violation';
        END IF;
        WITH RECURSIVE anc(id, parent_id, depth) AS (
            SELECT u.id, u.parent_id, 1 FROM public.platform_org_unit u WHERE u.id = NEW.parent_id
            UNION ALL
            SELECT u.id, u.parent_id, a.depth + 1
              FROM public.platform_org_unit u JOIN anc a ON u.id = a.parent_id
             WHERE a.depth <= max_depth + 1 AND a.id <> NEW.id
        )
        SELECT coalesce(bool_or(id = NEW.id), false), coalesce(max(depth), 0) INTO is_cycle, parent_depth FROM anc;
        IF is_cycle THEN
            RAISE EXCEPTION 'ck_org_unit_acyclic: moving % under % would create a cycle', NEW.code, NEW.parent_id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF TG_OP = 'UPDATE' THEN
        WITH RECURSIVE sub(id, h) AS (
            SELECT u.id, 1 FROM public.platform_org_unit u WHERE u.parent_id = NEW.id
            UNION ALL
            SELECT u.id, s.h + 1 FROM public.platform_org_unit u JOIN sub s ON u.parent_id = s.id WHERE s.h <= max_depth
        )
        SELECT coalesce(max(h), 0) INTO below FROM sub;
        IF NEW.status = 'INACTIVE' AND OLD.status = 'ACTIVE' THEN
            IF EXISTS (SELECT 1 FROM public.platform_org_unit WHERE parent_id = NEW.id AND status = 'ACTIVE')
               OR EXISTS (SELECT 1 FROM public.platform_position WHERE unit_id = NEW.id AND status = 'ACTIVE') THEN
                RAISE EXCEPTION 'ck_org_unit_deactivate_empty: unit still has ACTIVE sub-units or positions'
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;
    END IF;
    IF parent_depth + 1 + below > max_depth THEN
        RAISE EXCEPTION 'ck_org_unit_max_depth: tree depth % exceeds org_tree_max_depth % (DEC-048)',
            parent_depth + 1 + below, max_depth USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

-- SECURITY DEFINER (owner): the runtime role has no INSERT/UPDATE on the history table at all (ops/db/grants.sql)
CREATE FUNCTION platform_org_unit_history_writer() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.code = OLD.code AND NEW.name_fa = OLD.name_fa
       AND NEW.unit_type_code = OLD.unit_type_code AND NEW.parent_id IS NOT DISTINCT FROM OLD.parent_id
       AND NEW.status = OLD.status THEN
        RETURN NULL;
    END IF;
    UPDATE public.platform_org_unit_history SET valid_to = NEW.effective_from
     WHERE unit_id = NEW.id AND valid_to IS NULL;
    INSERT INTO public.platform_org_unit_history
        (unit_id, unit_row_version, valid_from, valid_to, code, name_fa, unit_type_code, parent_id, status,
         changed_by_id, recorded_at)
    VALUES (NEW.id, NEW.row_version, NEW.effective_from, NULL, NEW.code, NEW.name_fa, NEW.unit_type_code,
            NEW.parent_id, NEW.status, COALESCE(NEW.updated_by_id, NEW.created_by_id), statement_timestamp());
    RETURN NULL;
END;
$fn$;

CREATE TRIGGER trg_org_unit_effective BEFORE INSERT OR UPDATE ON public.platform_org_unit
    FOR EACH ROW EXECUTE FUNCTION platform_effective_from_guard();
CREATE TRIGGER trg_org_unit_tree_guard BEFORE INSERT OR UPDATE ON public.platform_org_unit
    FOR EACH ROW EXECUTE FUNCTION platform_org_unit_tree_guard();
CREATE TRIGGER trg_org_unit_history AFTER INSERT OR UPDATE ON public.platform_org_unit
    FOR EACH ROW EXECUTE FUNCTION platform_org_unit_history_writer();
CREATE TRIGGER trg_org_unit_history_append_only BEFORE UPDATE OR DELETE ON public.platform_org_unit_history
    FOR EACH ROW EXECUTE FUNCTION platform_close_once_only('valid_to');
ALTER TABLE public.platform_org_unit_history ADD CONSTRAINT ex_org_unit_history_no_overlap
    EXCLUDE USING gist (unit_id WITH =, tstzrange(valid_from, valid_to, '[)') WITH &&);

CREATE FUNCTION platform_position_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    is_cycle boolean := false;
    target_status text;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('platform_position_tree'));
    IF NEW.status = 'ACTIVE' AND NOT EXISTS (
        SELECT 1 FROM public.platform_org_unit WHERE id = NEW.unit_id AND status = 'ACTIVE') THEN
        RAISE EXCEPTION 'ck_position_unit_active: an ACTIVE position needs an ACTIVE unit' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.reports_to_id IS NOT NULL THEN
        SELECT status INTO target_status FROM public.platform_position WHERE id = NEW.reports_to_id;
        IF NEW.status = 'ACTIVE' AND target_status <> 'ACTIVE' THEN
            RAISE EXCEPTION 'ck_position_reports_to_active: reports-to target is not ACTIVE' USING ERRCODE = 'check_violation';
        END IF;
        WITH RECURSIVE up(id, reports_to_id, n) AS (
            SELECT p.id, p.reports_to_id, 1 FROM public.platform_position p WHERE p.id = NEW.reports_to_id
            UNION ALL
            SELECT p.id, p.reports_to_id, u.n + 1
              FROM public.platform_position p JOIN up u ON p.id = u.reports_to_id
             WHERE u.id <> NEW.id AND u.n < 10000
        )
        SELECT coalesce(bool_or(id = NEW.id), false) INTO is_cycle FROM up;
        IF is_cycle THEN
            RAISE EXCEPTION 'ck_position_reports_to_acyclic: reports-to of % would create a cycle', NEW.code
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.status = 'INACTIVE' AND OLD.status = 'ACTIVE' THEN
        IF EXISTS (SELECT 1 FROM public.platform_position_assignment pa
                    WHERE pa.position_id = NEW.id
                      AND tstzrange(pa.valid_from, pa.valid_to, '[)') @> statement_timestamp())
           OR EXISTS (SELECT 1 FROM public.platform_position WHERE reports_to_id = NEW.id AND status = 'ACTIVE') THEN
            RAISE EXCEPTION 'ck_position_deactivate_empty: position still has a current holder or ACTIVE reports'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$;

-- SECURITY DEFINER (owner): the runtime role has no INSERT/UPDATE on the history table at all (ops/db/grants.sql)
CREATE FUNCTION platform_position_history_writer() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.code = OLD.code AND NEW.title_fa = OLD.title_fa AND NEW.unit_id = OLD.unit_id
       AND NEW.reports_to_id IS NOT DISTINCT FROM OLD.reports_to_id AND NEW.is_unit_head = OLD.is_unit_head
       AND NEW.status = OLD.status THEN
        RETURN NULL;
    END IF;
    UPDATE public.platform_position_history SET valid_to = NEW.effective_from
     WHERE position_id = NEW.id AND valid_to IS NULL;
    INSERT INTO public.platform_position_history
        (position_id, position_row_version, valid_from, valid_to, unit_id, code, title_fa, reports_to_id,
         is_unit_head, status, changed_by_id, recorded_at)
    VALUES (NEW.id, NEW.row_version, NEW.effective_from, NULL, NEW.unit_id, NEW.code, NEW.title_fa,
            NEW.reports_to_id, NEW.is_unit_head, NEW.status, COALESCE(NEW.updated_by_id, NEW.created_by_id),
            statement_timestamp());
    RETURN NULL;
END;
$fn$;

CREATE TRIGGER trg_position_effective BEFORE INSERT OR UPDATE ON public.platform_position
    FOR EACH ROW EXECUTE FUNCTION platform_effective_from_guard();
CREATE TRIGGER trg_position_guard BEFORE INSERT OR UPDATE ON public.platform_position
    FOR EACH ROW EXECUTE FUNCTION platform_position_guard();
CREATE TRIGGER trg_position_history AFTER INSERT OR UPDATE ON public.platform_position
    FOR EACH ROW EXECUTE FUNCTION platform_position_history_writer();
CREATE TRIGGER trg_position_history_append_only BEFORE UPDATE OR DELETE ON public.platform_position_history
    FOR EACH ROW EXECUTE FUNCTION platform_close_once_only('valid_to');
ALTER TABLE public.platform_position_history ADD CONSTRAINT ex_position_history_no_overlap
    EXCLUDE USING gist (position_id WITH =, tstzrange(valid_from, valid_to, '[)') WITH &&);

CREATE FUNCTION platform_position_assignment_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    -- Serialise writes per person: concurrent GiST exclusion checks can deadlock each other; with the lock
    -- the losers deterministically get exclusion_violation (23P01 -> 409), never deadlock_detected (500).
    PERFORM pg_advisory_xact_lock(hashtextextended('platform_position_assignment:' || NEW.user_id::text, 0));
    IF TG_OP = 'UPDATE' THEN
        IF NEW.position_id <> OLD.position_id OR NEW.user_id <> OLD.user_id OR NEW.kind <> OLD.kind
           OR NEW.valid_from <> OLD.valid_from OR NEW.created_at <> OLD.created_at THEN
            RAISE EXCEPTION 'immutable_column: position assignment identity cannot change (end it and add a new one)'
                USING ERRCODE = 'restrict_violation';
        END IF;
    ELSIF NOT EXISTS (SELECT 1 FROM public.platform_position WHERE id = NEW.position_id AND status = 'ACTIVE') THEN
        RAISE EXCEPTION 'ck_position_assignment_position_active: position is not ACTIVE' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_position_assignment_guard BEFORE INSERT OR UPDATE ON public.platform_position_assignment
    FOR EACH ROW EXECUTE FUNCTION platform_position_assignment_guard();
-- DEC-048: one PRIMARY position per person at any instant (race-safe: the index decides, not a SELECT)
ALTER TABLE public.platform_position_assignment ADD CONSTRAINT ex_position_assignment_one_primary
    EXCLUDE USING gist (user_id WITH =, tstzrange(valid_from, valid_to, '[)') WITH &&) WHERE (kind = 'PRIMARY');
ALTER TABLE public.platform_position_assignment ADD CONSTRAINT ex_position_assignment_no_duplicate
    EXCLUDE USING gist (user_id WITH =, position_id WITH =, tstzrange(valid_from, valid_to, '[)') WITH &&);

-- ------------------------------------------------------------------------------------------ workflow
CREATE TRIGGER trg_approval_request_immutable BEFORE UPDATE ON public.platform_approval_request
    FOR EACH ROW EXECUTE FUNCTION platform_immutable_columns(
        'id', 'action', 'resource_type', 'resource_id', 'resource_revision', 'requested_by_id', 'requested_at',
        'expires_at', 'route_kind', 'route_scope_unit_id', 'workflow_instance_id');
CREATE TRIGGER trg_work_task_immutable BEFORE UPDATE ON public.platform_work_task
    FOR EACH ROW EXECUTE FUNCTION platform_immutable_columns('id', 'created_by_id', 'created_at', 'workflow_instance_id');

CREATE FUNCTION platform_workflow_definition_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF OLD.status <> 'DRAFT' AND (NEW.key <> OLD.key OR NEW.version <> OLD.version OR NEW.steps <> OLD.steps) THEN
        RAISE EXCEPTION 'immutable_column: definition %/% is %; publish a new version', OLD.key, OLD.version, OLD.status
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_workflow_definition_guard BEFORE UPDATE ON public.platform_workflow_definition
    FOR EACH ROW EXECUTE FUNCTION platform_workflow_definition_guard();

CREATE FUNCTION platform_workflow_instance_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.definition_id <> OLD.definition_id OR NEW.subject_type <> OLD.subject_type
           OR NEW.subject_id <> OLD.subject_id OR NEW.started_at <> OLD.started_at THEN
            RAISE EXCEPTION 'immutable_column: workflow instance keeps its pinned definition and subject'
                USING ERRCODE = 'restrict_violation';
        END IF;
    ELSIF NOT EXISTS (SELECT 1 FROM public.platform_workflow_definition WHERE id = NEW.definition_id AND status = 'ACTIVE') THEN
        RAISE EXCEPTION 'ck_workflow_instance_definition_active: definition is not ACTIVE' USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_workflow_instance_guard BEFORE INSERT OR UPDATE ON public.platform_workflow_instance
    FOR EACH ROW EXECUTE FUNCTION platform_workflow_instance_guard();

-- ------------------------------------------------------------------------------------------ jobs
CREATE FUNCTION platform_job_run_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    d record;
BEGIN
    IF TG_OP = 'UPDATE' AND (NEW.job_type <> OLD.job_type OR NEW.task_key <> OLD.task_key OR NEW.queued_at <> OLD.queued_at) THEN
        RAISE EXCEPTION 'immutable_column: job run identity cannot change' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.cancel_requested_at IS NOT NULL OR NEW.state IN ('CANCEL_REQUESTED', 'CANCELLED') THEN
        SELECT cancellable, protected INTO d FROM public.platform_job_definition WHERE job_type = NEW.job_type;
        IF d.protected OR NOT d.cancellable THEN
            RAISE EXCEPTION 'ck_job_run_not_cancellable: job type % is protected or not cancellable (JOB_PROTECTED)', NEW.job_type
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_job_run_guard BEFORE INSERT OR UPDATE ON public.platform_job_run
    FOR EACH ROW EXECUTE FUNCTION platform_job_run_guard();
CREATE TRIGGER trg_job_definition_immutable BEFORE UPDATE ON public.platform_job_definition
    FOR EACH ROW EXECUTE FUNCTION platform_immutable_columns('job_type', 'protected', 'provenance', 'created_at');

-- ------------------------------------------------------------------------------------------ documents
CREATE TRIGGER trg_stored_object_append_only BEFORE UPDATE OR DELETE ON public.platform_stored_object
    FOR EACH ROW EXECUTE FUNCTION platform_close_once_only('purge_after', 'bytes_purged_at');

CREATE FUNCTION platform_document_revision_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    o record;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.size_bytes > public.platform_param_int('document_upload_max_bytes') THEN
            RAISE EXCEPTION 'ck_document_revision_max_size: % bytes exceed document_upload_max_bytes (DEC-053)', NEW.size_bytes
                USING ERRCODE = 'check_violation';
        END IF;
        SELECT size_bytes, sha256 INTO o FROM public.platform_stored_object WHERE storage_key = NEW.storage_key;
        IF o.sha256 <> NEW.sha256 OR o.size_bytes <> NEW.size_bytes THEN
            RAISE EXCEPTION 'ck_document_revision_object_match: size/sha256 differ from the stored object'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM public.platform_upload_type WHERE extension = NEW.upload_extension AND is_allowed) THEN
            RAISE EXCEPTION 'ck_document_revision_type_allowed: % is not an allowed upload type (DEC-053)', NEW.upload_extension
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.status <> 'WORKING' OR NEW.scan_status <> 'QUARANTINED' THEN
            RAISE EXCEPTION 'ck_document_revision_starts_quarantined: a new revision starts WORKING/QUARANTINED (SEC-03)'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.document_id <> OLD.document_id OR NEW.revision_no <> OLD.revision_no
       OR NEW.parent_revision_id IS DISTINCT FROM OLD.parent_revision_id OR NEW.storage_key <> OLD.storage_key
       OR NEW.upload_extension <> OLD.upload_extension OR NEW.sha256 <> OLD.sha256 OR NEW.size_bytes <> OLD.size_bytes
       OR NEW.original_name <> OLD.original_name OR NEW.uploaded_by_id <> OLD.uploaded_by_id
       OR NEW.uploaded_at <> OLD.uploaded_at THEN
        RAISE EXCEPTION 'immutable_column: uploaded content of a revision never changes (upload a new revision)'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.scan_status IN ('CLEAN', 'REJECTED') AND (NEW.scan_status <> OLD.scan_status
       OR NEW.scan_finding <> OLD.scan_finding OR NEW.scanned_at IS DISTINCT FROM OLD.scanned_at) THEN
        RAISE EXCEPTION 'immutable_column: scan verdict % is final', OLD.scan_status USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.status = 'APPROVED' AND (NEW.status NOT IN ('APPROVED', 'SUPERSEDED')
       OR NEW.decided_by_id IS DISTINCT FROM OLD.decided_by_id OR NEW.decided_at IS DISTINCT FROM OLD.decided_at
       OR NEW.approval_request_id IS DISTINCT FROM OLD.approval_request_id OR NEW.change_note <> OLD.change_note) THEN
        RAISE EXCEPTION 'immutable_column: an APPROVED revision only becomes SUPERSEDED' USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_document_revision_guard BEFORE INSERT OR UPDATE ON public.platform_document_revision
    FOR EACH ROW EXECUTE FUNCTION platform_document_revision_guard();

CREATE FUNCTION platform_document_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF TG_OP = 'UPDATE' AND (NEW.created_by_id <> OLD.created_by_id OR NEW.created_at <> OLD.created_at) THEN
        RAISE EXCEPTION 'immutable_column: document creator cannot change' USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.current_approved_revision_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public.platform_document_revision r
         WHERE r.id = NEW.current_approved_revision_id AND r.document_id = NEW.id AND r.status = 'APPROVED') THEN
        RAISE EXCEPTION 'ck_document_current_revision: current revision must be an APPROVED revision of this document'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_document_guard BEFORE INSERT OR UPDATE ON public.platform_document
    FOR EACH ROW EXECUTE FUNCTION platform_document_guard();
"""

REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS trg_document_guard ON public.platform_document;
DROP FUNCTION IF EXISTS platform_document_guard();
DROP TRIGGER IF EXISTS trg_document_revision_guard ON public.platform_document_revision;
DROP FUNCTION IF EXISTS platform_document_revision_guard();
DROP TRIGGER IF EXISTS trg_stored_object_append_only ON public.platform_stored_object;
DROP TRIGGER IF EXISTS trg_job_definition_immutable ON public.platform_job_definition;
DROP TRIGGER IF EXISTS trg_job_run_guard ON public.platform_job_run;
DROP FUNCTION IF EXISTS platform_job_run_guard();
DROP TRIGGER IF EXISTS trg_workflow_instance_guard ON public.platform_workflow_instance;
DROP FUNCTION IF EXISTS platform_workflow_instance_guard();
DROP TRIGGER IF EXISTS trg_workflow_definition_guard ON public.platform_workflow_definition;
DROP FUNCTION IF EXISTS platform_workflow_definition_guard();
DROP TRIGGER IF EXISTS trg_work_task_immutable ON public.platform_work_task;
DROP TRIGGER IF EXISTS trg_approval_request_immutable ON public.platform_approval_request;
ALTER TABLE public.platform_position_assignment DROP CONSTRAINT IF EXISTS ex_position_assignment_no_duplicate;
ALTER TABLE public.platform_position_assignment DROP CONSTRAINT IF EXISTS ex_position_assignment_one_primary;
DROP TRIGGER IF EXISTS trg_position_assignment_guard ON public.platform_position_assignment;
DROP FUNCTION IF EXISTS platform_position_assignment_guard();
ALTER TABLE public.platform_position_history DROP CONSTRAINT IF EXISTS ex_position_history_no_overlap;
DROP TRIGGER IF EXISTS trg_position_history_append_only ON public.platform_position_history;
DROP TRIGGER IF EXISTS trg_position_history ON public.platform_position;
DROP TRIGGER IF EXISTS trg_position_guard ON public.platform_position;
DROP TRIGGER IF EXISTS trg_position_effective ON public.platform_position;
DROP FUNCTION IF EXISTS platform_position_history_writer();
DROP FUNCTION IF EXISTS platform_position_guard();
ALTER TABLE public.platform_org_unit_history DROP CONSTRAINT IF EXISTS ex_org_unit_history_no_overlap;
DROP TRIGGER IF EXISTS trg_org_unit_history_append_only ON public.platform_org_unit_history;
DROP TRIGGER IF EXISTS trg_org_unit_history ON public.platform_org_unit;
DROP TRIGGER IF EXISTS trg_org_unit_tree_guard ON public.platform_org_unit;
DROP TRIGGER IF EXISTS trg_org_unit_effective ON public.platform_org_unit;
DROP FUNCTION IF EXISTS platform_org_unit_history_writer();
DROP FUNCTION IF EXISTS platform_org_unit_tree_guard();
DROP FUNCTION IF EXISTS platform_effective_from_guard();
DROP TRIGGER IF EXISTS trg_break_glass_usage_append_only ON public.platform_break_glass_usage;
DROP TRIGGER IF EXISTS trg_break_glass_usage_account ON public.platform_break_glass_usage;
DROP FUNCTION IF EXISTS platform_break_glass_usage_guard();
DROP TRIGGER IF EXISTS trg_login_attempt_guard ON public.platform_login_attempt;
DROP FUNCTION IF EXISTS platform_login_attempt_guard();
DROP TRIGGER IF EXISTS trg_user_immutable ON public.platform_user;
DROP TRIGGER IF EXISTS trg_credential_immutable ON public.platform_credential;
DROP TRIGGER IF EXISTS trg_session_immutable ON public.platform_session;
DROP TRIGGER IF EXISTS trg_recovery_code_use_once ON public.platform_recovery_code;
DROP TRIGGER IF EXISTS trg_mfa_factor_guard ON public.platform_mfa_factor;
DROP FUNCTION IF EXISTS platform_mfa_factor_guard();
ALTER TABLE public.platform_role_assignment DROP CONSTRAINT IF EXISTS ex_role_assignment_no_overlap;
DROP TRIGGER IF EXISTS trg_role_assignment_guard ON public.platform_role_assignment;
DROP FUNCTION IF EXISTS platform_role_assignment_guard();
DROP TRIGGER IF EXISTS trg_permission_ba_guard ON public.platform_permission;
DROP FUNCTION IF EXISTS platform_permission_ba_guard();
DROP TRIGGER IF EXISTS trg_role_kind_guard ON public.platform_role;
DROP FUNCTION IF EXISTS platform_role_kind_guard();
DROP TRIGGER IF EXISTS trg_role_permission_guard ON public.platform_role_permission;
DROP FUNCTION IF EXISTS platform_role_permission_guard();
DROP TRIGGER IF EXISTS trg_dynamic_field_definition_immutable ON public.platform_dynamic_field_definition;
DROP TRIGGER IF EXISTS trg_parameter_definition_immutable ON public.platform_parameter_definition;
DROP TRIGGER IF EXISTS trg_parameter_value_guard ON public.platform_parameter_value;
DROP FUNCTION IF EXISTS platform_parameter_value_guard();
DROP FUNCTION IF EXISTS platform_param_int(text);
DROP FUNCTION IF EXISTS platform_param_value(text);
DROP FUNCTION IF EXISTS platform_immutable_columns();
DROP FUNCTION IF EXISTS platform_close_once_only();
DROP FUNCTION IF EXISTS platform_reject_terminal_update();
DROP FUNCTION IF EXISTS platform_bump_row();
DROP EXTENSION IF EXISTS btree_gist;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0007_phase01_platform_schema"),
    ]

    operations = [
        migrations.RunSQL(sql=FUNCTIONS_SQL, reverse_sql=REVERSE_SQL),
        migrations.RunSQL(sql=TOUCH_FWD, reverse_sql=TOUCH_REV),
    ]
