--
-- PostgreSQL database dump
--


-- Dumped from database version 17.9
-- Dumped by pg_dump version 17.9

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;


--
-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';


--
-- Name: platform_break_glass_usage_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_break_glass_usage_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.platform_user WHERE id = NEW.user_id AND is_break_glass) THEN
        RAISE EXCEPTION 'ck_break_glass_usage_account: user is not the break-glass account (DEC-054)'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: platform_bump_row(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_bump_row() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    NEW.row_version := OLD.row_version + 1;
    NEW.updated_at := statement_timestamp();
    RETURN NEW;
END;
$$;


--
-- Name: platform_close_once_only(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_close_once_only() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_document_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_document_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_document_revision_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_document_revision_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_effective_from_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_effective_from_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
    -- REV-0107 / employer answer 2026-11-05: org changes are never back-dated. effective_from given by the
    -- application must be >= now - 60 s (TECHNICAL clock tolerance between app server and DB, not a business
    -- rule). A late change keeps the real date only in the audit reason/note.
    IF (TG_OP = 'INSERT' OR NEW.effective_from IS DISTINCT FROM OLD.effective_from)
       AND NEW.effective_from < statement_timestamp() - interval '60 seconds' THEN
        RAISE EXCEPTION 'ck_effective_from_not_backdated: % changes cannot be back-dated (record the real date in the reason)', TG_TABLE_NAME
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
$$;


--
-- Name: platform_holds_owner_admin(uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_holds_owner_admin(p_user uuid) RETURNS boolean
    LANGUAGE sql STABLE
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
    SELECT p_user IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.platform_role_assignment ra
          JOIN public.platform_role r ON r.id = ra.role_id
         WHERE ra.user_id = p_user AND r.code = 'owner_admin' AND r.status = 'ACTIVE' AND ra.status = 'ACTIVE'
           AND tstzrange(ra.valid_from, ra.valid_to, '[)') @> statement_timestamp());
$$;


--
-- Name: platform_immutable_columns(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_immutable_columns() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_import_batch_provenance_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_import_batch_provenance_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    IF NEW.source_id IS DISTINCT FROM OLD.source_id
       OR NEW.file_sha256 IS DISTINCT FROM OLD.file_sha256
       OR NEW.byte_size IS DISTINCT FROM OLD.byte_size
       OR NEW.original_name IS DISTINCT FROM OLD.original_name
       OR NEW.actor_type IS DISTINCT FROM OLD.actor_type
       OR NEW.actor_id IS DISTINCT FROM OLD.actor_id
       OR NEW.request_id IS DISTINCT FROM OLD.request_id
       OR NEW.received_at IS DISTINCT FROM OLD.received_at THEN
        RAISE EXCEPTION 'import batch provenance is immutable'
            USING ERRCODE = 'restrict_violation',
                  HINT = 'Import the corrected file as a new batch.';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: platform_job_run_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_job_run_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_login_attempt_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_login_attempt_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_mfa_factor_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_mfa_factor_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_org_unit_history_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_org_unit_history_writer() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_org_unit_tree_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_org_unit_tree_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_param_int(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_param_int(p_key text) RETURNS bigint
    LANGUAGE sql STABLE
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
    SELECT public.platform_param_value(p_key)::bigint;
$$;


--
-- Name: platform_param_value(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_param_value(p_key text) RETURNS text
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_parameter_value_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_parameter_value_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $_$
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
    -- Q-0103 (employer answer 2026-11-05, closes REV-0106): an OWNER_POLICY value is proposed and published by
    -- the owner alone (no second person), but only by a user holding an ACTIVE owner_admin assignment now, with
    -- a reason. MFA step-up and the audit event are enforced by the 01.3/01.4 engine. Migration seeds are exempt.
    IF d.classification = 'OWNER_POLICY' AND NEW.provenance <> 'MIGRATION_SEED' THEN
        IF length(btrim(NEW.reason)) < 3 THEN
            RAISE EXCEPTION 'ck_parameter_value_owner_policy: % needs a reason (Q-0103)', NEW.parameter_key
                USING ERRCODE = 'check_violation';
        END IF;
        IF TG_OP = 'INSERT' AND NOT public.platform_holds_owner_admin(NEW.proposed_by_id) THEN
            RAISE EXCEPTION 'ck_parameter_value_owner_policy: only an owner_admin holder may propose % (Q-0103)',
                NEW.parameter_key USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.status = 'PUBLISHED' AND (TG_OP = 'INSERT' OR OLD.status <> 'PUBLISHED')
           AND NOT public.platform_holds_owner_admin(NEW.published_by_id) THEN
            RAISE EXCEPTION 'ck_parameter_value_owner_policy: only an owner_admin holder may publish % (Q-0103)',
                NEW.parameter_key USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    -- DEC-032: BUSINESS_RULE publish is maker-checker (never self-published)
    IF d.classification = 'BUSINESS_RULE' AND NEW.status IN ('PUBLISHED', 'SUPERSEDED')
       AND (NEW.published_by_id IS NULL OR NEW.published_by_id = NEW.proposed_by_id) THEN
        RAISE EXCEPTION 'ck_parameter_value_maker_checker: business rule % needs a second person to publish', NEW.parameter_key
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$_$;


--
-- Name: platform_permission_ba_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_permission_ba_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_position_assignment_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_position_assignment_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    cap smallint;
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
    -- Q-0106 (employer answer 2026-11-05): at most primary_capacity PRIMARY holders at any instant; serialised
    -- per position (lock order: person, then position - never the reverse, so no lock cycle)
    IF NEW.kind = 'PRIMARY' THEN
        PERFORM pg_advisory_xact_lock(hashtextextended('platform_position_capacity:' || NEW.position_id::text, 0));
        SELECT primary_capacity INTO cap FROM public.platform_position WHERE id = NEW.position_id;
        IF public.platform_position_peak_primary(NEW.position_id, NEW.id, NEW.valid_from, NEW.valid_to) + 1 > cap THEN
            RAISE EXCEPTION 'ck_position_primary_capacity: position already has % PRIMARY holder(s) in that period', cap
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: platform_position_assignment_not_backdated(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_position_assignment_not_backdated() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.valid_from < statement_timestamp() - interval '60 seconds' THEN
            RAISE EXCEPTION 'ck_position_assignment_not_backdated: an assignment cannot start in the past
            (record the real date in the reason)'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.valid_to IS DISTINCT FROM OLD.valid_to THEN
        IF OLD.valid_to IS NOT NULL AND OLD.valid_to < statement_timestamp() - interval '60 seconds' THEN
            RAISE EXCEPTION 'ck_position_assignment_not_backdated: an ended assignment is never changed again'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.valid_to IS NOT NULL AND NEW.valid_to < statement_timestamp() - interval '60 seconds' THEN
            RAISE EXCEPTION 'ck_position_assignment_not_backdated: an assignment cannot be ended in the past'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: platform_position_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_position_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
    IF TG_OP = 'UPDATE' AND NEW.primary_capacity < OLD.primary_capacity THEN
        -- same per-position lock as the assignment guard: a capacity decrease never races a new holder
        PERFORM pg_advisory_xact_lock(hashtextextended('platform_position_capacity:' || NEW.id::text, 0));
        IF public.platform_position_peak_primary(NEW.id, NULL, statement_timestamp(), NULL) > NEW.primary_capacity THEN
            RAISE EXCEPTION 'ck_position_primary_capacity: % has more current/future PRIMARY holders than %',
                NEW.code, NEW.primary_capacity USING ERRCODE = 'check_violation';
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
$$;


--
-- Name: platform_position_history_writer(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_position_history_writer() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.code = OLD.code AND NEW.title_fa = OLD.title_fa AND NEW.unit_id = OLD.unit_id
       AND NEW.reports_to_id IS NOT DISTINCT FROM OLD.reports_to_id AND NEW.is_unit_head = OLD.is_unit_head
       AND NEW.primary_capacity = OLD.primary_capacity AND NEW.status = OLD.status THEN
        RETURN NULL;
    END IF;
    UPDATE public.platform_position_history SET valid_to = NEW.effective_from
     WHERE position_id = NEW.id AND valid_to IS NULL;
    INSERT INTO public.platform_position_history
        (position_id, position_row_version, valid_from, valid_to, unit_id, code, title_fa, reports_to_id,
         is_unit_head, primary_capacity, status, changed_by_id, recorded_at)
    VALUES (NEW.id, NEW.row_version, NEW.effective_from, NULL, NEW.unit_id, NEW.code, NEW.title_fa,
            NEW.reports_to_id, NEW.is_unit_head, NEW.primary_capacity, NEW.status, COALESCE(NEW.updated_by_id, NEW.created_by_id),
            statement_timestamp());
    RETURN NULL;
END;
$$;


--
-- Name: platform_position_peak_primary(uuid, uuid, timestamp with time zone, timestamp with time zone); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_position_peak_primary(p_position uuid, p_exclude uuid, p_from timestamp with time zone, p_to timestamp with time zone) RETURNS bigint
    LANGUAGE sql STABLE
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
    WITH r AS (
        SELECT tstzrange(pa.valid_from, pa.valid_to, '[)') AS rng, pa.valid_from
          FROM public.platform_position_assignment pa
         WHERE pa.position_id = p_position AND pa.kind = 'PRIMARY'
           AND pa.id IS DISTINCT FROM p_exclude
           AND tstzrange(pa.valid_from, pa.valid_to, '[)') && tstzrange(p_from, p_to, '[)')
    ), pts AS (
        SELECT p_from AS p
        UNION SELECT valid_from FROM r WHERE valid_from > p_from
    )
    SELECT coalesce(max((SELECT count(*) FROM r WHERE r.rng @> pts.p)), 0) FROM pts;
$$;


--
-- Name: platform_reject_mutation(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_reject_mutation() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    RAISE EXCEPTION 'table % is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation',
              HINT = 'Audit events are immutable; record a new compensating event instead.';
END;
$$;


--
-- Name: platform_reject_terminal_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_reject_terminal_update() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    old_state text := to_jsonb(OLD) ->> TG_ARGV[0];
BEGIN
    IF old_state = ANY (TG_ARGV[1:TG_NARGS - 1]) THEN
        RAISE EXCEPTION 'terminal_immutable: % row in terminal state % cannot change', TG_TABLE_NAME, old_state
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: platform_reject_truncate_nonempty(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_reject_truncate_nonempty() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    has_rows boolean;
BEGIN
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %I.%I)', TG_TABLE_SCHEMA, TG_TABLE_NAME) INTO has_rows;
    IF has_rows THEN
        RAISE EXCEPTION 'table % is append-only: TRUNCATE is not allowed', TG_TABLE_NAME
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NULL;
END;
$$;


--
-- Name: platform_role_assignment_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_role_assignment_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_role_kind_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_role_kind_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_role_permission_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_role_permission_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


--
-- Name: platform_staging_row_payload_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_staging_row_payload_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    IF NEW.batch_id IS DISTINCT FROM OLD.batch_id
       OR NEW.sheet_name IS DISTINCT FROM OLD.sheet_name
       OR NEW.row_number IS DISTINCT FROM OLD.row_number
       OR NEW.payload IS DISTINCT FROM OLD.payload
       OR NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256 THEN
        RAISE EXCEPTION 'staged row payload is immutable'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: platform_touch_row(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_touch_row() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    NEW.row_version := OLD.row_version + 1;
    NEW.updated_at := statement_timestamp();  -- same clock as the db_default Now() columns
    NEW.created_at := OLD.created_at;
    RETURN NEW;
END;
$$;


--
-- Name: platform_workflow_definition_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_workflow_definition_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    IF OLD.status <> 'DRAFT' AND (NEW.key <> OLD.key OR NEW.version <> OLD.version OR NEW.steps <> OLD.steps) THEN
        RAISE EXCEPTION 'immutable_column: definition %/% is %; publish a new version', OLD.key, OLD.version, OLD.status
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: platform_workflow_instance_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_workflow_instance_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: django_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.django_migrations (
    id bigint NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.django_migrations ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.django_migrations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_approval_request; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_approval_request (
    id uuid NOT NULL,
    resource_type character varying(64) NOT NULL,
    resource_id character varying(64) NOT NULL,
    resource_revision bigint NOT NULL,
    status character varying(12) DEFAULT 'PENDING'::character varying NOT NULL,
    requested_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    route_kind character varying(20) DEFAULT 'ROLE_UNIT_SCOPE'::character varying NOT NULL,
    decision_note character varying(500) NOT NULL,
    closed_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    decided_by_id uuid,
    requested_by_id uuid NOT NULL,
    route_scope_unit_id uuid,
    action character varying(120) NOT NULL,
    workflow_instance_id uuid,
    CONSTRAINT ck_approval_request_closed_at CHECK ((((closed_at IS NULL) AND ((status)::text = 'PENDING'::text)) OR ((NOT ((status)::text = 'PENDING'::text)) AND (closed_at IS NOT NULL)))),
    CONSTRAINT ck_approval_request_decided_has_decider CHECK (((NOT ((status)::text = ANY ((ARRAY['APPROVED'::character varying, 'REJECTED'::character varying])::text[]))) OR (decided_by_id IS NOT NULL))),
    CONSTRAINT ck_approval_request_expiry_after_request CHECK ((expires_at > requested_at)),
    CONSTRAINT ck_approval_request_maker_checker CHECK (((decided_by_id IS NULL) OR (NOT ((decided_by_id = requested_by_id) AND (decided_by_id IS NOT NULL))))),
    CONSTRAINT ck_approval_request_reject_note CHECK (((NOT ((status)::text = 'REJECTED'::text)) OR (length((decision_note)::text) >= 3))),
    CONSTRAINT ck_approval_request_resource_fmt CHECK (((resource_type)::text ~ '^[a-z][a-z0-9_]{0,63}$'::text)),
    CONSTRAINT ck_approval_request_resource_id_nonempty CHECK ((NOT ((resource_id)::text = ''::text))),
    CONSTRAINT ck_approval_request_revision_nonneg CHECK ((resource_revision >= 0)),
    CONSTRAINT ck_approval_request_route_kind CHECK (((route_kind)::text = 'ROLE_UNIT_SCOPE'::text)),
    CONSTRAINT ck_approval_request_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_approval_request_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying, 'WITHDRAWN'::character varying, 'SUPERSEDED'::character varying, 'EXPIRED'::character varying])::text[]))),
    CONSTRAINT ck_approval_request_undecided_no_decider CHECK ((((status)::text = ANY ((ARRAY['APPROVED'::character varying, 'REJECTED'::character varying])::text[])) OR (decided_by_id IS NULL)))
);


--
-- Name: platform_audit_event; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_audit_event (
    id uuid NOT NULL,
    occurred_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    actor_type character varying(16) NOT NULL,
    actor_id uuid,
    request_id uuid,
    correlation_id uuid,
    action character varying(150) NOT NULL,
    outcome character varying(16) NOT NULL,
    resource_type character varying(100) NOT NULL,
    resource_id character varying(64) NOT NULL,
    resource_version bigint,
    scope jsonb NOT NULL,
    reason text NOT NULL,
    before jsonb,
    after jsonb,
    chain_seq bigint,
    event_hash character varying(64) DEFAULT ''::character varying NOT NULL,
    network_zone character varying(8) DEFAULT ''::character varying NOT NULL,
    prev_hash character varying(64) DEFAULT ''::character varying NOT NULL,
    session_id uuid,
    CONSTRAINT ck_audit_event_action_fmt CHECK (((action)::text ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)+$'::text)),
    CONSTRAINT ck_audit_event_actor_id_for_user CHECK (((NOT ((actor_type)::text = 'USER'::text)) OR (actor_id IS NOT NULL))),
    CONSTRAINT ck_audit_event_actor_type CHECK (((actor_type)::text = ANY ((ARRAY['USER'::character varying, 'SYSTEM'::character varying, 'ANONYMOUS'::character varying])::text[]))),
    CONSTRAINT ck_audit_event_chain_consistent CHECK ((((chain_seq IS NULL) AND ((event_hash)::text = ''::text)) OR ((chain_seq >= 1) AND ((event_hash)::text ~ '^[0-9a-f]{64}$'::text)))),
    CONSTRAINT ck_audit_event_event_hash_fmt CHECK ((((event_hash)::text = ''::text) OR ((event_hash)::text ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_audit_event_network_zone CHECK (((network_zone)::text = ANY ((ARRAY[''::character varying, 'INTERNAL'::character varying, 'EXTERNAL'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT ck_audit_event_outcome CHECK (((outcome)::text = ANY ((ARRAY['SUCCESS'::character varying, 'DENIED'::character varying, 'FAILED'::character varying])::text[]))),
    CONSTRAINT ck_audit_event_prev_hash_fmt CHECK ((((prev_hash)::text = ''::text) OR ((prev_hash)::text ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_audit_event_resource_type_nonempty CHECK ((NOT ((resource_type)::text = ''::text))),
    CONSTRAINT ck_audit_event_resource_version_nonneg CHECK (((resource_version IS NULL) OR (resource_version >= 0))),
    CONSTRAINT ck_audit_event_scope_object CHECK ((jsonb_typeof(scope) = 'object'::text))
);


--
-- Name: platform_audit_integrity_run; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_audit_integrity_run (
    id uuid NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone NOT NULL,
    status character varying(8) NOT NULL,
    events_checked bigint NOT NULL,
    checked_up_to_seq bigint,
    first_broken_event_id uuid,
    error_code character varying(64) NOT NULL,
    job_run_id uuid,
    CONSTRAINT ck_audit_integrity_run_broken_ref CHECK (((NOT ((status)::text = 'BROKEN'::text)) OR (first_broken_event_id IS NOT NULL))),
    CONSTRAINT ck_audit_integrity_run_count_nonneg CHECK ((events_checked >= 0)),
    CONSTRAINT ck_audit_integrity_run_error_code CHECK (((NOT ((status)::text = 'ERROR'::text)) OR ((error_code)::text ~ '^[A-Z][A-Z0-9_]{2,63}$'::text))),
    CONSTRAINT ck_audit_integrity_run_finished_after_start CHECK ((finished_at >= started_at)),
    CONSTRAINT ck_audit_integrity_run_status CHECK (((status)::text = ANY ((ARRAY['OK'::character varying, 'BROKEN'::character varying, 'ERROR'::character varying])::text[])))
);


--
-- Name: platform_break_glass_usage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_break_glass_usage (
    id uuid NOT NULL,
    started_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    reason character varying(500) NOT NULL,
    alerted_at timestamp with time zone,
    ended_at timestamp with time zone,
    password_rotated_at timestamp with time zone,
    user_id uuid NOT NULL,
    session_id uuid,
    CONSTRAINT ck_break_glass_usage_end_after_start CHECK (((ended_at IS NULL) OR (ended_at >= started_at))),
    CONSTRAINT ck_break_glass_usage_reason CHECK ((length((reason)::text) >= 3))
);


--
-- Name: platform_compensation_record; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_compensation_record (
    id uuid NOT NULL,
    event_id uuid NOT NULL,
    event_type character varying(150) NOT NULL,
    consumer character varying(150) NOT NULL,
    aggregate_type character varying(100) NOT NULL,
    aggregate_id character varying(64) NOT NULL,
    trigger character varying(16) NOT NULL,
    failure_code character varying(500) NOT NULL,
    outcome character varying(16) NOT NULL,
    hook_error character varying(150) NOT NULL,
    recorded_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    CONSTRAINT ck_compensation_record_consumer_fmt CHECK (((consumer)::text ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)+$'::text)),
    CONSTRAINT ck_compensation_record_hook_error CHECK (((NOT ((outcome)::text = 'HOOK_FAILED'::text)) OR (NOT ((hook_error)::text = ''::text)))),
    CONSTRAINT ck_compensation_record_outcome CHECK (((outcome)::text = ANY ((ARRAY['MANUAL_REQUIRED'::character varying, 'COMPLETED'::character varying, 'HOOK_FAILED'::character varying])::text[]))),
    CONSTRAINT ck_compensation_record_trigger CHECK (((trigger)::text = 'DEAD_LETTER'::text)),
    CONSTRAINT ck_compensation_record_type_fmt CHECK (((event_type)::text ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)+$'::text))
);


--
-- Name: platform_conflict_item; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_conflict_item (
    id bigint NOT NULL,
    conflict_id uuid NOT NULL,
    conflict_key character varying(200) NOT NULL,
    kind character varying(64) NOT NULL,
    details jsonb NOT NULL,
    status character varying(16) DEFAULT 'OPEN'::character varying NOT NULL,
    raised_by_type character varying(16) NOT NULL,
    raised_by_id uuid,
    raised_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    resolved_by uuid,
    resolved_at timestamp with time zone,
    resolution_note character varying(500) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    batch_id uuid,
    source_id smallint NOT NULL,
    CONSTRAINT ck_conflict_item_details_object CHECK ((jsonb_typeof(details) = 'object'::text)),
    CONSTRAINT ck_conflict_item_key_nonempty CHECK ((NOT ((conflict_key)::text = ''::text))),
    CONSTRAINT ck_conflict_item_kind_fmt CHECK (((kind)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text)),
    CONSTRAINT ck_conflict_item_raised_by_id_for_user CHECK (((NOT ((raised_by_type)::text = 'USER'::text)) OR (raised_by_id IS NOT NULL))),
    CONSTRAINT ck_conflict_item_raised_by_type CHECK (((raised_by_type)::text = ANY ((ARRAY['USER'::character varying, 'SYSTEM'::character varying, 'ANONYMOUS'::character varying])::text[]))),
    CONSTRAINT ck_conflict_item_resolution_consistent CHECK (((((status)::text = 'OPEN'::text) AND ((resolution_note)::text = ''::text) AND (resolved_at IS NULL) AND (resolved_by IS NULL)) OR ((NOT ((status)::text = 'OPEN'::text)) AND (resolved_at IS NOT NULL) AND (resolved_by IS NOT NULL) AND (NOT ((resolution_note)::text = ''::text))))),
    CONSTRAINT ck_conflict_item_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_conflict_item_status CHECK (((status)::text = ANY ((ARRAY['OPEN'::character varying, 'RESOLVED'::character varying, 'DISMISSED'::character varying])::text[])))
);


--
-- Name: platform_conflict_item_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_conflict_item ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_conflict_item_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_credential; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_credential (
    user_id uuid NOT NULL,
    password_hash character varying(256) NOT NULL,
    set_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    must_change boolean DEFAULT true NOT NULL,
    is_one_time boolean DEFAULT false NOT NULL,
    one_time_expires_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    set_by_id uuid,
    CONSTRAINT ck_credential_expiry_after_set CHECK (((expires_at IS NULL) OR (expires_at > set_at))),
    CONSTRAINT ck_credential_hash_fmt CHECK (((password_hash)::text ~ '^[a-z0-9_]{3,32}\$.+$'::text)),
    CONSTRAINT ck_credential_one_time_after_set CHECK (((one_time_expires_at IS NULL) OR (one_time_expires_at > set_at))),
    CONSTRAINT ck_credential_one_time_expiry CHECK (((NOT is_one_time) OR (must_change AND (one_time_expires_at IS NOT NULL)))),
    CONSTRAINT ck_credential_row_version_pos CHECK ((row_version >= 1))
);


--
-- Name: platform_document; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_document (
    id uuid NOT NULL,
    document_type character varying(64) NOT NULL,
    title_fa character varying(200) NOT NULL,
    owner_entity_type character varying(64) NOT NULL,
    owner_entity_id character varying(64) NOT NULL,
    sensitivity character varying(2) NOT NULL,
    legacy_location_ref character varying(500) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by_id uuid NOT NULL,
    updated_by_id uuid,
    current_approved_revision_id uuid,
    CONSTRAINT ck_document_owner_ref CHECK (((((owner_entity_id)::text = ''::text) AND ((owner_entity_type)::text = ''::text)) OR (((owner_entity_type)::text ~ '^[a-z][a-z0-9_]{0,63}$'::text) AND (NOT ((owner_entity_id)::text = ''::text))))),
    CONSTRAINT ck_document_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_document_sensitivity CHECK (((sensitivity)::text = ANY ((ARRAY['S1'::character varying, 'S2'::character varying, 'S3'::character varying])::text[]))),
    CONSTRAINT ck_document_title_nonempty CHECK ((NOT ((title_fa)::text = ''::text))),
    CONSTRAINT ck_document_type_fmt CHECK (((document_type)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text))
);


--
-- Name: platform_document_revision; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_document_revision (
    id uuid NOT NULL,
    revision_no integer NOT NULL,
    status character varying(12) DEFAULT 'WORKING'::character varying NOT NULL,
    scan_status character varying(12) DEFAULT 'QUARANTINED'::character varying NOT NULL,
    scan_finding character varying(200) NOT NULL,
    scanned_at timestamp with time zone,
    scanner_version character varying(64) NOT NULL,
    sha256 character varying(64) NOT NULL,
    size_bytes bigint NOT NULL,
    media_type_detected character varying(127) NOT NULL,
    original_name character varying(255) NOT NULL,
    change_note character varying(500) NOT NULL,
    uploaded_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    submitted_at timestamp with time zone,
    decided_at timestamp with time zone,
    reject_reason character varying(500) NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    approval_request_id uuid,
    decided_by_id uuid,
    document_id uuid NOT NULL,
    parent_revision_id uuid,
    submitted_by_id uuid,
    uploaded_by_id uuid NOT NULL,
    storage_key character varying(64) NOT NULL,
    upload_extension character varying(8) NOT NULL,
    CONSTRAINT ck_document_revision_approved_has_decider CHECK (((NOT ((status)::text = ANY ((ARRAY['APPROVED'::character varying, 'SUPERSEDED'::character varying])::text[]))) OR ((decided_at IS NOT NULL) AND (decided_by_id IS NOT NULL)))),
    CONSTRAINT ck_document_revision_maker_checker CHECK (((decided_by_id IS NULL) OR (NOT ((decided_by_id = uploaded_by_id) AND (decided_by_id IS NOT NULL))))),
    CONSTRAINT ck_document_revision_name_basename CHECK (((original_name)::text ~ '^[^/\\\x01-\x1f\x7f]+$'::text)),
    CONSTRAINT ck_document_revision_no_pos CHECK ((revision_no >= 1)),
    CONSTRAINT ck_document_revision_reject_reason CHECK (((NOT ((status)::text = 'REJECTED'::text)) OR ((scan_status)::text = 'REJECTED'::text) OR ((decided_by_id IS NOT NULL) AND (length((reject_reason)::text) >= 3)))),
    CONSTRAINT ck_document_revision_review_needs_clean CHECK (((NOT ((status)::text = ANY ((ARRAY['IN_REVIEW'::character varying, 'APPROVED'::character varying, 'SUPERSEDED'::character varying])::text[]))) OR ((scan_status)::text = 'CLEAN'::text))),
    CONSTRAINT ck_document_revision_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_document_revision_scan CHECK (((scan_status)::text = ANY ((ARRAY['QUARANTINED'::character varying, 'SCANNING'::character varying, 'CLEAN'::character varying, 'REJECTED'::character varying])::text[]))),
    CONSTRAINT ck_document_revision_scan_reject CHECK (((NOT ((scan_status)::text = 'REJECTED'::text)) OR ((status)::text = 'REJECTED'::text))),
    CONSTRAINT ck_document_revision_scanned_at CHECK (((NOT ((scan_status)::text = ANY ((ARRAY['CLEAN'::character varying, 'REJECTED'::character varying])::text[]))) OR (scanned_at IS NOT NULL))),
    CONSTRAINT ck_document_revision_sha256_fmt CHECK (((sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_document_revision_size_pos CHECK ((size_bytes > 0)),
    CONSTRAINT ck_document_revision_status CHECK (((status)::text = ANY ((ARRAY['WORKING'::character varying, 'IN_REVIEW'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying, 'SUPERSEDED'::character varying])::text[])))
);


--
-- Name: platform_dynamic_field_definition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_dynamic_field_definition (
    id uuid NOT NULL,
    field_key character varying(64) NOT NULL,
    entity_scope character varying(64) NOT NULL,
    label_fa character varying(200) NOT NULL,
    datatype character varying(10) NOT NULL,
    security_class character varying(2) NOT NULL,
    help_fa character varying(500) NOT NULL,
    status character varying(8) DEFAULT 'DRAFT'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by_id uuid,
    updated_by_id uuid,
    CONSTRAINT ck_dynamic_field_datatype CHECK (((datatype)::text = ANY ((ARRAY['STRING'::character varying, 'INTEGER'::character varying, 'DECIMAL'::character varying, 'BOOLEAN'::character varying, 'DATE'::character varying, 'ENUM'::character varying, 'REFERENCE'::character varying])::text[]))),
    CONSTRAINT ck_dynamic_field_draft_only CHECK (((status)::text = 'DRAFT'::text)),
    CONSTRAINT ck_dynamic_field_key_fmt CHECK (((field_key)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text)),
    CONSTRAINT ck_dynamic_field_label_nonempty CHECK ((NOT ((label_fa)::text = ''::text))),
    CONSTRAINT ck_dynamic_field_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_dynamic_field_scope_fmt CHECK (((entity_scope)::text ~ '^[a-z][a-z0-9_]{0,63}$'::text)),
    CONSTRAINT ck_dynamic_field_security_class CHECK (((security_class)::text = ANY ((ARRAY['S0'::character varying, 'S1'::character varying, 'S2'::character varying, 'S3'::character varying])::text[])))
);


--
-- Name: platform_idempotency_record; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_idempotency_record (
    id uuid NOT NULL,
    actor_id uuid NOT NULL,
    key uuid NOT NULL,
    method character varying(7) NOT NULL,
    endpoint character varying(255) NOT NULL,
    request_hash character varying(64) NOT NULL,
    state character varying(20) DEFAULT 'IN_PROGRESS'::character varying NOT NULL,
    response_status smallint,
    response_headers jsonb NOT NULL,
    response_body jsonb,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_idempotency_record_completed_has_status CHECK (((NOT ((state)::text = 'COMPLETED'::text)) OR (response_status IS NOT NULL))),
    CONSTRAINT ck_idempotency_record_endpoint_nonempty CHECK ((NOT ((endpoint)::text = ''::text))),
    CONSTRAINT ck_idempotency_record_expiry_after_create CHECK ((expires_at > created_at)),
    CONSTRAINT ck_idempotency_record_hash_fmt CHECK (((request_hash)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_idempotency_record_method CHECK (((method)::text = ANY ((ARRAY['POST'::character varying, 'PUT'::character varying, 'PATCH'::character varying, 'DELETE'::character varying])::text[]))),
    CONSTRAINT ck_idempotency_record_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_idempotency_record_state CHECK (((state)::text = ANY ((ARRAY['IN_PROGRESS'::character varying, 'COMPLETED'::character varying, 'FAILED_RETRYABLE'::character varying])::text[]))),
    CONSTRAINT ck_idempotency_record_status_range CHECK (((response_status IS NULL) OR ((response_status >= 100) AND (response_status <= 599))))
);


--
-- Name: platform_import_batch; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_import_batch (
    id uuid NOT NULL,
    file_sha256 character varying(64) NOT NULL,
    byte_size bigint NOT NULL,
    original_name character varying(255) NOT NULL,
    actor_type character varying(16) NOT NULL,
    actor_id uuid,
    request_id uuid,
    correlation_id uuid,
    status character varying(16) DEFAULT 'RECEIVED'::character varying NOT NULL,
    source_as_of timestamp with time zone,
    row_count integer DEFAULT 0 NOT NULL,
    error_row_count integer DEFAULT 0 NOT NULL,
    received_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    staged_at timestamp with time zone,
    validated_at timestamp with time zone,
    closed_at timestamp with time zone,
    close_reason character varying(500) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    source_id smallint NOT NULL,
    CONSTRAINT ck_import_batch_actor_id_for_user CHECK (((NOT ((actor_type)::text = 'USER'::text)) OR (actor_id IS NOT NULL))),
    CONSTRAINT ck_import_batch_actor_type CHECK (((actor_type)::text = ANY ((ARRAY['USER'::character varying, 'SYSTEM'::character varying, 'ANONYMOUS'::character varying])::text[]))),
    CONSTRAINT ck_import_batch_byte_size_pos CHECK ((byte_size > 0)),
    CONSTRAINT ck_import_batch_closed_has_reason CHECK (((NOT ((status)::text = ANY ((ARRAY['REJECTED'::character varying, 'SUPERSEDED'::character varying])::text[]))) OR ((closed_at IS NOT NULL) AND (NOT ((close_reason)::text = ''::text))))),
    CONSTRAINT ck_import_batch_error_rows_range CHECK (((error_row_count >= 0) AND (error_row_count <= row_count))),
    CONSTRAINT ck_import_batch_name_nonempty CHECK ((NOT ((original_name)::text = ''::text))),
    CONSTRAINT ck_import_batch_row_count_nonneg CHECK ((row_count >= 0)),
    CONSTRAINT ck_import_batch_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_import_batch_sha256_fmt CHECK (((file_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_import_batch_staged_has_ts CHECK ((((status)::text = 'RECEIVED'::text) OR ((status)::text = 'REJECTED'::text) OR (staged_at IS NOT NULL))),
    CONSTRAINT ck_import_batch_status CHECK (((status)::text = ANY ((ARRAY['RECEIVED'::character varying, 'STAGED'::character varying, 'VALIDATED'::character varying, 'REJECTED'::character varying, 'SUPERSEDED'::character varying, 'APPLIED'::character varying, 'COMPENSATED'::character varying])::text[]))),
    CONSTRAINT ck_import_batch_validated_has_ts CHECK (((NOT ((status)::text = ANY ((ARRAY['VALIDATED'::character varying, 'SUPERSEDED'::character varying, 'APPLIED'::character varying, 'COMPENSATED'::character varying])::text[]))) OR (validated_at IS NOT NULL)))
);


--
-- Name: platform_import_staging_row; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_import_staging_row (
    id bigint NOT NULL,
    sheet_name character varying(100) NOT NULL,
    row_number integer NOT NULL,
    payload jsonb NOT NULL,
    payload_sha256 character varying(64) NOT NULL,
    validation_status character varying(16) DEFAULT 'NEW'::character varying NOT NULL,
    error_codes jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    batch_id uuid NOT NULL,
    CONSTRAINT ck_staging_row_error_codes_array CHECK ((jsonb_typeof(error_codes) = 'array'::text)),
    CONSTRAINT ck_staging_row_error_has_codes CHECK (((NOT ((validation_status)::text = 'ERROR'::text)) OR (NOT (error_codes = '[]'::jsonb)))),
    CONSTRAINT ck_staging_row_number_pos CHECK ((row_number >= 1)),
    CONSTRAINT ck_staging_row_payload_object CHECK ((jsonb_typeof(payload) = 'object'::text)),
    CONSTRAINT ck_staging_row_payload_sha256_fmt CHECK (((payload_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_staging_row_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_staging_row_status CHECK (((validation_status)::text = ANY ((ARRAY['NEW'::character varying, 'PENDING_REVIEW'::character varying, 'ERROR'::character varying, 'MATCHED'::character varying, 'REJECTED'::character varying, 'APPROVED'::character varying])::text[])))
);


--
-- Name: platform_import_staging_row_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_import_staging_row ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_import_staging_row_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_inbox_event; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_inbox_event (
    id bigint NOT NULL,
    consumer character varying(150) NOT NULL,
    event_id uuid NOT NULL,
    event_type character varying(150) NOT NULL,
    attempt integer NOT NULL,
    processed_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    CONSTRAINT ck_inbox_event_attempt_pos CHECK ((attempt >= 1)),
    CONSTRAINT ck_inbox_event_consumer_fmt CHECK (((consumer)::text ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)+$'::text)),
    CONSTRAINT ck_inbox_event_type_fmt CHECK (((event_type)::text ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)+$'::text))
);


--
-- Name: platform_inbox_event_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_inbox_event ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_inbox_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_integration_source; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_integration_source (
    id smallint NOT NULL,
    code character varying(64) NOT NULL,
    name_fa character varying(200) NOT NULL,
    kind character varying(16) NOT NULL,
    direction character varying(16) DEFAULT 'READ_ONLY'::character varying NOT NULL,
    policy_decision_id character varying(7) NOT NULL,
    staleness_threshold interval NOT NULL,
    threshold_basis character varying(20) DEFAULT 'TECHNICAL_DEFAULT'::character varying NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    last_success_at timestamp with time zone,
    last_as_of timestamp with time zone,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    last_success_batch_id uuid,
    CONSTRAINT ck_integration_source_code_fmt CHECK (((code)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text)),
    CONSTRAINT ck_integration_source_decision_fmt CHECK (((policy_decision_id)::text ~ '^DEC-[0-9]{3}$'::text)),
    CONSTRAINT ck_integration_source_kind CHECK (((kind)::text = ANY ((ARRAY['EXCEL_FILE'::character varying, 'XLSM_FILE'::character varying])::text[]))),
    CONSTRAINT ck_integration_source_last_success_pair CHECK ((((last_success_at IS NULL) AND (last_success_batch_id IS NULL)) OR ((last_success_at IS NOT NULL) AND (last_success_batch_id IS NOT NULL)))),
    CONSTRAINT ck_integration_source_name_nonempty CHECK ((NOT ((name_fa)::text = ''::text))),
    CONSTRAINT ck_integration_source_read_only CHECK (((direction)::text = 'READ_ONLY'::text)),
    CONSTRAINT ck_integration_source_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_integration_source_threshold_basis CHECK (((threshold_basis)::text = ANY ((ARRAY['TECHNICAL_DEFAULT'::character varying, 'OWNER_APPROVED'::character varying])::text[]))),
    CONSTRAINT ck_integration_source_threshold_pos CHECK ((staleness_threshold > '00:00:00'::interval))
);


--
-- Name: platform_integration_source_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_integration_source ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_integration_source_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_job_definition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_job_definition (
    job_type character varying(64) NOT NULL,
    name_fa character varying(200) NOT NULL,
    cancellable boolean NOT NULL,
    protected boolean NOT NULL,
    decision_id character varying(7) NOT NULL,
    provenance character varying(16) DEFAULT 'MIGRATION_SEED'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_job_definition_decision_fmt CHECK ((((decision_id)::text = ''::text) OR ((decision_id)::text ~ '^DEC-[0-9]{3}$'::text))),
    CONSTRAINT ck_job_definition_name_nonempty CHECK ((NOT ((name_fa)::text = ''::text))),
    CONSTRAINT ck_job_definition_protected_not_cancellable CHECK ((NOT (cancellable AND protected))),
    CONSTRAINT ck_job_definition_provenance CHECK (((provenance)::text = 'MIGRATION_SEED'::text)),
    CONSTRAINT ck_job_definition_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_job_definition_type_fmt CHECK (((job_type)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text))
);


--
-- Name: platform_job_run; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_job_run (
    id uuid NOT NULL,
    task_key character varying(200) NOT NULL,
    worker_task_id character varying(64) NOT NULL,
    state character varying(20) DEFAULT 'QUEUED'::character varying NOT NULL,
    queued_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    progress smallint,
    last_checkpoint_at timestamp with time zone,
    cancel_requested_at timestamp with time zone,
    cancel_reason character varying(500) NOT NULL,
    cancel_too_late boolean DEFAULT false NOT NULL,
    error_code character varying(64) NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    cancel_requested_by_id uuid,
    job_type character varying(64) NOT NULL,
    requested_by_id uuid,
    CONSTRAINT ck_job_run_cancel_reason CHECK (((cancel_requested_at IS NULL) OR ((cancel_requested_by_id IS NOT NULL) AND (length((cancel_reason)::text) >= 3)))),
    CONSTRAINT ck_job_run_cancel_requested CHECK (((NOT ((state)::text = ANY ((ARRAY['CANCEL_REQUESTED'::character varying, 'CANCELLED'::character varying])::text[]))) OR (cancel_requested_at IS NOT NULL))),
    CONSTRAINT ck_job_run_cancel_too_late CHECK (((NOT cancel_too_late) OR ((cancel_requested_at IS NOT NULL) AND ((state)::text = ANY ((ARRAY['SUCCEEDED'::character varying, 'FAILED'::character varying])::text[]))))),
    CONSTRAINT ck_job_run_error_code_fmt CHECK ((((error_code)::text = ''::text) OR ((error_code)::text ~ '^[A-Z][A-Z0-9_]{2,63}$'::text))),
    CONSTRAINT ck_job_run_failed_has_code CHECK (((NOT ((state)::text = 'FAILED'::text)) OR ((error_code)::text ~ '^[A-Z][A-Z0-9_]{2,63}$'::text))),
    CONSTRAINT ck_job_run_live_not_finished CHECK ((((state)::text = ANY ((ARRAY['CANCELLED'::character varying, 'SUCCEEDED'::character varying, 'FAILED'::character varying])::text[])) OR (finished_at IS NULL))),
    CONSTRAINT ck_job_run_progress_range CHECK (((progress IS NULL) OR ((progress >= 0) AND (progress <= 100)))),
    CONSTRAINT ck_job_run_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_job_run_running_started CHECK (((NOT ((state)::text = ANY ((ARRAY['RUNNING'::character varying, 'CANCEL_REQUESTED'::character varying])::text[]))) OR (started_at IS NOT NULL))),
    CONSTRAINT ck_job_run_state CHECK (((state)::text = ANY ((ARRAY['QUEUED'::character varying, 'RUNNING'::character varying, 'CANCEL_REQUESTED'::character varying, 'CANCELLED'::character varying, 'SUCCEEDED'::character varying, 'FAILED'::character varying])::text[]))),
    CONSTRAINT ck_job_run_task_key_nonempty CHECK ((NOT ((task_key)::text = ''::text))),
    CONSTRAINT ck_job_run_terminal_finished CHECK (((NOT ((state)::text = ANY ((ARRAY['CANCELLED'::character varying, 'SUCCEEDED'::character varying, 'FAILED'::character varying])::text[]))) OR (finished_at IS NOT NULL)))
);


--
-- Name: platform_login_attempt; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_login_attempt (
    id bigint NOT NULL,
    occurred_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    username_attempted character varying(64) NOT NULL,
    outcome character varying(24) NOT NULL,
    client_ip inet,
    network_zone character varying(8) NOT NULL,
    request_id uuid,
    user_id uuid,
    session_id uuid,
    CONSTRAINT ck_login_attempt_outcome CHECK (((outcome)::text = ANY ((ARRAY['OK'::character varying, 'INVALID_CREDENTIALS'::character varying, 'LOCKED'::character varying, 'DISABLED'::character varying, 'ONE_TIME_EXPIRED'::character varying, 'NETWORK_POLICY_DENIED'::character varying, 'MFA_OK'::character varying, 'MFA_FAILED'::character varying, 'RECOVERY_CODE_USED'::character varying])::text[]))),
    CONSTRAINT ck_login_attempt_zone CHECK (((network_zone)::text = ANY ((ARRAY['INTERNAL'::character varying, 'EXTERNAL'::character varying, 'UNKNOWN'::character varying])::text[])))
);


--
-- Name: platform_login_attempt_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_login_attempt ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_login_attempt_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_mfa_factor; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_mfa_factor (
    id uuid NOT NULL,
    method character varying(8) DEFAULT 'TOTP'::character varying NOT NULL,
    status character varying(8) DEFAULT 'PENDING'::character varying NOT NULL,
    secret_ciphertext bytea,
    key_ref character varying(64) NOT NULL,
    confirmed_at timestamp with time zone,
    last_used_step bigint,
    revoked_at timestamp with time zone,
    revoke_reason character varying(500) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    revoked_by_id uuid,
    user_id uuid NOT NULL,
    CONSTRAINT ck_mfa_factor_active_confirmed CHECK (((NOT ((status)::text = 'ACTIVE'::text)) OR (confirmed_at IS NOT NULL))),
    CONSTRAINT ck_mfa_factor_key_ref CHECK (((secret_ciphertext IS NULL) OR (NOT ((key_ref)::text = ''::text)))),
    CONSTRAINT ck_mfa_factor_live_has_secret CHECK ((((status)::text = 'REVOKED'::text) OR ((revoked_at IS NULL) AND (secret_ciphertext IS NOT NULL)))),
    CONSTRAINT ck_mfa_factor_method CHECK (((method)::text = 'TOTP'::text)),
    CONSTRAINT ck_mfa_factor_revoked_no_secret CHECK (((NOT ((status)::text = 'REVOKED'::text)) OR ((revoked_at IS NOT NULL) AND (secret_ciphertext IS NULL)))),
    CONSTRAINT ck_mfa_factor_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_mfa_factor_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'ACTIVE'::character varying, 'REVOKED'::character varying])::text[])))
);


--
-- Name: platform_org_unit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_org_unit (
    id uuid NOT NULL,
    code character varying(64) NOT NULL,
    name_fa character varying(200) NOT NULL,
    status character varying(8) DEFAULT 'ACTIVE'::character varying NOT NULL,
    effective_from timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    provenance character varying(16) DEFAULT 'SYS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by_id uuid,
    parent_id uuid,
    updated_by_id uuid,
    unit_type_code character varying(32) NOT NULL,
    CONSTRAINT ck_org_unit_code_fmt CHECK (((code)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text)),
    CONSTRAINT ck_org_unit_name_nonempty CHECK ((NOT ((name_fa)::text = ''::text))),
    CONSTRAINT ck_org_unit_not_own_parent CHECK ((NOT ((parent_id = id) AND (parent_id IS NOT NULL)))),
    CONSTRAINT ck_org_unit_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'SEED_SYNTHETIC'::character varying])::text[]))),
    CONSTRAINT ck_org_unit_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_org_unit_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying])::text[]))),
    CONSTRAINT ck_org_unit_synthetic_label CHECK (((NOT ((provenance)::text = 'SEED_SYNTHETIC'::text)) OR ((name_fa)::text ~~ '%محیط آزمایشی — داده ساختگی%'::text)))
);


--
-- Name: platform_org_unit_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_org_unit_history (
    id bigint NOT NULL,
    unit_row_version bigint NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    code character varying(64) NOT NULL,
    name_fa character varying(200) NOT NULL,
    unit_type_code character varying(32) NOT NULL,
    status character varying(8) NOT NULL,
    recorded_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    changed_by_id uuid,
    parent_id uuid,
    unit_id uuid NOT NULL,
    CONSTRAINT ck_org_unit_history_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying])::text[]))),
    CONSTRAINT ck_org_unit_history_validity CHECK (((valid_to IS NULL) OR (valid_to >= valid_from)))
);


--
-- Name: platform_org_unit_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_org_unit_history ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_org_unit_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_org_unit_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_org_unit_type (
    code character varying(32) NOT NULL,
    name_fa character varying(100) NOT NULL,
    sort_order smallint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    decision_id character varying(7) NOT NULL,
    provenance character varying(16) DEFAULT 'SYS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by_id uuid,
    CONSTRAINT ck_org_unit_type_code_fmt CHECK (((code)::text ~ '^[A-Z][A-Z_]{1,31}$'::text)),
    CONSTRAINT ck_org_unit_type_decision_fmt CHECK ((((decision_id)::text = ''::text) OR ((decision_id)::text ~ '^DEC-[0-9]{3}$'::text))),
    CONSTRAINT ck_org_unit_type_name_nonempty CHECK ((NOT ((name_fa)::text = ''::text))),
    CONSTRAINT ck_org_unit_type_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'MIGRATION_SEED'::character varying])::text[]))),
    CONSTRAINT ck_org_unit_type_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_org_unit_type_seed_has_decision CHECK (((NOT ((provenance)::text = 'MIGRATION_SEED'::text)) OR (NOT ((decision_id)::text = ''::text)))),
    CONSTRAINT ck_org_unit_type_sort_nonneg CHECK ((sort_order >= 0))
);


--
-- Name: platform_outbox_event; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_outbox_event (
    id bigint NOT NULL,
    event_id uuid NOT NULL,
    event_type character varying(150) NOT NULL,
    schema_version integer DEFAULT 1 NOT NULL,
    aggregate_type character varying(100) NOT NULL,
    aggregate_id character varying(64) NOT NULL,
    aggregate_version bigint NOT NULL,
    occurred_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    actor_type character varying(16) NOT NULL,
    actor_id uuid,
    request_id uuid,
    correlation_id uuid,
    causation_id uuid,
    payload jsonb NOT NULL,
    delivery_status character varying(16) DEFAULT 'PENDING'::character varying NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    last_error text NOT NULL,
    dispatched_at timestamp with time zone,
    acked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_outbox_event_acked_has_ts CHECK (((NOT ((delivery_status)::text = 'ACKED'::text)) OR (acked_at IS NOT NULL))),
    CONSTRAINT ck_outbox_event_actor_id_for_user CHECK (((NOT ((actor_type)::text = 'USER'::text)) OR (actor_id IS NOT NULL))),
    CONSTRAINT ck_outbox_event_actor_type CHECK (((actor_type)::text = ANY ((ARRAY['USER'::character varying, 'SYSTEM'::character varying, 'ANONYMOUS'::character varying])::text[]))),
    CONSTRAINT ck_outbox_event_agg_version_nonneg CHECK ((aggregate_version >= 0)),
    CONSTRAINT ck_outbox_event_attempts_nonneg CHECK ((attempts >= 0)),
    CONSTRAINT ck_outbox_event_delivery_status CHECK (((delivery_status)::text = ANY ((ARRAY['PENDING'::character varying, 'DISPATCHED'::character varying, 'ACKED'::character varying, 'FAILED'::character varying, 'DEAD_LETTER'::character varying])::text[]))),
    CONSTRAINT ck_outbox_event_dispatched_has_ts CHECK (((NOT ((delivery_status)::text = 'DISPATCHED'::text)) OR (dispatched_at IS NOT NULL))),
    CONSTRAINT ck_outbox_event_payload_object CHECK ((jsonb_typeof(payload) = 'object'::text)),
    CONSTRAINT ck_outbox_event_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_outbox_event_schema_version_pos CHECK ((schema_version >= 1)),
    CONSTRAINT ck_outbox_event_type_fmt CHECK (((event_type)::text ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_-]*)+$'::text))
);


--
-- Name: platform_outbox_event_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_outbox_event ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_outbox_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_parameter_definition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_parameter_definition (
    key character varying(64) NOT NULL,
    label_fa character varying(200) NOT NULL,
    datatype character varying(8) NOT NULL,
    unit character varying(16) NOT NULL,
    owner_module character varying(32) NOT NULL,
    classification character varying(16) NOT NULL,
    decision_id character varying(7) NOT NULL,
    min_value numeric(20,4),
    max_value numeric(20,4),
    allowed_values jsonb,
    description_fa character varying(500) NOT NULL,
    provenance character varying(16) DEFAULT 'SYS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by_id uuid,
    CONSTRAINT ck_parameter_definition_bounds CHECK (((min_value IS NULL) OR (max_value IS NULL) OR (min_value <= max_value))),
    CONSTRAINT ck_parameter_definition_classification CHECK (((classification)::text = ANY ((ARRAY['TECHNICAL'::character varying, 'OWNER_POLICY'::character varying, 'BUSINESS_RULE'::character varying])::text[]))),
    CONSTRAINT ck_parameter_definition_datatype CHECK (((datatype)::text = ANY ((ARRAY['STRING'::character varying, 'INTEGER'::character varying, 'DECIMAL'::character varying, 'BOOLEAN'::character varying, 'DATE'::character varying, 'DURATION'::character varying, 'ENUM'::character varying])::text[]))),
    CONSTRAINT ck_parameter_definition_decision_fmt CHECK ((((decision_id)::text = ''::text) OR ((decision_id)::text ~ '^DEC-[0-9]{3}$'::text))),
    CONSTRAINT ck_parameter_definition_decision_required CHECK ((((classification)::text = 'TECHNICAL'::text) OR (NOT ((decision_id)::text = ''::text)))),
    CONSTRAINT ck_parameter_definition_enum_values CHECK (((((datatype)::text = 'ENUM'::text) AND (allowed_values IS NOT NULL)) OR ((NOT ((datatype)::text = 'ENUM'::text)) AND (allowed_values IS NULL)))),
    CONSTRAINT ck_parameter_definition_key_fmt CHECK (((key)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text)),
    CONSTRAINT ck_parameter_definition_label_nonempty CHECK ((NOT ((label_fa)::text = ''::text))),
    CONSTRAINT ck_parameter_definition_module_fmt CHECK (((owner_module)::text ~ '^[a-z][a-z0-9_]{1,31}$'::text)),
    CONSTRAINT ck_parameter_definition_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'MIGRATION_SEED'::character varying])::text[]))),
    CONSTRAINT ck_parameter_definition_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_parameter_definition_unit CHECK (((unit)::text = ANY ((ARRAY[''::character varying, 'count'::character varying, 'characters'::character varying, 'seconds'::character varying, 'minutes'::character varying, 'hours'::character varying, 'days'::character varying, 'months'::character varying, 'bytes'::character varying, 'levels'::character varying])::text[])))
);


--
-- Name: platform_parameter_value; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_parameter_value (
    id uuid NOT NULL,
    value character varying(500) NOT NULL,
    status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    decision_id character varying(7) NOT NULL,
    reason character varying(500) NOT NULL,
    provenance character varying(16) DEFAULT 'SYS'::character varying NOT NULL,
    proposed_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    published_at timestamp with time zone,
    superseded_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    approval_request_id uuid,
    parameter_key character varying(64) NOT NULL,
    proposed_by_id uuid,
    published_by_id uuid,
    CONSTRAINT ck_parameter_value_decision_fmt CHECK ((((decision_id)::text = ''::text) OR ((decision_id)::text ~ '^DEC-[0-9]{3}$'::text))),
    CONSTRAINT ck_parameter_value_proposer CHECK ((((proposed_by_id IS NULL) AND ((provenance)::text = 'MIGRATION_SEED'::text)) OR ((proposed_by_id IS NOT NULL) AND ((provenance)::text = 'SYS'::text)))),
    CONSTRAINT ck_parameter_value_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'MIGRATION_SEED'::character varying])::text[]))),
    CONSTRAINT ck_parameter_value_published_has_publisher CHECK (((NOT ((status)::text = ANY ((ARRAY['PUBLISHED'::character varying, 'SUPERSEDED'::character varying])::text[]))) OR ((published_at IS NOT NULL) AND (((provenance)::text = 'MIGRATION_SEED'::text) OR (published_by_id IS NOT NULL))))),
    CONSTRAINT ck_parameter_value_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_parameter_value_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'PENDING_APPROVAL'::character varying, 'PUBLISHED'::character varying, 'SUPERSEDED'::character varying, 'REJECTED'::character varying])::text[]))),
    CONSTRAINT ck_parameter_value_superseded_at CHECK (((NOT ((status)::text = 'SUPERSEDED'::text)) OR (superseded_at IS NOT NULL)))
);


--
-- Name: platform_password_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_password_history (
    id bigint NOT NULL,
    password_hash character varying(256) NOT NULL,
    set_at timestamp with time zone NOT NULL,
    recorded_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    user_id uuid NOT NULL,
    CONSTRAINT ck_password_history_hash_fmt CHECK (((password_hash)::text ~ '^[a-z0-9_]{3,32}\$.+$'::text))
);


--
-- Name: platform_password_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_password_history ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_password_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_permission; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_permission (
    action character varying(120) NOT NULL,
    module character varying(32) NOT NULL,
    description_fa character varying(300) NOT NULL,
    sensitivity character varying(2) NOT NULL,
    mfa_step_up boolean NOT NULL,
    business_approval boolean NOT NULL,
    maker_checker boolean NOT NULL,
    matrix_version character varying(16) NOT NULL,
    decision_id character varying(7) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    CONSTRAINT ck_permission_action_fmt CHECK (((action)::text ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$'::text)),
    CONSTRAINT ck_permission_ba_is_sod_and_mfa CHECK (((NOT business_approval) OR (maker_checker AND mfa_step_up))),
    CONSTRAINT ck_permission_decision_fmt CHECK (((decision_id)::text ~ '^DEC-[0-9]{3}$'::text)),
    CONSTRAINT ck_permission_description_nonempty CHECK ((NOT ((description_fa)::text = ''::text))),
    CONSTRAINT ck_permission_matrix_version_fmt CHECK (((matrix_version)::text ~ '^[0-9]+\.[0-9]+$'::text)),
    CONSTRAINT ck_permission_module_fmt CHECK (((module)::text ~ '^[a-z][a-z0-9_]{1,31}$'::text)),
    CONSTRAINT ck_permission_sensitivity CHECK (((sensitivity)::text = ANY ((ARRAY[''::character varying, 'S0'::character varying, 'S1'::character varying, 'S2'::character varying, 'S3'::character varying])::text[])))
);


--
-- Name: platform_position; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_position (
    id uuid NOT NULL,
    code character varying(64) NOT NULL,
    title_fa character varying(200) NOT NULL,
    is_unit_head boolean DEFAULT false NOT NULL,
    primary_capacity smallint DEFAULT 1 NOT NULL,
    status character varying(8) DEFAULT 'ACTIVE'::character varying NOT NULL,
    effective_from timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    provenance character varying(16) DEFAULT 'SYS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by_id uuid,
    reports_to_id uuid,
    unit_id uuid NOT NULL,
    updated_by_id uuid,
    CONSTRAINT ck_position_capacity_pos CHECK ((primary_capacity >= 1)),
    CONSTRAINT ck_position_code_fmt CHECK (((code)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text)),
    CONSTRAINT ck_position_head_capacity_one CHECK (((NOT is_unit_head) OR (primary_capacity = 1))),
    CONSTRAINT ck_position_not_own_manager CHECK ((NOT ((reports_to_id = id) AND (reports_to_id IS NOT NULL)))),
    CONSTRAINT ck_position_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'SEED_SYNTHETIC'::character varying])::text[]))),
    CONSTRAINT ck_position_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_position_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying])::text[]))),
    CONSTRAINT ck_position_synthetic_label CHECK (((NOT ((provenance)::text = 'SEED_SYNTHETIC'::text)) OR ((title_fa)::text ~~ '%محیط آزمایشی — داده ساختگی%'::text))),
    CONSTRAINT ck_position_title_nonempty CHECK ((NOT ((title_fa)::text = ''::text)))
);


--
-- Name: platform_position_assignment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_position_assignment (
    id uuid NOT NULL,
    kind character varying(8) NOT NULL,
    valid_from timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    valid_to timestamp with time zone,
    reason character varying(500) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by_id uuid,
    position_id uuid NOT NULL,
    updated_by_id uuid,
    user_id uuid NOT NULL,
    CONSTRAINT ck_position_assignment_acting_has_end CHECK (((NOT ((kind)::text = 'ACTING'::text)) OR (valid_to IS NOT NULL))),
    CONSTRAINT ck_position_assignment_kind CHECK (((kind)::text = ANY ((ARRAY['PRIMARY'::character varying, 'ACTING'::character varying])::text[]))),
    CONSTRAINT ck_position_assignment_reason CHECK ((length((reason)::text) >= 3)),
    CONSTRAINT ck_position_assignment_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_position_assignment_validity CHECK (((valid_to IS NULL) OR (valid_to > valid_from)))
);


--
-- Name: platform_position_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_position_history (
    id bigint NOT NULL,
    position_row_version bigint NOT NULL,
    valid_from timestamp with time zone NOT NULL,
    valid_to timestamp with time zone,
    code character varying(64) NOT NULL,
    title_fa character varying(200) NOT NULL,
    is_unit_head boolean NOT NULL,
    primary_capacity smallint NOT NULL,
    status character varying(8) NOT NULL,
    recorded_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    changed_by_id uuid,
    position_id uuid NOT NULL,
    reports_to_id uuid,
    unit_id uuid NOT NULL,
    CONSTRAINT ck_position_history_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying])::text[]))),
    CONSTRAINT ck_position_history_validity CHECK (((valid_to IS NULL) OR (valid_to >= valid_from)))
);


--
-- Name: platform_position_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_position_history ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_position_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_recovery_code; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_recovery_code (
    id bigint NOT NULL,
    generation uuid NOT NULL,
    code_hash character varying(256) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    used_at timestamp with time zone,
    user_id uuid NOT NULL,
    CONSTRAINT ck_recovery_code_hash_fmt CHECK (((code_hash)::text ~ '^[a-z0-9_]{3,32}\$.+$'::text))
);


--
-- Name: platform_recovery_code_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_recovery_code ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_recovery_code_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_role; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_role (
    id uuid NOT NULL,
    code character varying(64) NOT NULL,
    name_fa character varying(200) NOT NULL,
    kind character varying(16) NOT NULL,
    status character varying(8) DEFAULT 'DRAFT'::character varying NOT NULL,
    matrix_version character varying(16) NOT NULL,
    decision_id character varying(7) NOT NULL,
    provenance character varying(16) DEFAULT 'SYS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by_id uuid,
    updated_by_id uuid,
    CONSTRAINT ck_role_active_has_matrix CHECK (((NOT ((status)::text = 'ACTIVE'::text)) OR (NOT ((matrix_version)::text = ''::text)))),
    CONSTRAINT ck_role_code_fmt CHECK (((code)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text)),
    CONSTRAINT ck_role_decision_fmt CHECK ((((decision_id)::text = ''::text) OR ((decision_id)::text ~ '^DEC-[0-9]{3}$'::text))),
    CONSTRAINT ck_role_kind CHECK (((kind)::text = ANY ((ARRAY['TECHNICAL'::character varying, 'BUSINESS'::character varying])::text[]))),
    CONSTRAINT ck_role_matrix_version_fmt CHECK ((((matrix_version)::text = ''::text) OR ((matrix_version)::text ~ '^[0-9]+\.[0-9]+$'::text))),
    CONSTRAINT ck_role_name_nonempty CHECK ((NOT ((name_fa)::text = ''::text))),
    CONSTRAINT ck_role_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'MIGRATION_SEED'::character varying])::text[]))),
    CONSTRAINT ck_role_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_role_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'ACTIVE'::character varying, 'RETIRED'::character varying])::text[])))
);


--
-- Name: platform_role_assignment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_role_assignment (
    id uuid NOT NULL,
    scope_kind character varying(20) NOT NULL,
    valid_from timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    valid_to timestamp with time zone,
    status character varying(20) NOT NULL,
    granted_via character varying(20) DEFAULT 'ADMIN'::character varying NOT NULL,
    requires_second_approval boolean DEFAULT false NOT NULL,
    reason character varying(500) NOT NULL,
    revoked_at timestamp with time zone,
    revoke_reason character varying(500) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    approval_request_id uuid,
    granted_by_id uuid,
    revoked_by_id uuid,
    role_id uuid NOT NULL,
    scope_unit_id uuid,
    updated_by_id uuid,
    user_id uuid NOT NULL,
    self_assignment boolean GENERATED ALWAYS AS (COALESCE((granted_by_id = user_id), false)) STORED,
    CONSTRAINT ck_role_assignment_granted_by CHECK ((((granted_by_id IS NOT NULL) AND ((granted_via)::text = 'ADMIN'::text)) OR ((granted_by_id IS NULL) AND ((granted_via)::text = 'CONSOLE_BOOTSTRAP'::text)))),
    CONSTRAINT ck_role_assignment_granted_via CHECK (((granted_via)::text = ANY ((ARRAY['ADMIN'::character varying, 'CONSOLE_BOOTSTRAP'::character varying])::text[]))),
    CONSTRAINT ck_role_assignment_reason CHECK ((length((reason)::text) >= 3)),
    CONSTRAINT ck_role_assignment_revoked_reason CHECK (((NOT ((status)::text = 'REVOKED'::text)) OR ((revoked_at IS NOT NULL) AND (length((revoke_reason)::text) >= 3)))),
    CONSTRAINT ck_role_assignment_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_role_assignment_scope_kind CHECK (((scope_kind)::text = ANY ((ARRAY['GLOBAL'::character varying, 'ORG_UNIT'::character varying, 'ORG_UNIT_SUBTREE'::character varying])::text[]))),
    CONSTRAINT ck_role_assignment_scope_ref CHECK (((((scope_kind)::text = 'GLOBAL'::text) AND (scope_unit_id IS NULL)) OR (((scope_kind)::text = ANY ((ARRAY['ORG_UNIT'::character varying, 'ORG_UNIT_SUBTREE'::character varying])::text[])) AND (scope_unit_id IS NOT NULL)))),
    CONSTRAINT ck_role_assignment_second_approval CHECK (((NOT requires_second_approval) OR (NOT ((status)::text = 'ACTIVE'::text)) OR (approval_request_id IS NOT NULL))),
    CONSTRAINT ck_role_assignment_status CHECK (((status)::text = ANY ((ARRAY['PENDING_APPROVAL'::character varying, 'ACTIVE'::character varying, 'EXPIRED'::character varying, 'REVOKED'::character varying])::text[]))),
    CONSTRAINT ck_role_assignment_validity CHECK (((valid_to IS NULL) OR (valid_to > valid_from)))
);


--
-- Name: platform_role_permission; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_role_permission (
    id bigint NOT NULL,
    grant_mode character varying(20) NOT NULL,
    max_sensitivity character varying(2) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    permission_action character varying(120) NOT NULL,
    role_id uuid NOT NULL,
    CONSTRAINT ck_role_permission_max_sensitivity CHECK (((max_sensitivity)::text = ANY ((ARRAY[''::character varying, 'S1'::character varying, 'S2'::character varying, 'S3'::character varying])::text[]))),
    CONSTRAINT ck_role_permission_mode CHECK (((grant_mode)::text = ANY ((ARRAY['SCOPE'::character varying, 'OWN'::character varying, 'OWN_UNIT'::character varying, 'OWN_AND_OWN_UNIT'::character varying])::text[])))
);


--
-- Name: platform_role_permission_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_role_permission ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_role_permission_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: platform_schema_meta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_schema_meta (
    id smallint NOT NULL,
    schema_contract character varying(32) NOT NULL,
    seeded_by_migration character varying(100) NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    CONSTRAINT ck_schema_meta_contract_nonempty CHECK ((NOT ((schema_contract)::text = ''::text))),
    CONSTRAINT ck_schema_meta_singleton CHECK ((id = 1))
);


--
-- Name: platform_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_session (
    id uuid NOT NULL,
    session_key_hash character varying(64) NOT NULL,
    state character varying(16) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    idle_expires_at timestamp with time zone NOT NULL,
    absolute_expires_at timestamp with time zone NOT NULL,
    mfa_verified_at timestamp with time zone,
    network_zone character varying(8) NOT NULL,
    client_ip inet,
    user_agent_hash character varying(64) NOT NULL,
    ended_at timestamp with time zone,
    end_reason character varying(20) NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    revoked_by_id uuid,
    user_id uuid NOT NULL,
    CONSTRAINT ck_session_absolute_after_create CHECK ((absolute_expires_at > created_at)),
    CONSTRAINT ck_session_end_reason CHECK (((end_reason)::text = ANY ((ARRAY[''::character varying, 'IDLE_TIMEOUT'::character varying, 'ABSOLUTE_TIMEOUT'::character varying, 'MFA_TIMEOUT'::character varying, 'LOGOUT'::character varying, 'SELF_REVOKE'::character varying, 'ADMIN_REVOKE'::character varying, 'USER_DISABLED'::character varying, 'PASSWORD_CHANGED'::character varying, 'MFA_RESET'::character varying, 'CONCURRENT_LIMIT'::character varying])::text[]))),
    CONSTRAINT ck_session_ended_has_reason CHECK (((NOT ((state)::text = ANY ((ARRAY['EXPIRED'::character varying, 'REVOKED'::character varying, 'LOGGED_OUT'::character varying])::text[]))) OR ((ended_at IS NOT NULL) AND (NOT ((end_reason)::text = ''::text))))),
    CONSTRAINT ck_session_idle_le_absolute CHECK ((idle_expires_at <= absolute_expires_at)),
    CONSTRAINT ck_session_key_hash_fmt CHECK (((session_key_hash)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_session_live_not_ended CHECK (((NOT ((state)::text = ANY ((ARRAY['MFA_PENDING'::character varying, 'ACTIVE'::character varying])::text[]))) OR (((end_reason)::text = ''::text) AND (ended_at IS NULL)))),
    CONSTRAINT ck_session_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_session_state CHECK (((state)::text = ANY ((ARRAY['MFA_PENDING'::character varying, 'ACTIVE'::character varying, 'EXPIRED'::character varying, 'REVOKED'::character varying, 'LOGGED_OUT'::character varying])::text[]))),
    CONSTRAINT ck_session_ua_hash_fmt CHECK ((((user_agent_hash)::text = ''::text) OR ((user_agent_hash)::text ~ '^[0-9a-f]{64}$'::text))),
    CONSTRAINT ck_session_zone CHECK (((network_zone)::text = ANY ((ARRAY['INTERNAL'::character varying, 'EXTERNAL'::character varying, 'UNKNOWN'::character varying])::text[])))
);


--
-- Name: platform_stored_object; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_stored_object (
    storage_key character varying(64) NOT NULL,
    volume character varying(64) NOT NULL,
    size_bytes bigint NOT NULL,
    sha256 character varying(64) NOT NULL,
    encryption_scheme character varying(20) NOT NULL,
    key_ref character varying(64) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    purge_after timestamp with time zone,
    bytes_purged_at timestamp with time zone,
    CONSTRAINT ck_stored_object_encryption CHECK (((encryption_scheme)::text = 'ENCRYPTED_VOLUME'::text)),
    CONSTRAINT ck_stored_object_key_ref_nonempty CHECK ((NOT ((key_ref)::text = ''::text))),
    CONSTRAINT ck_stored_object_purge_scheduled CHECK (((bytes_purged_at IS NULL) OR (purge_after IS NOT NULL))),
    CONSTRAINT ck_stored_object_sha256_fmt CHECK (((sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_stored_object_size_pos CHECK ((size_bytes > 0)),
    CONSTRAINT ck_stored_object_storage_key_fmt CHECK (((storage_key)::text ~ '^[A-Za-z0-9_-]{32,64}$'::text)),
    CONSTRAINT ck_stored_object_volume_fmt CHECK (((volume)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text))
);


--
-- Name: platform_upload_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_upload_type (
    extension character varying(8) NOT NULL,
    media_type character varying(127) NOT NULL,
    label_fa character varying(100) NOT NULL,
    content_check character varying(32) NOT NULL,
    is_allowed boolean DEFAULT true NOT NULL,
    decision_id character varying(7) NOT NULL,
    provenance character varying(16) DEFAULT 'MIGRATION_SEED'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    CONSTRAINT ck_upload_type_content_check CHECK (((content_check)::text = ANY ((ARRAY['PDF'::character varying, 'PNG'::character varying, 'JPEG'::character varying, 'DXF'::character varying, 'OOXML_NO_MACRO'::character varying])::text[]))),
    CONSTRAINT ck_upload_type_decision_fmt CHECK (((decision_id)::text ~ '^DEC-[0-9]{3}$'::text)),
    CONSTRAINT ck_upload_type_extension_fmt CHECK (((extension)::text ~ '^[a-z0-9]{2,8}$'::text)),
    CONSTRAINT ck_upload_type_media_type_fmt CHECK (((media_type)::text ~ '^[a-z]+/[a-z0-9.+-]+$'::text)),
    CONSTRAINT ck_upload_type_never_forbidden CHECK ((NOT ((extension)::text = ANY ((ARRAY['xlsm'::character varying, 'xltm'::character varying, 'xlam'::character varying, 'xlsb'::character varying, 'docm'::character varying, 'dotm'::character varying, 'pptm'::character varying, 'potm'::character varying, 'exe'::character varying, 'dll'::character varying, 'com'::character varying, 'scr'::character varying, 'msi'::character varying, 'bat'::character varying, 'cmd'::character varying, 'ps1'::character varying, 'vbs'::character varying, 'vbe'::character varying, 'js'::character varying, 'jse'::character varying, 'wsf'::character varying, 'hta'::character varying, 'sh'::character varying, 'py'::character varying, 'jar'::character varying, 'html'::character varying, 'htm'::character varying, 'svg'::character varying])::text[])))),
    CONSTRAINT ck_upload_type_provenance CHECK (((provenance)::text = 'MIGRATION_SEED'::text))
);


--
-- Name: platform_user; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_user (
    id uuid NOT NULL,
    username character varying(64) NOT NULL,
    display_name character varying(200) NOT NULL,
    status character varying(16) DEFAULT 'CREATED'::character varying NOT NULL,
    account_kind character varying(16) NOT NULL,
    network_policy character varying(24) NOT NULL,
    mfa_enrolled boolean DEFAULT false NOT NULL,
    is_break_glass boolean DEFAULT false NOT NULL,
    last_login_at timestamp with time zone,
    failed_login_count integer DEFAULT 0 NOT NULL,
    locked_until timestamp with time zone,
    status_changed_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    provenance character varying(16) DEFAULT 'SYS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by_id uuid,
    updated_by_id uuid,
    CONSTRAINT ck_user_account_kind CHECK (((account_kind)::text = ANY ((ARRAY['PERSON'::character varying, 'OPERATOR'::character varying])::text[]))),
    CONSTRAINT ck_user_break_glass_person CHECK (((NOT is_break_glass) OR ((account_kind)::text = 'PERSON'::text))),
    CONSTRAINT ck_user_display_name_nonempty CHECK ((NOT ((display_name)::text = ''::text))),
    CONSTRAINT ck_user_failed_count_nonneg CHECK ((failed_login_count >= 0)),
    CONSTRAINT ck_user_locked_has_until CHECK (((NOT ((status)::text = 'LOCKED'::text)) OR (locked_until IS NOT NULL))),
    CONSTRAINT ck_user_network_policy CHECK (((network_policy)::text = ANY ((ARRAY['INTERNAL_ONLY'::character varying, 'ANY_WITH_MFA_OUTSIDE'::character varying])::text[]))),
    CONSTRAINT ck_user_operator_internal_only CHECK (((NOT ((account_kind)::text = 'OPERATOR'::text)) OR ((network_policy)::text = 'INTERNAL_ONLY'::text))),
    CONSTRAINT ck_user_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'SEED_SYNTHETIC'::character varying])::text[]))),
    CONSTRAINT ck_user_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_user_status CHECK (((status)::text = ANY ((ARRAY['CREATED'::character varying, 'ACTIVE'::character varying, 'LOCKED'::character varying, 'DISABLED'::character varying])::text[]))),
    CONSTRAINT ck_user_synthetic_label CHECK (((NOT ((provenance)::text = 'SEED_SYNTHETIC'::text)) OR ((display_name)::text ~~ '%محیط آزمایشی — داده ساختگی%'::text))),
    CONSTRAINT ck_user_username_fmt CHECK (((username)::text ~ '^[a-z0-9][a-z0-9._-]{2,63}$'::text))
);


--
-- Name: platform_work_task; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_work_task (
    id uuid NOT NULL,
    subject character varying(300) NOT NULL,
    related_type character varying(64) NOT NULL,
    related_id character varying(64) NOT NULL,
    related_revision bigint,
    assignee_kind character varying(8) NOT NULL,
    status character varying(12) DEFAULT 'OPEN'::character varying NOT NULL,
    due_at timestamp with time zone,
    blocked_reason character varying(500) NOT NULL,
    blocked_by_ref character varying(200) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    completed_at timestamp with time zone,
    closed_at timestamp with time zone,
    cancelled_at timestamp with time zone,
    cancel_reason character varying(500) NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    assignee_position_id uuid,
    assignee_unit_id uuid,
    assignee_user_id uuid,
    cancelled_by_id uuid,
    closed_by_id uuid,
    completed_by_id uuid,
    created_by_id uuid,
    updated_by_id uuid,
    workflow_instance_id uuid,
    CONSTRAINT ck_work_task_assigned_to_user CHECK (((NOT ((status)::text = 'ASSIGNED'::text)) OR ((assignee_kind)::text = 'USER'::text))),
    CONSTRAINT ck_work_task_assignee_kind CHECK (((assignee_kind)::text = ANY ((ARRAY['USER'::character varying, 'ORG_UNIT'::character varying, 'POSITION'::character varying])::text[]))),
    CONSTRAINT ck_work_task_assignee_ref CHECK (((((assignee_kind)::text = 'USER'::text) AND (assignee_position_id IS NULL) AND (assignee_unit_id IS NULL) AND (assignee_user_id IS NOT NULL)) OR (((assignee_kind)::text = 'ORG_UNIT'::text) AND (assignee_position_id IS NULL) AND (assignee_unit_id IS NOT NULL) AND (assignee_user_id IS NULL)) OR (((assignee_kind)::text = 'POSITION'::text) AND (assignee_position_id IS NOT NULL) AND (assignee_unit_id IS NULL) AND (assignee_user_id IS NULL)))),
    CONSTRAINT ck_work_task_blocked_reason CHECK (((NOT ((status)::text = 'BLOCKED'::text)) OR (length((blocked_reason)::text) >= 3))),
    CONSTRAINT ck_work_task_cancel_reason CHECK (((NOT ((status)::text = 'CANCELLED'::text)) OR ((cancelled_at IS NOT NULL) AND (length((cancel_reason)::text) >= 3)))),
    CONSTRAINT ck_work_task_closed_has_verifier CHECK (((NOT ((status)::text = 'CLOSED'::text)) OR ((closed_at IS NOT NULL) AND (closed_by_id IS NOT NULL)))),
    CONSTRAINT ck_work_task_done_has_completer CHECK (((NOT ((status)::text = ANY ((ARRAY['DONE'::character varying, 'CLOSED'::character varying])::text[]))) OR ((completed_at IS NOT NULL) AND (completed_by_id IS NOT NULL)))),
    CONSTRAINT ck_work_task_related_ref CHECK (((((related_id)::text = ''::text) AND (related_revision IS NULL) AND ((related_type)::text = ''::text)) OR (((related_type)::text ~ '^[a-z][a-z0-9_]{0,63}$'::text) AND (NOT ((related_id)::text = ''::text))))),
    CONSTRAINT ck_work_task_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_work_task_status CHECK (((status)::text = ANY ((ARRAY['OPEN'::character varying, 'ASSIGNED'::character varying, 'IN_PROGRESS'::character varying, 'BLOCKED'::character varying, 'DONE'::character varying, 'CLOSED'::character varying, 'CANCELLED'::character varying])::text[]))),
    CONSTRAINT ck_work_task_subject_nonempty CHECK ((NOT ((subject)::text = ''::text))),
    CONSTRAINT ck_work_task_verifier CHECK (((closed_by_id IS NULL) OR (NOT ((closed_by_id = completed_by_id) AND (closed_by_id IS NOT NULL) AND (completed_by_id IS NOT NULL)))))
);


--
-- Name: platform_workflow_definition; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_workflow_definition (
    id uuid NOT NULL,
    key character varying(64) NOT NULL,
    version integer NOT NULL,
    name_fa character varying(200) NOT NULL,
    status character varying(8) DEFAULT 'DRAFT'::character varying NOT NULL,
    steps jsonb NOT NULL,
    decision_id character varying(7) NOT NULL,
    provenance character varying(16) DEFAULT 'MIGRATION_SEED'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_workflow_definition_decision_fmt CHECK ((((decision_id)::text = ''::text) OR ((decision_id)::text ~ '^DEC-[0-9]{3}$'::text))),
    CONSTRAINT ck_workflow_definition_key_fmt CHECK (((key)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text)),
    CONSTRAINT ck_workflow_definition_name_nonempty CHECK ((NOT ((name_fa)::text = ''::text))),
    CONSTRAINT ck_workflow_definition_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'MIGRATION_SEED'::character varying, 'SEED_SYNTHETIC'::character varying])::text[]))),
    CONSTRAINT ck_workflow_definition_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_workflow_definition_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'ACTIVE'::character varying, 'RETIRED'::character varying])::text[]))),
    CONSTRAINT ck_workflow_definition_steps_array CHECK ((jsonb_typeof(steps) = 'array'::text)),
    CONSTRAINT ck_workflow_definition_version_pos CHECK ((version >= 1))
);


--
-- Name: platform_workflow_instance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_workflow_instance (
    id uuid NOT NULL,
    subject_type character varying(64) NOT NULL,
    subject_id character varying(64) NOT NULL,
    status character varying(20) DEFAULT 'RUNNING'::character varying NOT NULL,
    current_step character varying(64) NOT NULL,
    started_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    ended_at timestamp with time zone,
    cancel_requested_at timestamp with time zone,
    cancel_reason character varying(500) NOT NULL,
    failure_code character varying(64) NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    cancel_requested_by_id uuid,
    definition_id uuid NOT NULL,
    started_by_id uuid,
    CONSTRAINT ck_workflow_instance_cancel_reason CHECK (((NOT ((status)::text = ANY ((ARRAY['CANCEL_REQUESTED'::character varying, 'COMPENSATING'::character varying, 'CANCELLED'::character varying])::text[]))) OR ((cancel_requested_at IS NOT NULL) AND (length((cancel_reason)::text) >= 3)))),
    CONSTRAINT ck_workflow_instance_failure_code CHECK (((NOT ((status)::text = 'FAILED'::text)) OR ((failure_code)::text ~ '^[A-Z][A-Z0-9_]{2,63}$'::text))),
    CONSTRAINT ck_workflow_instance_live_not_ended CHECK ((((status)::text = ANY ((ARRAY['COMPLETED'::character varying, 'CANCELLED'::character varying, 'FAILED'::character varying])::text[])) OR (ended_at IS NULL))),
    CONSTRAINT ck_workflow_instance_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_workflow_instance_status CHECK (((status)::text = ANY ((ARRAY['RUNNING'::character varying, 'WAITING'::character varying, 'CANCEL_REQUESTED'::character varying, 'COMPENSATING'::character varying, 'COMPLETED'::character varying, 'CANCELLED'::character varying, 'FAILED'::character varying])::text[]))),
    CONSTRAINT ck_workflow_instance_subject_fmt CHECK (((subject_type)::text ~ '^[a-z][a-z0-9_]{0,63}$'::text)),
    CONSTRAINT ck_workflow_instance_subject_id_nonempty CHECK ((NOT ((subject_id)::text = ''::text))),
    CONSTRAINT ck_workflow_instance_terminal_ended CHECK (((NOT ((status)::text = ANY ((ARRAY['COMPLETED'::character varying, 'CANCELLED'::character varying, 'FAILED'::character varying])::text[]))) OR (ended_at IS NOT NULL)))
);


--
-- Name: platform_workflow_step_event; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_workflow_step_event (
    id bigint NOT NULL,
    seq integer NOT NULL,
    step_key character varying(64) NOT NULL,
    event character varying(24) NOT NULL,
    occurred_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    detail jsonb NOT NULL,
    actor_id uuid,
    instance_id uuid NOT NULL,
    CONSTRAINT ck_workflow_step_event_detail_object CHECK ((jsonb_typeof(detail) = 'object'::text)),
    CONSTRAINT ck_workflow_step_event_kind CHECK (((event)::text = ANY ((ARRAY['ENTERED'::character varying, 'COMPLETED'::character varying, 'FAILED'::character varying, 'COMPENSATION_STARTED'::character varying, 'COMPENSATED'::character varying])::text[]))),
    CONSTRAINT ck_workflow_step_event_seq_pos CHECK ((seq >= 1)),
    CONSTRAINT ck_workflow_step_event_step_nonempty CHECK ((NOT ((step_key)::text = ''::text)))
);


--
-- Name: platform_workflow_step_event_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.platform_workflow_step_event ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.platform_workflow_step_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: platform_org_unit_history ex_org_unit_history_no_overlap; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit_history
    ADD CONSTRAINT ex_org_unit_history_no_overlap EXCLUDE USING gist (unit_id WITH =, tstzrange(valid_from, valid_to, '[)'::text) WITH &&);


--
-- Name: platform_position_assignment ex_position_assignment_no_duplicate; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_assignment
    ADD CONSTRAINT ex_position_assignment_no_duplicate EXCLUDE USING gist (user_id WITH =, position_id WITH =, tstzrange(valid_from, valid_to, '[)'::text) WITH &&);


--
-- Name: platform_position_assignment ex_position_assignment_one_primary; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_assignment
    ADD CONSTRAINT ex_position_assignment_one_primary EXCLUDE USING gist (user_id WITH =, tstzrange(valid_from, valid_to, '[)'::text) WITH &&) WHERE (((kind)::text = 'PRIMARY'::text));


--
-- Name: platform_position_history ex_position_history_no_overlap; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_history
    ADD CONSTRAINT ex_position_history_no_overlap EXCLUDE USING gist (position_id WITH =, tstzrange(valid_from, valid_to, '[)'::text) WITH &&);


--
-- Name: platform_role_assignment ex_role_assignment_no_overlap; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_assignment
    ADD CONSTRAINT ex_role_assignment_no_overlap EXCLUDE USING gist (user_id WITH =, role_id WITH =, scope_kind WITH =, COALESCE(scope_unit_id, '00000000-0000-0000-0000-000000000000'::uuid) WITH =, tstzrange(valid_from, valid_to, '[)'::text) WITH &&) WHERE (((status)::text = ANY ((ARRAY['PENDING_APPROVAL'::character varying, 'ACTIVE'::character varying])::text[])));


--
-- Name: platform_approval_request platform_approval_request_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_approval_request
    ADD CONSTRAINT platform_approval_request_pkey PRIMARY KEY (id);


--
-- Name: platform_audit_event platform_audit_event_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_audit_event
    ADD CONSTRAINT platform_audit_event_pkey PRIMARY KEY (id);


--
-- Name: platform_audit_integrity_run platform_audit_integrity_run_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_audit_integrity_run
    ADD CONSTRAINT platform_audit_integrity_run_pkey PRIMARY KEY (id);


--
-- Name: platform_break_glass_usage platform_break_glass_usage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_break_glass_usage
    ADD CONSTRAINT platform_break_glass_usage_pkey PRIMARY KEY (id);


--
-- Name: platform_compensation_record platform_compensation_record_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_compensation_record
    ADD CONSTRAINT platform_compensation_record_pkey PRIMARY KEY (id);


--
-- Name: platform_conflict_item platform_conflict_item_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_conflict_item
    ADD CONSTRAINT platform_conflict_item_pkey PRIMARY KEY (id);


--
-- Name: platform_credential platform_credential_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_credential
    ADD CONSTRAINT platform_credential_pkey PRIMARY KEY (user_id);


--
-- Name: platform_document platform_document_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document
    ADD CONSTRAINT platform_document_pkey PRIMARY KEY (id);


--
-- Name: platform_document_revision platform_document_revision_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT platform_document_revision_pkey PRIMARY KEY (id);


--
-- Name: platform_dynamic_field_definition platform_dynamic_field_definition_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_dynamic_field_definition
    ADD CONSTRAINT platform_dynamic_field_definition_pkey PRIMARY KEY (id);


--
-- Name: platform_idempotency_record platform_idempotency_record_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_idempotency_record
    ADD CONSTRAINT platform_idempotency_record_pkey PRIMARY KEY (id);


--
-- Name: platform_import_batch platform_import_batch_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_import_batch
    ADD CONSTRAINT platform_import_batch_pkey PRIMARY KEY (id);


--
-- Name: platform_import_staging_row platform_import_staging_row_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_import_staging_row
    ADD CONSTRAINT platform_import_staging_row_pkey PRIMARY KEY (id);


--
-- Name: platform_inbox_event platform_inbox_event_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_inbox_event
    ADD CONSTRAINT platform_inbox_event_pkey PRIMARY KEY (id);


--
-- Name: platform_integration_source platform_integration_source_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_integration_source
    ADD CONSTRAINT platform_integration_source_pkey PRIMARY KEY (id);


--
-- Name: platform_job_definition platform_job_definition_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_job_definition
    ADD CONSTRAINT platform_job_definition_pkey PRIMARY KEY (job_type);


--
-- Name: platform_job_run platform_job_run_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_job_run
    ADD CONSTRAINT platform_job_run_pkey PRIMARY KEY (id);


--
-- Name: platform_login_attempt platform_login_attempt_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_login_attempt
    ADD CONSTRAINT platform_login_attempt_pkey PRIMARY KEY (id);


--
-- Name: platform_mfa_factor platform_mfa_factor_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_mfa_factor
    ADD CONSTRAINT platform_mfa_factor_pkey PRIMARY KEY (id);


--
-- Name: platform_org_unit_history platform_org_unit_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit_history
    ADD CONSTRAINT platform_org_unit_history_pkey PRIMARY KEY (id);


--
-- Name: platform_org_unit platform_org_unit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit
    ADD CONSTRAINT platform_org_unit_pkey PRIMARY KEY (id);


--
-- Name: platform_org_unit_type platform_org_unit_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit_type
    ADD CONSTRAINT platform_org_unit_type_pkey PRIMARY KEY (code);


--
-- Name: platform_outbox_event platform_outbox_event_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_outbox_event
    ADD CONSTRAINT platform_outbox_event_pkey PRIMARY KEY (id);


--
-- Name: platform_parameter_definition platform_parameter_definition_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_parameter_definition
    ADD CONSTRAINT platform_parameter_definition_pkey PRIMARY KEY (key);


--
-- Name: platform_parameter_value platform_parameter_value_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_parameter_value
    ADD CONSTRAINT platform_parameter_value_pkey PRIMARY KEY (id);


--
-- Name: platform_password_history platform_password_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_password_history
    ADD CONSTRAINT platform_password_history_pkey PRIMARY KEY (id);


--
-- Name: platform_permission platform_permission_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_permission
    ADD CONSTRAINT platform_permission_pkey PRIMARY KEY (action);


--
-- Name: platform_position_assignment platform_position_assignment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_assignment
    ADD CONSTRAINT platform_position_assignment_pkey PRIMARY KEY (id);


--
-- Name: platform_position_history platform_position_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_history
    ADD CONSTRAINT platform_position_history_pkey PRIMARY KEY (id);


--
-- Name: platform_position platform_position_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position
    ADD CONSTRAINT platform_position_pkey PRIMARY KEY (id);


--
-- Name: platform_recovery_code platform_recovery_code_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_recovery_code
    ADD CONSTRAINT platform_recovery_code_pkey PRIMARY KEY (id);


--
-- Name: platform_role_assignment platform_role_assignment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_assignment
    ADD CONSTRAINT platform_role_assignment_pkey PRIMARY KEY (id);


--
-- Name: platform_role_permission platform_role_permission_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_permission
    ADD CONSTRAINT platform_role_permission_pkey PRIMARY KEY (id);


--
-- Name: platform_role platform_role_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role
    ADD CONSTRAINT platform_role_pkey PRIMARY KEY (id);


--
-- Name: platform_schema_meta platform_schema_meta_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_schema_meta
    ADD CONSTRAINT platform_schema_meta_pkey PRIMARY KEY (id);


--
-- Name: platform_session platform_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_session
    ADD CONSTRAINT platform_session_pkey PRIMARY KEY (id);


--
-- Name: platform_stored_object platform_stored_object_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_stored_object
    ADD CONSTRAINT platform_stored_object_pkey PRIMARY KEY (storage_key);


--
-- Name: platform_upload_type platform_upload_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_upload_type
    ADD CONSTRAINT platform_upload_type_pkey PRIMARY KEY (extension);


--
-- Name: platform_user platform_user_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_user
    ADD CONSTRAINT platform_user_pkey PRIMARY KEY (id);


--
-- Name: platform_work_task platform_work_task_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_work_task
    ADD CONSTRAINT platform_work_task_pkey PRIMARY KEY (id);


--
-- Name: platform_workflow_definition platform_workflow_definition_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_workflow_definition
    ADD CONSTRAINT platform_workflow_definition_pkey PRIMARY KEY (id);


--
-- Name: platform_workflow_instance platform_workflow_instance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_workflow_instance
    ADD CONSTRAINT platform_workflow_instance_pkey PRIMARY KEY (id);


--
-- Name: platform_workflow_step_event platform_workflow_step_event_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_workflow_step_event
    ADD CONSTRAINT platform_workflow_step_event_pkey PRIMARY KEY (id);


--
-- Name: platform_audit_event uq_audit_event_chain_seq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_audit_event
    ADD CONSTRAINT uq_audit_event_chain_seq UNIQUE (chain_seq);


--
-- Name: platform_compensation_record uq_compensation_record_consumer_event; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_compensation_record
    ADD CONSTRAINT uq_compensation_record_consumer_event UNIQUE (consumer, event_id);


--
-- Name: platform_conflict_item uq_conflict_item_conflict_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_conflict_item
    ADD CONSTRAINT uq_conflict_item_conflict_id UNIQUE (conflict_id);


--
-- Name: platform_document_revision uq_document_revision__storage_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT uq_document_revision__storage_key UNIQUE (storage_key);


--
-- Name: CONSTRAINT uq_document_revision__storage_key ON platform_document_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT uq_document_revision__storage_key ON public.platform_document_revision IS 'django-name:platform_document_revision_storage_key_key';


--
-- Name: platform_document_revision uq_document_revision_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT uq_document_revision_no UNIQUE (document_id, revision_no);


--
-- Name: platform_dynamic_field_definition uq_dynamic_field_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_dynamic_field_definition
    ADD CONSTRAINT uq_dynamic_field_key UNIQUE (field_key);


--
-- Name: platform_idempotency_record uq_idempotency_record_actor_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_idempotency_record
    ADD CONSTRAINT uq_idempotency_record_actor_key UNIQUE (actor_id, key);


--
-- Name: platform_import_batch uq_import_batch_source_sha256; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_import_batch
    ADD CONSTRAINT uq_import_batch_source_sha256 UNIQUE (source_id, file_sha256);


--
-- Name: platform_inbox_event uq_inbox_event_consumer_event; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_inbox_event
    ADD CONSTRAINT uq_inbox_event_consumer_event UNIQUE (consumer, event_id);


--
-- Name: platform_integration_source uq_integration_source_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_integration_source
    ADD CONSTRAINT uq_integration_source_code UNIQUE (code);


--
-- Name: platform_job_run uq_job_run_task_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_job_run
    ADD CONSTRAINT uq_job_run_task_key UNIQUE (task_key);


--
-- Name: platform_org_unit uq_org_unit_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit
    ADD CONSTRAINT uq_org_unit_code UNIQUE (code);


--
-- Name: platform_org_unit_history uq_org_unit_history_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit_history
    ADD CONSTRAINT uq_org_unit_history_version UNIQUE (unit_id, unit_row_version);


--
-- Name: platform_outbox_event uq_outbox_event_event_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_outbox_event
    ADD CONSTRAINT uq_outbox_event_event_id UNIQUE (event_id);


--
-- Name: platform_position uq_position_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position
    ADD CONSTRAINT uq_position_code UNIQUE (code);


--
-- Name: platform_position_history uq_position_history_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_history
    ADD CONSTRAINT uq_position_history_version UNIQUE (position_id, position_row_version);


--
-- Name: platform_recovery_code uq_recovery_code_user_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_recovery_code
    ADD CONSTRAINT uq_recovery_code_user_hash UNIQUE (user_id, code_hash);


--
-- Name: platform_role uq_role_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role
    ADD CONSTRAINT uq_role_code UNIQUE (code);


--
-- Name: platform_role_permission uq_role_permission_pair; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_permission
    ADD CONSTRAINT uq_role_permission_pair UNIQUE (role_id, permission_action);


--
-- Name: platform_session uq_session_key_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_session
    ADD CONSTRAINT uq_session_key_hash UNIQUE (session_key_hash);


--
-- Name: platform_import_staging_row uq_staging_row_position; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_import_staging_row
    ADD CONSTRAINT uq_staging_row_position UNIQUE (batch_id, sheet_name, row_number);


--
-- Name: platform_user uq_user_username; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_user
    ADD CONSTRAINT uq_user_username UNIQUE (username);


--
-- Name: platform_workflow_definition uq_workflow_definition_key_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_workflow_definition
    ADD CONSTRAINT uq_workflow_definition_key_version UNIQUE (key, version);


--
-- Name: platform_workflow_step_event uq_workflow_step_event_seq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_workflow_step_event
    ADD CONSTRAINT uq_workflow_step_event_seq UNIQUE (instance_id, seq);


--
-- Name: ix_approval_request_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_request_action ON public.platform_approval_request USING btree (action);


--
-- Name: ix_approval_request_decider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_request_decider ON public.platform_approval_request USING btree (decided_by_id);


--
-- Name: ix_approval_request_expiry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_request_expiry ON public.platform_approval_request USING btree (expires_at) WHERE ((status)::text = 'PENDING'::text);


--
-- Name: ix_approval_request_instance; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_request_instance ON public.platform_approval_request USING btree (workflow_instance_id);


--
-- Name: ix_approval_request_requester; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_request_requester ON public.platform_approval_request USING btree (requested_by_id, status);


--
-- Name: ix_approval_request_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_request_resource ON public.platform_approval_request USING btree (resource_type, resource_id);


--
-- Name: ix_approval_request_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_approval_request_scope ON public.platform_approval_request USING btree (route_scope_unit_id, status);


--
-- Name: ix_audit_event_actor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_event_actor ON public.platform_audit_event USING btree (actor_id, occurred_at);


--
-- Name: ix_audit_event_occurred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_event_occurred ON public.platform_audit_event USING btree (occurred_at);


--
-- Name: ix_audit_event_request; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_event_request ON public.platform_audit_event USING btree (request_id);


--
-- Name: ix_audit_event_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_event_resource ON public.platform_audit_event USING btree (resource_type, resource_id, occurred_at);


--
-- Name: ix_audit_event_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_event_session ON public.platform_audit_event USING btree (session_id);


--
-- Name: ix_audit_integrity_finished; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_integrity_finished ON public.platform_audit_integrity_run USING btree (finished_at);


--
-- Name: ix_audit_integrity_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_integrity_job ON public.platform_audit_integrity_run USING btree (job_run_id);


--
-- Name: ix_break_glass_usage_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_break_glass_usage_session ON public.platform_break_glass_usage USING btree (session_id);


--
-- Name: ix_break_glass_usage_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_break_glass_usage_user ON public.platform_break_glass_usage USING btree (user_id, started_at);


--
-- Name: ix_compensation_record_event; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_compensation_record_event ON public.platform_compensation_record USING btree (event_id);


--
-- Name: ix_compensation_record_outcome; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_compensation_record_outcome ON public.platform_compensation_record USING btree (outcome, recorded_at);


--
-- Name: ix_conflict_item_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conflict_item_batch ON public.platform_conflict_item USING btree (batch_id);


--
-- Name: ix_conflict_item_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_conflict_item_status ON public.platform_conflict_item USING btree (status, id);


--
-- Name: ix_credential_set_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credential_set_by ON public.platform_credential USING btree (set_by_id);


--
-- Name: ix_document_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_created_by ON public.platform_document USING btree (created_by_id);


--
-- Name: ix_document_current_rev; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_current_rev ON public.platform_document USING btree (current_approved_revision_id);


--
-- Name: ix_document_owner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_owner ON public.platform_document USING btree (owner_entity_type, owner_entity_id);


--
-- Name: ix_document_revision__storage_key_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_revision__storage_key_like ON public.platform_document_revision USING btree (storage_key varchar_pattern_ops);


--
-- Name: INDEX ix_document_revision__storage_key_like; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX public.ix_document_revision__storage_key_like IS 'django-name:platform_document_revision_storage_key_edb23f63_like';


--
-- Name: ix_document_revision_approval; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_revision_approval ON public.platform_document_revision USING btree (approval_request_id);


--
-- Name: ix_document_revision_decider; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_revision_decider ON public.platform_document_revision USING btree (decided_by_id);


--
-- Name: ix_document_revision_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_revision_doc ON public.platform_document_revision USING btree (document_id, status);


--
-- Name: ix_document_revision_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_revision_parent ON public.platform_document_revision USING btree (parent_revision_id);


--
-- Name: ix_document_revision_scan; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_revision_scan ON public.platform_document_revision USING btree (scan_status);


--
-- Name: ix_document_revision_submitter; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_revision_submitter ON public.platform_document_revision USING btree (submitted_by_id);


--
-- Name: ix_document_revision_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_revision_type ON public.platform_document_revision USING btree (upload_extension);


--
-- Name: ix_document_revision_uploader; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_revision_uploader ON public.platform_document_revision USING btree (uploaded_by_id);


--
-- Name: ix_document_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_type ON public.platform_document USING btree (document_type);


--
-- Name: ix_document_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_updated_by ON public.platform_document USING btree (updated_by_id);


--
-- Name: ix_dynamic_field_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dynamic_field_created_by ON public.platform_dynamic_field_definition USING btree (created_by_id);


--
-- Name: ix_dynamic_field_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dynamic_field_scope ON public.platform_dynamic_field_definition USING btree (entity_scope);


--
-- Name: ix_dynamic_field_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dynamic_field_updated_by ON public.platform_dynamic_field_definition USING btree (updated_by_id);


--
-- Name: ix_idempotency_record_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_idempotency_record_expires ON public.platform_idempotency_record USING btree (expires_at);


--
-- Name: ix_import_batch_source_recv; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_import_batch_source_recv ON public.platform_import_batch USING btree (source_id, received_at);


--
-- Name: ix_import_batch_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_import_batch_status ON public.platform_import_batch USING btree (status, received_at);


--
-- Name: ix_inbox_event_event; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_inbox_event_event ON public.platform_inbox_event USING btree (event_id);


--
-- Name: ix_job_definition__job_type_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_definition__job_type_like ON public.platform_job_definition USING btree (job_type varchar_pattern_ops);


--
-- Name: INDEX ix_job_definition__job_type_like; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX public.ix_job_definition__job_type_like IS 'django-name:platform_job_definition_job_type_c6300ab5_like';


--
-- Name: ix_job_run_cancel_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_run_cancel_by ON public.platform_job_run USING btree (cancel_requested_by_id);


--
-- Name: ix_job_run_requested_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_run_requested_by ON public.platform_job_run USING btree (requested_by_id);


--
-- Name: ix_job_run_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_run_state ON public.platform_job_run USING btree (state, queued_at);


--
-- Name: ix_job_run_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_job_run_type ON public.platform_job_run USING btree (job_type, queued_at);


--
-- Name: ix_login_attempt_ip; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_login_attempt_ip ON public.platform_login_attempt USING btree (client_ip, occurred_at);


--
-- Name: ix_login_attempt_occurred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_login_attempt_occurred ON public.platform_login_attempt USING btree (occurred_at);


--
-- Name: ix_login_attempt_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_login_attempt_session ON public.platform_login_attempt USING btree (session_id);


--
-- Name: ix_login_attempt_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_login_attempt_user ON public.platform_login_attempt USING btree (user_id, occurred_at);


--
-- Name: ix_login_attempt_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_login_attempt_username ON public.platform_login_attempt USING btree (username_attempted, occurred_at);


--
-- Name: ix_mfa_factor_revoked_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mfa_factor_revoked_by ON public.platform_mfa_factor USING btree (revoked_by_id);


--
-- Name: ix_mfa_factor_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mfa_factor_user ON public.platform_mfa_factor USING btree (user_id, status);


--
-- Name: ix_org_unit_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_org_unit_created_by ON public.platform_org_unit USING btree (created_by_id);


--
-- Name: ix_org_unit_history_changed_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_org_unit_history_changed_by ON public.platform_org_unit_history USING btree (changed_by_id);


--
-- Name: ix_org_unit_history_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_org_unit_history_parent ON public.platform_org_unit_history USING btree (parent_id);


--
-- Name: ix_org_unit_history_unit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_org_unit_history_unit ON public.platform_org_unit_history USING btree (unit_id, valid_from);


--
-- Name: ix_org_unit_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_org_unit_parent ON public.platform_org_unit USING btree (parent_id);


--
-- Name: ix_org_unit_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_org_unit_type ON public.platform_org_unit USING btree (unit_type_code);


--
-- Name: ix_org_unit_type__code_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_org_unit_type__code_like ON public.platform_org_unit_type USING btree (code varchar_pattern_ops);


--
-- Name: INDEX ix_org_unit_type__code_like; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX public.ix_org_unit_type__code_like IS 'django-name:platform_org_unit_type_code_5b0b3989_like';


--
-- Name: ix_org_unit_type_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_org_unit_type_created_by ON public.platform_org_unit_type USING btree (created_by_id);


--
-- Name: ix_org_unit_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_org_unit_updated_by ON public.platform_org_unit USING btree (updated_by_id);


--
-- Name: ix_outbox_event_aggregate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbox_event_aggregate ON public.platform_outbox_event USING btree (aggregate_type, aggregate_id, aggregate_version);


--
-- Name: ix_outbox_event_correlation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbox_event_correlation ON public.platform_outbox_event USING btree (correlation_id);


--
-- Name: ix_outbox_event_dead_letter; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbox_event_dead_letter ON public.platform_outbox_event USING btree (occurred_at) WHERE ((delivery_status)::text = 'DEAD_LETTER'::text);


--
-- Name: ix_outbox_event_dispatch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbox_event_dispatch ON public.platform_outbox_event USING btree (next_attempt_at, id) WHERE ((delivery_status)::text = ANY ((ARRAY['PENDING'::character varying, 'FAILED'::character varying])::text[]));


--
-- Name: ix_parameter_definition__key_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_parameter_definition__key_like ON public.platform_parameter_definition USING btree (key varchar_pattern_ops);


--
-- Name: INDEX ix_parameter_definition__key_like; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX public.ix_parameter_definition__key_like IS 'django-name:platform_parameter_definition_key_f4dad133_like';


--
-- Name: ix_parameter_definition_cby; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_parameter_definition_cby ON public.platform_parameter_definition USING btree (created_by_id);


--
-- Name: ix_parameter_value_approval; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_parameter_value_approval ON public.platform_parameter_value USING btree (approval_request_id);


--
-- Name: ix_parameter_value_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_parameter_value_lookup ON public.platform_parameter_value USING btree (parameter_key, status, effective_from);


--
-- Name: ix_parameter_value_proposer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_parameter_value_proposer ON public.platform_parameter_value USING btree (proposed_by_id);


--
-- Name: ix_parameter_value_publisher; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_parameter_value_publisher ON public.platform_parameter_value USING btree (published_by_id);


--
-- Name: ix_password_history_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_password_history_user ON public.platform_password_history USING btree (user_id, set_at);


--
-- Name: ix_permission__action_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_permission__action_like ON public.platform_permission USING btree (action varchar_pattern_ops);


--
-- Name: INDEX ix_permission__action_like; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX public.ix_permission__action_like IS 'django-name:platform_permission_action_5656cdcf_like';


--
-- Name: ix_position_assignment_cby; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_assignment_cby ON public.platform_position_assignment USING btree (created_by_id);


--
-- Name: ix_position_assignment_pos; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_assignment_pos ON public.platform_position_assignment USING btree (position_id, valid_from);


--
-- Name: ix_position_assignment_uby; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_assignment_uby ON public.platform_position_assignment USING btree (updated_by_id);


--
-- Name: ix_position_assignment_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_assignment_user ON public.platform_position_assignment USING btree (user_id, valid_from);


--
-- Name: ix_position_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_created_by ON public.platform_position USING btree (created_by_id);


--
-- Name: ix_position_history_changed_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_history_changed_by ON public.platform_position_history USING btree (changed_by_id);


--
-- Name: ix_position_history_position; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_history_position ON public.platform_position_history USING btree (position_id, valid_from);


--
-- Name: ix_position_history_reports_to; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_history_reports_to ON public.platform_position_history USING btree (reports_to_id);


--
-- Name: ix_position_history_unit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_history_unit ON public.platform_position_history USING btree (unit_id);


--
-- Name: ix_position_reports_to; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_reports_to ON public.platform_position USING btree (reports_to_id);


--
-- Name: ix_position_unit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_unit ON public.platform_position USING btree (unit_id, status);


--
-- Name: ix_position_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_position_updated_by ON public.platform_position USING btree (updated_by_id);


--
-- Name: ix_recovery_code_user_gen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recovery_code_user_gen ON public.platform_recovery_code USING btree (user_id, generation);


--
-- Name: ix_role_assignment_approval; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_assignment_approval ON public.platform_role_assignment USING btree (approval_request_id);


--
-- Name: ix_role_assignment_granted_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_assignment_granted_by ON public.platform_role_assignment USING btree (granted_by_id);


--
-- Name: ix_role_assignment_revoked_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_assignment_revoked_by ON public.platform_role_assignment USING btree (revoked_by_id);


--
-- Name: ix_role_assignment_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_assignment_role ON public.platform_role_assignment USING btree (role_id, status);


--
-- Name: ix_role_assignment_scope_unit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_assignment_scope_unit ON public.platform_role_assignment USING btree (scope_unit_id);


--
-- Name: ix_role_assignment_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_assignment_updated_by ON public.platform_role_assignment USING btree (updated_by_id);


--
-- Name: ix_role_assignment_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_assignment_user ON public.platform_role_assignment USING btree (user_id, status);


--
-- Name: ix_role_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_created_by ON public.platform_role USING btree (created_by_id);


--
-- Name: ix_role_permission_permission; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_permission_permission ON public.platform_role_permission USING btree (permission_action);


--
-- Name: ix_role_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_updated_by ON public.platform_role USING btree (updated_by_id);


--
-- Name: ix_session_expiry; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_session_expiry ON public.platform_session USING btree (absolute_expires_at) WHERE ((state)::text = ANY ((ARRAY['MFA_PENDING'::character varying, 'ACTIVE'::character varying])::text[]));


--
-- Name: ix_session_revoked_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_session_revoked_by ON public.platform_session USING btree (revoked_by_id);


--
-- Name: ix_session_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_session_user ON public.platform_session USING btree (user_id, created_at);


--
-- Name: ix_session_user_live; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_session_user_live ON public.platform_session USING btree (user_id, created_at) WHERE ((state)::text = ANY ((ARRAY['MFA_PENDING'::character varying, 'ACTIVE'::character varying])::text[]));


--
-- Name: ix_staging_row_batch_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_staging_row_batch_status ON public.platform_import_staging_row USING btree (batch_id, validation_status);


--
-- Name: ix_stored_object__storage_key_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stored_object__storage_key_like ON public.platform_stored_object USING btree (storage_key varchar_pattern_ops);


--
-- Name: INDEX ix_stored_object__storage_key_like; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX public.ix_stored_object__storage_key_like IS 'django-name:platform_stored_object_storage_key_7ba048b7_like';


--
-- Name: ix_stored_object_purge_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stored_object_purge_due ON public.platform_stored_object USING btree (purge_after) WHERE ((bytes_purged_at IS NULL) AND (purge_after IS NOT NULL));


--
-- Name: ix_stored_object_sha256; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stored_object_sha256 ON public.platform_stored_object USING btree (sha256);


--
-- Name: ix_upload_type__extension_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_upload_type__extension_like ON public.platform_upload_type USING btree (extension varchar_pattern_ops);


--
-- Name: INDEX ix_upload_type__extension_like; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX public.ix_upload_type__extension_like IS 'django-name:platform_upload_type_extension_075912c7_like';


--
-- Name: ix_user_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_created_by ON public.platform_user USING btree (created_by_id);


--
-- Name: ix_user_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_status ON public.platform_user USING btree (status);


--
-- Name: ix_user_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_updated_by ON public.platform_user USING btree (updated_by_id);


--
-- Name: ix_work_task_assignee_pos; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_task_assignee_pos ON public.platform_work_task USING btree (assignee_position_id, status);


--
-- Name: ix_work_task_assignee_unit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_task_assignee_unit ON public.platform_work_task USING btree (assignee_unit_id, status);


--
-- Name: ix_work_task_assignee_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_task_assignee_user ON public.platform_work_task USING btree (assignee_user_id, status);


--
-- Name: ix_work_task_cancelled_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_task_cancelled_by ON public.platform_work_task USING btree (cancelled_by_id);


--
-- Name: ix_work_task_closed_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_task_closed_by ON public.platform_work_task USING btree (closed_by_id);


--
-- Name: ix_work_task_completed_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_task_completed_by ON public.platform_work_task USING btree (completed_by_id);


--
-- Name: ix_work_task_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_task_created_by ON public.platform_work_task USING btree (created_by_id);


--
-- Name: ix_work_task_instance; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_task_instance ON public.platform_work_task USING btree (workflow_instance_id);


--
-- Name: ix_work_task_related; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_task_related ON public.platform_work_task USING btree (related_type, related_id);


--
-- Name: ix_work_task_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_task_updated_by ON public.platform_work_task USING btree (updated_by_id);


--
-- Name: ix_workflow_instance_cancel_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_instance_cancel_by ON public.platform_workflow_instance USING btree (cancel_requested_by_id);


--
-- Name: ix_workflow_instance_def; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_instance_def ON public.platform_workflow_instance USING btree (definition_id);


--
-- Name: ix_workflow_instance_starter; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_instance_starter ON public.platform_workflow_instance USING btree (started_by_id);


--
-- Name: ix_workflow_instance_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_instance_status ON public.platform_workflow_instance USING btree (status, started_at);


--
-- Name: ix_workflow_instance_subject; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_instance_subject ON public.platform_workflow_instance USING btree (subject_type, subject_id);


--
-- Name: ix_workflow_step_event_actor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_workflow_step_event_actor ON public.platform_workflow_step_event USING btree (actor_id);


--
-- Name: platform_conflict_item_batch_id_c92fb881; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX platform_conflict_item_batch_id_c92fb881 ON public.platform_conflict_item USING btree (batch_id);


--
-- Name: platform_conflict_item_source_id_8a45872b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX platform_conflict_item_source_id_8a45872b ON public.platform_conflict_item USING btree (source_id);


--
-- Name: platform_import_batch_source_id_2e0caa3b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX platform_import_batch_source_id_2e0caa3b ON public.platform_import_batch USING btree (source_id);


--
-- Name: platform_import_staging_row_batch_id_ffe87cfc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX platform_import_staging_row_batch_id_ffe87cfc ON public.platform_import_staging_row USING btree (batch_id);


--
-- Name: platform_integration_source_last_success_batch_id_d00d7522; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX platform_integration_source_last_success_batch_id_d00d7522 ON public.platform_integration_source USING btree (last_success_batch_id);


--
-- Name: uq_approval_request_one_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_approval_request_one_pending ON public.platform_approval_request USING btree (resource_type, resource_id, resource_revision, action) WHERE ((status)::text = 'PENDING'::text);


--
-- Name: uq_conflict_item_open_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_conflict_item_open_key ON public.platform_conflict_item USING btree (source_id, kind, conflict_key) WHERE ((status)::text = 'OPEN'::text);


--
-- Name: uq_document_revision_one_approved; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_document_revision_one_approved ON public.platform_document_revision USING btree (document_id) WHERE ((status)::text = 'APPROVED'::text);


--
-- Name: uq_job_run_worker_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_job_run_worker_task_id ON public.platform_job_run USING btree (worker_task_id) WHERE (NOT ((worker_task_id)::text = ''::text));


--
-- Name: uq_mfa_factor_one_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_mfa_factor_one_active ON public.platform_mfa_factor USING btree (user_id, method) WHERE ((status)::text = 'ACTIVE'::text);


--
-- Name: uq_mfa_factor_one_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_mfa_factor_one_pending ON public.platform_mfa_factor USING btree (user_id) WHERE ((status)::text = 'PENDING'::text);


--
-- Name: uq_parameter_value_effective; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_parameter_value_effective ON public.platform_parameter_value USING btree (parameter_key, effective_from) WHERE ((status)::text = ANY ((ARRAY['PUBLISHED'::character varying, 'SUPERSEDED'::character varying])::text[]));


--
-- Name: uq_position_one_active_head; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_position_one_active_head ON public.platform_position USING btree (unit_id) WHERE (is_unit_head AND ((status)::text = 'ACTIVE'::text));


--
-- Name: uq_user_single_break_glass; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_user_single_break_glass ON public.platform_user USING btree (is_break_glass) WHERE is_break_glass;


--
-- Name: uq_workflow_definition_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_workflow_definition_active ON public.platform_workflow_definition USING btree (key) WHERE ((status)::text = 'ACTIVE'::text);


--
-- Name: platform_approval_request trg_approval_request_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_approval_request_a_terminal BEFORE UPDATE ON public.platform_approval_request FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'APPROVED', 'REJECTED', 'WITHDRAWN', 'SUPERSEDED', 'EXPIRED');


--
-- Name: platform_approval_request trg_approval_request_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_approval_request_immutable BEFORE UPDATE ON public.platform_approval_request FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'action', 'resource_type', 'resource_id', 'resource_revision', 'requested_by_id', 'requested_at', 'expires_at', 'route_kind', 'route_scope_unit_id', 'workflow_instance_id');


--
-- Name: platform_approval_request trg_approval_request_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_approval_request_touch BEFORE UPDATE ON public.platform_approval_request FOR EACH ROW EXECUTE FUNCTION public.platform_bump_row();


--
-- Name: platform_audit_event trg_audit_event_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_audit_event_append_only BEFORE DELETE OR UPDATE ON public.platform_audit_event FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: platform_audit_event trg_audit_event_no_truncate; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_audit_event_no_truncate BEFORE TRUNCATE ON public.platform_audit_event FOR EACH STATEMENT EXECUTE FUNCTION public.platform_reject_truncate_nonempty();


--
-- Name: platform_audit_integrity_run trg_audit_integrity_run_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_audit_integrity_run_append_only BEFORE DELETE OR UPDATE ON public.platform_audit_integrity_run FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: platform_break_glass_usage trg_break_glass_usage_account; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_break_glass_usage_account BEFORE INSERT ON public.platform_break_glass_usage FOR EACH ROW EXECUTE FUNCTION public.platform_break_glass_usage_guard();


--
-- Name: platform_break_glass_usage trg_break_glass_usage_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_break_glass_usage_append_only BEFORE DELETE OR UPDATE ON public.platform_break_glass_usage FOR EACH ROW EXECUTE FUNCTION public.platform_close_once_only('alerted_at', 'ended_at', 'password_rotated_at');


--
-- Name: platform_compensation_record trg_compensation_record_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_compensation_record_append_only BEFORE DELETE OR UPDATE ON public.platform_compensation_record FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: platform_conflict_item trg_conflict_item_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_conflict_item_touch BEFORE UPDATE ON public.platform_conflict_item FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_credential trg_credential_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_credential_immutable BEFORE UPDATE ON public.platform_credential FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('user_id', 'created_at');


--
-- Name: platform_credential trg_credential_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_credential_touch BEFORE UPDATE ON public.platform_credential FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_document trg_document_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_document_guard BEFORE INSERT OR UPDATE ON public.platform_document FOR EACH ROW EXECUTE FUNCTION public.platform_document_guard();


--
-- Name: platform_document_revision trg_document_revision_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_document_revision_a_terminal BEFORE UPDATE ON public.platform_document_revision FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'REJECTED', 'SUPERSEDED');


--
-- Name: platform_document_revision trg_document_revision_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_document_revision_guard BEFORE INSERT OR UPDATE ON public.platform_document_revision FOR EACH ROW EXECUTE FUNCTION public.platform_document_revision_guard();


--
-- Name: platform_document_revision trg_document_revision_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_document_revision_touch BEFORE UPDATE ON public.platform_document_revision FOR EACH ROW EXECUTE FUNCTION public.platform_bump_row();


--
-- Name: platform_document trg_document_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_document_touch BEFORE UPDATE ON public.platform_document FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_dynamic_field_definition trg_dynamic_field_definition_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_dynamic_field_definition_immutable BEFORE UPDATE ON public.platform_dynamic_field_definition FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'field_key', 'entity_scope', 'created_at', 'created_by_id');


--
-- Name: platform_dynamic_field_definition trg_dynamic_field_definition_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_dynamic_field_definition_touch BEFORE UPDATE ON public.platform_dynamic_field_definition FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_idempotency_record trg_idempotency_record_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_idempotency_record_touch BEFORE UPDATE ON public.platform_idempotency_record FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_import_batch trg_import_batch_provenance; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_import_batch_provenance BEFORE UPDATE ON public.platform_import_batch FOR EACH ROW EXECUTE FUNCTION public.platform_import_batch_provenance_guard();


--
-- Name: platform_import_batch trg_import_batch_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_import_batch_touch BEFORE UPDATE ON public.platform_import_batch FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_inbox_event trg_inbox_event_no_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_inbox_event_no_update BEFORE UPDATE ON public.platform_inbox_event FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: platform_integration_source trg_integration_source_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_integration_source_touch BEFORE UPDATE ON public.platform_integration_source FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_job_definition trg_job_definition_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_job_definition_immutable BEFORE UPDATE ON public.platform_job_definition FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('job_type', 'protected', 'provenance', 'created_at');


--
-- Name: platform_job_definition trg_job_definition_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_job_definition_touch BEFORE UPDATE ON public.platform_job_definition FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_job_run trg_job_run_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_job_run_a_terminal BEFORE UPDATE ON public.platform_job_run FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('state', 'CANCELLED', 'SUCCEEDED', 'FAILED');


--
-- Name: platform_job_run trg_job_run_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_job_run_guard BEFORE INSERT OR UPDATE ON public.platform_job_run FOR EACH ROW EXECUTE FUNCTION public.platform_job_run_guard();


--
-- Name: platform_job_run trg_job_run_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_job_run_touch BEFORE UPDATE ON public.platform_job_run FOR EACH ROW EXECUTE FUNCTION public.platform_bump_row();


--
-- Name: platform_login_attempt trg_login_attempt_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_login_attempt_guard BEFORE DELETE OR UPDATE ON public.platform_login_attempt FOR EACH ROW EXECUTE FUNCTION public.platform_login_attempt_guard();


--
-- Name: platform_mfa_factor trg_mfa_factor_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_mfa_factor_a_terminal BEFORE UPDATE ON public.platform_mfa_factor FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'REVOKED');


--
-- Name: platform_mfa_factor trg_mfa_factor_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_mfa_factor_guard BEFORE UPDATE ON public.platform_mfa_factor FOR EACH ROW EXECUTE FUNCTION public.platform_mfa_factor_guard();


--
-- Name: platform_mfa_factor trg_mfa_factor_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_mfa_factor_touch BEFORE UPDATE ON public.platform_mfa_factor FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_org_unit trg_org_unit_effective; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_org_unit_effective BEFORE INSERT OR UPDATE ON public.platform_org_unit FOR EACH ROW EXECUTE FUNCTION public.platform_effective_from_guard();


--
-- Name: platform_org_unit trg_org_unit_history; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_org_unit_history AFTER INSERT OR UPDATE ON public.platform_org_unit FOR EACH ROW EXECUTE FUNCTION public.platform_org_unit_history_writer();


--
-- Name: platform_org_unit_history trg_org_unit_history_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_org_unit_history_append_only BEFORE DELETE OR UPDATE ON public.platform_org_unit_history FOR EACH ROW EXECUTE FUNCTION public.platform_close_once_only('valid_to');


--
-- Name: platform_org_unit trg_org_unit_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_org_unit_touch BEFORE UPDATE ON public.platform_org_unit FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_org_unit trg_org_unit_tree_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_org_unit_tree_guard BEFORE INSERT OR UPDATE ON public.platform_org_unit FOR EACH ROW EXECUTE FUNCTION public.platform_org_unit_tree_guard();


--
-- Name: platform_org_unit_type trg_org_unit_type_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_org_unit_type_touch BEFORE UPDATE ON public.platform_org_unit_type FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_outbox_event trg_outbox_event_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_outbox_event_touch BEFORE UPDATE ON public.platform_outbox_event FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_parameter_definition trg_parameter_definition_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_parameter_definition_immutable BEFORE UPDATE ON public.platform_parameter_definition FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('key', 'datatype', 'unit', 'owner_module', 'classification', 'decision_id', 'min_value', 'max_value', 'allowed_values', 'provenance', 'created_at', 'created_by_id');


--
-- Name: platform_parameter_definition trg_parameter_definition_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_parameter_definition_touch BEFORE UPDATE ON public.platform_parameter_definition FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_parameter_value trg_parameter_value_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_parameter_value_a_terminal BEFORE UPDATE ON public.platform_parameter_value FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'SUPERSEDED', 'REJECTED');


--
-- Name: platform_parameter_value trg_parameter_value_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_parameter_value_guard BEFORE INSERT OR UPDATE ON public.platform_parameter_value FOR EACH ROW EXECUTE FUNCTION public.platform_parameter_value_guard();


--
-- Name: platform_parameter_value trg_parameter_value_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_parameter_value_touch BEFORE UPDATE ON public.platform_parameter_value FOR EACH ROW EXECUTE FUNCTION public.platform_bump_row();


--
-- Name: platform_password_history trg_password_history_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_password_history_append_only BEFORE DELETE OR UPDATE ON public.platform_password_history FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: platform_permission trg_permission_ba_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_permission_ba_guard BEFORE UPDATE ON public.platform_permission FOR EACH ROW EXECUTE FUNCTION public.platform_permission_ba_guard();


--
-- Name: platform_position_assignment trg_position_assignment_a_not_backdated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_position_assignment_a_not_backdated BEFORE INSERT OR UPDATE ON public.platform_position_assignment FOR EACH ROW EXECUTE FUNCTION public.platform_position_assignment_not_backdated();


--
-- Name: platform_position_assignment trg_position_assignment_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_position_assignment_guard BEFORE INSERT OR UPDATE ON public.platform_position_assignment FOR EACH ROW EXECUTE FUNCTION public.platform_position_assignment_guard();


--
-- Name: platform_position_assignment trg_position_assignment_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_position_assignment_touch BEFORE UPDATE ON public.platform_position_assignment FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_position trg_position_effective; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_position_effective BEFORE INSERT OR UPDATE ON public.platform_position FOR EACH ROW EXECUTE FUNCTION public.platform_effective_from_guard();


--
-- Name: platform_position trg_position_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_position_guard BEFORE INSERT OR UPDATE ON public.platform_position FOR EACH ROW EXECUTE FUNCTION public.platform_position_guard();


--
-- Name: platform_position trg_position_history; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_position_history AFTER INSERT OR UPDATE ON public.platform_position FOR EACH ROW EXECUTE FUNCTION public.platform_position_history_writer();


--
-- Name: platform_position_history trg_position_history_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_position_history_append_only BEFORE DELETE OR UPDATE ON public.platform_position_history FOR EACH ROW EXECUTE FUNCTION public.platform_close_once_only('valid_to');


--
-- Name: platform_position trg_position_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_position_touch BEFORE UPDATE ON public.platform_position FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_recovery_code trg_recovery_code_use_once; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_recovery_code_use_once BEFORE UPDATE ON public.platform_recovery_code FOR EACH ROW EXECUTE FUNCTION public.platform_close_once_only('used_at');


--
-- Name: platform_role trg_role_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_role_a_terminal BEFORE UPDATE ON public.platform_role FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'RETIRED');


--
-- Name: platform_role_assignment trg_role_assignment_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_role_assignment_a_terminal BEFORE UPDATE ON public.platform_role_assignment FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'EXPIRED', 'REVOKED');


--
-- Name: platform_role_assignment trg_role_assignment_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_role_assignment_guard BEFORE INSERT OR UPDATE ON public.platform_role_assignment FOR EACH ROW EXECUTE FUNCTION public.platform_role_assignment_guard();


--
-- Name: platform_role_assignment trg_role_assignment_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_role_assignment_touch BEFORE UPDATE ON public.platform_role_assignment FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_role trg_role_kind_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_role_kind_guard BEFORE UPDATE ON public.platform_role FOR EACH ROW EXECUTE FUNCTION public.platform_role_kind_guard();


--
-- Name: platform_role_permission trg_role_permission_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_role_permission_guard BEFORE INSERT OR DELETE OR UPDATE ON public.platform_role_permission FOR EACH ROW EXECUTE FUNCTION public.platform_role_permission_guard();


--
-- Name: platform_role trg_role_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_role_touch BEFORE UPDATE ON public.platform_role FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_session trg_session_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_session_a_terminal BEFORE UPDATE ON public.platform_session FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('state', 'EXPIRED', 'REVOKED', 'LOGGED_OUT');


--
-- Name: platform_session trg_session_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_session_immutable BEFORE UPDATE ON public.platform_session FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'user_id', 'created_at');


--
-- Name: platform_session trg_session_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_session_touch BEFORE UPDATE ON public.platform_session FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_import_staging_row trg_staging_row_payload; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_staging_row_payload BEFORE UPDATE ON public.platform_import_staging_row FOR EACH ROW EXECUTE FUNCTION public.platform_staging_row_payload_guard();


--
-- Name: platform_import_staging_row trg_staging_row_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_staging_row_touch BEFORE UPDATE ON public.platform_import_staging_row FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_stored_object trg_stored_object_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_stored_object_append_only BEFORE DELETE OR UPDATE ON public.platform_stored_object FOR EACH ROW EXECUTE FUNCTION public.platform_close_once_only('purge_after', 'bytes_purged_at');


--
-- Name: platform_user trg_user_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_user_immutable BEFORE UPDATE ON public.platform_user FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'is_break_glass', 'provenance', 'created_at', 'created_by_id');


--
-- Name: platform_user trg_user_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_user_touch BEFORE UPDATE ON public.platform_user FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_work_task trg_work_task_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_work_task_a_terminal BEFORE UPDATE ON public.platform_work_task FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'CLOSED', 'CANCELLED');


--
-- Name: platform_work_task trg_work_task_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_work_task_immutable BEFORE UPDATE ON public.platform_work_task FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'created_by_id', 'created_at', 'workflow_instance_id');


--
-- Name: platform_work_task trg_work_task_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_work_task_touch BEFORE UPDATE ON public.platform_work_task FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_workflow_definition trg_workflow_definition_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_workflow_definition_guard BEFORE UPDATE ON public.platform_workflow_definition FOR EACH ROW EXECUTE FUNCTION public.platform_workflow_definition_guard();


--
-- Name: platform_workflow_definition trg_workflow_definition_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_workflow_definition_touch BEFORE UPDATE ON public.platform_workflow_definition FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: platform_workflow_instance trg_workflow_instance_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_workflow_instance_a_terminal BEFORE UPDATE ON public.platform_workflow_instance FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'COMPLETED', 'CANCELLED', 'FAILED');


--
-- Name: platform_workflow_instance trg_workflow_instance_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_workflow_instance_guard BEFORE INSERT OR UPDATE ON public.platform_workflow_instance FOR EACH ROW EXECUTE FUNCTION public.platform_workflow_instance_guard();


--
-- Name: platform_workflow_instance trg_workflow_instance_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_workflow_instance_touch BEFORE UPDATE ON public.platform_workflow_instance FOR EACH ROW EXECUTE FUNCTION public.platform_bump_row();


--
-- Name: platform_workflow_step_event trg_workflow_step_event_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_workflow_step_event_append_only BEFORE DELETE OR UPDATE ON public.platform_workflow_step_event FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: platform_approval_request fk_approval_request__action; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_approval_request
    ADD CONSTRAINT fk_approval_request__action FOREIGN KEY (action) REFERENCES public.platform_permission(action) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_approval_request__action ON platform_approval_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_approval_request__action ON public.platform_approval_request IS 'django-name:platform_approval_re_action_254c7274_fk_platform_';


--
-- Name: platform_approval_request fk_approval_request__decided_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_approval_request
    ADD CONSTRAINT fk_approval_request__decided_by_id FOREIGN KEY (decided_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_approval_request__decided_by_id ON platform_approval_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_approval_request__decided_by_id ON public.platform_approval_request IS 'django-name:platform_approval_re_decided_by_id_8304a14d_fk_platform_';


--
-- Name: platform_approval_request fk_approval_request__requested_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_approval_request
    ADD CONSTRAINT fk_approval_request__requested_by_id FOREIGN KEY (requested_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_approval_request__requested_by_id ON platform_approval_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_approval_request__requested_by_id ON public.platform_approval_request IS 'django-name:platform_approval_re_requested_by_id_fb34d20e_fk_platform_';


--
-- Name: platform_approval_request fk_approval_request__route_scope_unit_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_approval_request
    ADD CONSTRAINT fk_approval_request__route_scope_unit_id FOREIGN KEY (route_scope_unit_id) REFERENCES public.platform_org_unit(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_approval_request__route_scope_unit_id ON platform_approval_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_approval_request__route_scope_unit_id ON public.platform_approval_request IS 'django-name:platform_approval_re_route_scope_unit_id_af757051_fk_platform_';


--
-- Name: platform_approval_request fk_approval_request__workflow_instance_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_approval_request
    ADD CONSTRAINT fk_approval_request__workflow_instance_id FOREIGN KEY (workflow_instance_id) REFERENCES public.platform_workflow_instance(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_approval_request__workflow_instance_id ON platform_approval_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_approval_request__workflow_instance_id ON public.platform_approval_request IS 'django-name:platform_approval_re_workflow_instance_id_deb1bcba_fk_platform_';


--
-- Name: platform_audit_integrity_run fk_audit_integrity_run__job_run_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_audit_integrity_run
    ADD CONSTRAINT fk_audit_integrity_run__job_run_id FOREIGN KEY (job_run_id) REFERENCES public.platform_job_run(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_audit_integrity_run__job_run_id ON platform_audit_integrity_run; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_audit_integrity_run__job_run_id ON public.platform_audit_integrity_run IS 'django-name:platform_audit_integ_job_run_id_9e8a8b6a_fk_platform_';


--
-- Name: platform_break_glass_usage fk_break_glass_usage__session_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_break_glass_usage
    ADD CONSTRAINT fk_break_glass_usage__session_id FOREIGN KEY (session_id) REFERENCES public.platform_session(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_break_glass_usage__session_id ON platform_break_glass_usage; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_break_glass_usage__session_id ON public.platform_break_glass_usage IS 'django-name:platform_break_glass_session_id_a622976b_fk_platform_';


--
-- Name: platform_break_glass_usage fk_break_glass_usage__user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_break_glass_usage
    ADD CONSTRAINT fk_break_glass_usage__user_id FOREIGN KEY (user_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_break_glass_usage__user_id ON platform_break_glass_usage; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_break_glass_usage__user_id ON public.platform_break_glass_usage IS 'django-name:platform_break_glass_usage_user_id_c5d6304b_fk_platform_user_id';


--
-- Name: platform_credential fk_credential__set_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_credential
    ADD CONSTRAINT fk_credential__set_by_id FOREIGN KEY (set_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_credential__set_by_id ON platform_credential; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_credential__set_by_id ON public.platform_credential IS 'django-name:platform_credential_set_by_id_f4f85b62_fk_platform_user_id';


--
-- Name: platform_credential fk_credential__user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_credential
    ADD CONSTRAINT fk_credential__user_id FOREIGN KEY (user_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_credential__user_id ON platform_credential; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_credential__user_id ON public.platform_credential IS 'django-name:platform_credential_user_id_c1cac35f_fk_platform_user_id';


--
-- Name: platform_document fk_document__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document
    ADD CONSTRAINT fk_document__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document__created_by_id ON platform_document; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document__created_by_id ON public.platform_document IS 'django-name:platform_document_created_by_id_3d8daecf_fk_platform_user_id';


--
-- Name: platform_document fk_document__current_approved_revision_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document
    ADD CONSTRAINT fk_document__current_approved_revision_id FOREIGN KEY (current_approved_revision_id) REFERENCES public.platform_document_revision(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document__current_approved_revision_id ON platform_document; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document__current_approved_revision_id ON public.platform_document IS 'django-name:platform_document_current_approved_rev_d54c244f_fk_platform_';


--
-- Name: platform_document fk_document__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document
    ADD CONSTRAINT fk_document__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document__updated_by_id ON platform_document; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document__updated_by_id ON public.platform_document IS 'django-name:platform_document_updated_by_id_9c91c917_fk_platform_user_id';


--
-- Name: platform_document_revision fk_document_revision__approval_request_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT fk_document_revision__approval_request_id FOREIGN KEY (approval_request_id) REFERENCES public.platform_approval_request(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document_revision__approval_request_id ON platform_document_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document_revision__approval_request_id ON public.platform_document_revision IS 'django-name:platform_document_re_approval_request_id_34372719_fk_platform_';


--
-- Name: platform_document_revision fk_document_revision__decided_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT fk_document_revision__decided_by_id FOREIGN KEY (decided_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document_revision__decided_by_id ON platform_document_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document_revision__decided_by_id ON public.platform_document_revision IS 'django-name:platform_document_re_decided_by_id_81fb971f_fk_platform_';


--
-- Name: platform_document_revision fk_document_revision__document_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT fk_document_revision__document_id FOREIGN KEY (document_id) REFERENCES public.platform_document(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document_revision__document_id ON platform_document_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document_revision__document_id ON public.platform_document_revision IS 'django-name:platform_document_re_document_id_433b4aea_fk_platform_';


--
-- Name: platform_document_revision fk_document_revision__parent_revision_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT fk_document_revision__parent_revision_id FOREIGN KEY (parent_revision_id) REFERENCES public.platform_document_revision(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document_revision__parent_revision_id ON platform_document_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document_revision__parent_revision_id ON public.platform_document_revision IS 'django-name:platform_document_re_parent_revision_id_fa4b3f4e_fk_platform_';


--
-- Name: platform_document_revision fk_document_revision__storage_key; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT fk_document_revision__storage_key FOREIGN KEY (storage_key) REFERENCES public.platform_stored_object(storage_key) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document_revision__storage_key ON platform_document_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document_revision__storage_key ON public.platform_document_revision IS 'django-name:platform_document_re_storage_key_edb23f63_fk_platform_';


--
-- Name: platform_document_revision fk_document_revision__submitted_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT fk_document_revision__submitted_by_id FOREIGN KEY (submitted_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document_revision__submitted_by_id ON platform_document_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document_revision__submitted_by_id ON public.platform_document_revision IS 'django-name:platform_document_re_submitted_by_id_4111e3e6_fk_platform_';


--
-- Name: platform_document_revision fk_document_revision__upload_extension; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT fk_document_revision__upload_extension FOREIGN KEY (upload_extension) REFERENCES public.platform_upload_type(extension) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document_revision__upload_extension ON platform_document_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document_revision__upload_extension ON public.platform_document_revision IS 'django-name:platform_document_re_upload_extension_080ba01b_fk_platform_';


--
-- Name: platform_document_revision fk_document_revision__uploaded_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_document_revision
    ADD CONSTRAINT fk_document_revision__uploaded_by_id FOREIGN KEY (uploaded_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_document_revision__uploaded_by_id ON platform_document_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_document_revision__uploaded_by_id ON public.platform_document_revision IS 'django-name:platform_document_re_uploaded_by_id_ee211f78_fk_platform_';


--
-- Name: platform_dynamic_field_definition fk_dynamic_field_definition__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_dynamic_field_definition
    ADD CONSTRAINT fk_dynamic_field_definition__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_dynamic_field_definition__created_by_id ON platform_dynamic_field_definition; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_dynamic_field_definition__created_by_id ON public.platform_dynamic_field_definition IS 'django-name:platform_dynamic_fie_created_by_id_d1711b4d_fk_platform_';


--
-- Name: platform_dynamic_field_definition fk_dynamic_field_definition__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_dynamic_field_definition
    ADD CONSTRAINT fk_dynamic_field_definition__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_dynamic_field_definition__updated_by_id ON platform_dynamic_field_definition; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_dynamic_field_definition__updated_by_id ON public.platform_dynamic_field_definition IS 'django-name:platform_dynamic_fie_updated_by_id_a7355061_fk_platform_';


--
-- Name: platform_job_run fk_job_run__cancel_requested_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_job_run
    ADD CONSTRAINT fk_job_run__cancel_requested_by_id FOREIGN KEY (cancel_requested_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_job_run__cancel_requested_by_id ON platform_job_run; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_job_run__cancel_requested_by_id ON public.platform_job_run IS 'django-name:platform_job_run_cancel_requested_by__2e776558_fk_platform_';


--
-- Name: platform_job_run fk_job_run__job_type; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_job_run
    ADD CONSTRAINT fk_job_run__job_type FOREIGN KEY (job_type) REFERENCES public.platform_job_definition(job_type) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_job_run__job_type ON platform_job_run; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_job_run__job_type ON public.platform_job_run IS 'django-name:platform_job_run_job_type_54cb0560_fk_platform_';


--
-- Name: platform_job_run fk_job_run__requested_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_job_run
    ADD CONSTRAINT fk_job_run__requested_by_id FOREIGN KEY (requested_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_job_run__requested_by_id ON platform_job_run; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_job_run__requested_by_id ON public.platform_job_run IS 'django-name:platform_job_run_requested_by_id_1db3aa03_fk_platform_user_id';


--
-- Name: platform_login_attempt fk_login_attempt__session_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_login_attempt
    ADD CONSTRAINT fk_login_attempt__session_id FOREIGN KEY (session_id) REFERENCES public.platform_session(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_login_attempt__session_id ON platform_login_attempt; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_login_attempt__session_id ON public.platform_login_attempt IS 'django-name:platform_login_attem_session_id_8b56e8be_fk_platform_';


--
-- Name: platform_login_attempt fk_login_attempt__user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_login_attempt
    ADD CONSTRAINT fk_login_attempt__user_id FOREIGN KEY (user_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_login_attempt__user_id ON platform_login_attempt; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_login_attempt__user_id ON public.platform_login_attempt IS 'django-name:platform_login_attempt_user_id_eca1d0e8_fk_platform_user_id';


--
-- Name: platform_mfa_factor fk_mfa_factor__revoked_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_mfa_factor
    ADD CONSTRAINT fk_mfa_factor__revoked_by_id FOREIGN KEY (revoked_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_mfa_factor__revoked_by_id ON platform_mfa_factor; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_mfa_factor__revoked_by_id ON public.platform_mfa_factor IS 'django-name:platform_mfa_factor_revoked_by_id_05214ae1_fk_platform_user_id';


--
-- Name: platform_mfa_factor fk_mfa_factor__user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_mfa_factor
    ADD CONSTRAINT fk_mfa_factor__user_id FOREIGN KEY (user_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_mfa_factor__user_id ON platform_mfa_factor; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_mfa_factor__user_id ON public.platform_mfa_factor IS 'django-name:platform_mfa_factor_user_id_7b19edeb_fk_platform_user_id';


--
-- Name: platform_org_unit fk_org_unit__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit
    ADD CONSTRAINT fk_org_unit__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_org_unit__created_by_id ON platform_org_unit; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_org_unit__created_by_id ON public.platform_org_unit IS 'django-name:platform_org_unit_created_by_id_3c0b60f0_fk_platform_user_id';


--
-- Name: platform_org_unit fk_org_unit__parent_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit
    ADD CONSTRAINT fk_org_unit__parent_id FOREIGN KEY (parent_id) REFERENCES public.platform_org_unit(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_org_unit__parent_id ON platform_org_unit; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_org_unit__parent_id ON public.platform_org_unit IS 'django-name:platform_org_unit_parent_id_8f679f64_fk_platform_org_unit_id';


--
-- Name: platform_org_unit fk_org_unit__unit_type_code; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit
    ADD CONSTRAINT fk_org_unit__unit_type_code FOREIGN KEY (unit_type_code) REFERENCES public.platform_org_unit_type(code) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_org_unit__unit_type_code ON platform_org_unit; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_org_unit__unit_type_code ON public.platform_org_unit IS 'django-name:platform_org_unit_unit_type_code_051e2d62_fk_platform_';


--
-- Name: platform_org_unit fk_org_unit__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit
    ADD CONSTRAINT fk_org_unit__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_org_unit__updated_by_id ON platform_org_unit; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_org_unit__updated_by_id ON public.platform_org_unit IS 'django-name:platform_org_unit_updated_by_id_fc0cab60_fk_platform_user_id';


--
-- Name: platform_org_unit_history fk_org_unit_history__changed_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit_history
    ADD CONSTRAINT fk_org_unit_history__changed_by_id FOREIGN KEY (changed_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_org_unit_history__changed_by_id ON platform_org_unit_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_org_unit_history__changed_by_id ON public.platform_org_unit_history IS 'django-name:platform_org_unit_hi_changed_by_id_f9a545e4_fk_platform_';


--
-- Name: platform_org_unit_history fk_org_unit_history__parent_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit_history
    ADD CONSTRAINT fk_org_unit_history__parent_id FOREIGN KEY (parent_id) REFERENCES public.platform_org_unit(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_org_unit_history__parent_id ON platform_org_unit_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_org_unit_history__parent_id ON public.platform_org_unit_history IS 'django-name:platform_org_unit_hi_parent_id_6314d164_fk_platform_';


--
-- Name: platform_org_unit_history fk_org_unit_history__unit_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit_history
    ADD CONSTRAINT fk_org_unit_history__unit_id FOREIGN KEY (unit_id) REFERENCES public.platform_org_unit(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_org_unit_history__unit_id ON platform_org_unit_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_org_unit_history__unit_id ON public.platform_org_unit_history IS 'django-name:platform_org_unit_hi_unit_id_f49ca853_fk_platform_';


--
-- Name: platform_org_unit_type fk_org_unit_type__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_org_unit_type
    ADD CONSTRAINT fk_org_unit_type__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_org_unit_type__created_by_id ON platform_org_unit_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_org_unit_type__created_by_id ON public.platform_org_unit_type IS 'django-name:platform_org_unit_ty_created_by_id_26e1eb3c_fk_platform_';


--
-- Name: platform_parameter_definition fk_parameter_definition__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_parameter_definition
    ADD CONSTRAINT fk_parameter_definition__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_parameter_definition__created_by_id ON platform_parameter_definition; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_parameter_definition__created_by_id ON public.platform_parameter_definition IS 'django-name:platform_parameter_d_created_by_id_cc9a4beb_fk_platform_';


--
-- Name: platform_parameter_value fk_parameter_value__approval_request_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_parameter_value
    ADD CONSTRAINT fk_parameter_value__approval_request_id FOREIGN KEY (approval_request_id) REFERENCES public.platform_approval_request(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_parameter_value__approval_request_id ON platform_parameter_value; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_parameter_value__approval_request_id ON public.platform_parameter_value IS 'django-name:platform_parameter_v_approval_request_id_b5c57e62_fk_platform_';


--
-- Name: platform_parameter_value fk_parameter_value__parameter_key; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_parameter_value
    ADD CONSTRAINT fk_parameter_value__parameter_key FOREIGN KEY (parameter_key) REFERENCES public.platform_parameter_definition(key) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_parameter_value__parameter_key ON platform_parameter_value; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_parameter_value__parameter_key ON public.platform_parameter_value IS 'django-name:platform_parameter_v_parameter_key_898fab42_fk_platform_';


--
-- Name: platform_parameter_value fk_parameter_value__proposed_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_parameter_value
    ADD CONSTRAINT fk_parameter_value__proposed_by_id FOREIGN KEY (proposed_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_parameter_value__proposed_by_id ON platform_parameter_value; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_parameter_value__proposed_by_id ON public.platform_parameter_value IS 'django-name:platform_parameter_v_proposed_by_id_dbe43bde_fk_platform_';


--
-- Name: platform_parameter_value fk_parameter_value__published_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_parameter_value
    ADD CONSTRAINT fk_parameter_value__published_by_id FOREIGN KEY (published_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_parameter_value__published_by_id ON platform_parameter_value; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_parameter_value__published_by_id ON public.platform_parameter_value IS 'django-name:platform_parameter_v_published_by_id_85bf30cf_fk_platform_';


--
-- Name: platform_password_history fk_password_history__user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_password_history
    ADD CONSTRAINT fk_password_history__user_id FOREIGN KEY (user_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_password_history__user_id ON platform_password_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_password_history__user_id ON public.platform_password_history IS 'django-name:platform_password_history_user_id_bcd1dca7_fk_platform_user_id';


--
-- Name: platform_position fk_position__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position
    ADD CONSTRAINT fk_position__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position__created_by_id ON platform_position; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position__created_by_id ON public.platform_position IS 'django-name:platform_position_created_by_id_b58de941_fk_platform_user_id';


--
-- Name: platform_position fk_position__reports_to_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position
    ADD CONSTRAINT fk_position__reports_to_id FOREIGN KEY (reports_to_id) REFERENCES public.platform_position(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position__reports_to_id ON platform_position; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position__reports_to_id ON public.platform_position IS 'django-name:platform_position_reports_to_id_19851a15_fk_platform_';


--
-- Name: platform_position fk_position__unit_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position
    ADD CONSTRAINT fk_position__unit_id FOREIGN KEY (unit_id) REFERENCES public.platform_org_unit(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position__unit_id ON platform_position; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position__unit_id ON public.platform_position IS 'django-name:platform_position_unit_id_a0d7c259_fk_platform_org_unit_id';


--
-- Name: platform_position fk_position__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position
    ADD CONSTRAINT fk_position__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position__updated_by_id ON platform_position; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position__updated_by_id ON public.platform_position IS 'django-name:platform_position_updated_by_id_b6ffe3ef_fk_platform_user_id';


--
-- Name: platform_position_assignment fk_position_assignment__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_assignment
    ADD CONSTRAINT fk_position_assignment__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position_assignment__created_by_id ON platform_position_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position_assignment__created_by_id ON public.platform_position_assignment IS 'django-name:platform_position_as_created_by_id_7405d00a_fk_platform_';


--
-- Name: platform_position_assignment fk_position_assignment__position_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_assignment
    ADD CONSTRAINT fk_position_assignment__position_id FOREIGN KEY (position_id) REFERENCES public.platform_position(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position_assignment__position_id ON platform_position_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position_assignment__position_id ON public.platform_position_assignment IS 'django-name:platform_position_as_position_id_673547be_fk_platform_';


--
-- Name: platform_position_assignment fk_position_assignment__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_assignment
    ADD CONSTRAINT fk_position_assignment__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position_assignment__updated_by_id ON platform_position_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position_assignment__updated_by_id ON public.platform_position_assignment IS 'django-name:platform_position_as_updated_by_id_07fe2ce0_fk_platform_';


--
-- Name: platform_position_assignment fk_position_assignment__user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_assignment
    ADD CONSTRAINT fk_position_assignment__user_id FOREIGN KEY (user_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position_assignment__user_id ON platform_position_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position_assignment__user_id ON public.platform_position_assignment IS 'django-name:platform_position_as_user_id_4cf841a1_fk_platform_';


--
-- Name: platform_position_history fk_position_history__changed_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_history
    ADD CONSTRAINT fk_position_history__changed_by_id FOREIGN KEY (changed_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position_history__changed_by_id ON platform_position_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position_history__changed_by_id ON public.platform_position_history IS 'django-name:platform_position_hi_changed_by_id_e069c5bd_fk_platform_';


--
-- Name: platform_position_history fk_position_history__position_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_history
    ADD CONSTRAINT fk_position_history__position_id FOREIGN KEY (position_id) REFERENCES public.platform_position(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position_history__position_id ON platform_position_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position_history__position_id ON public.platform_position_history IS 'django-name:platform_position_hi_position_id_034cb75c_fk_platform_';


--
-- Name: platform_position_history fk_position_history__reports_to_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_history
    ADD CONSTRAINT fk_position_history__reports_to_id FOREIGN KEY (reports_to_id) REFERENCES public.platform_position(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position_history__reports_to_id ON platform_position_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position_history__reports_to_id ON public.platform_position_history IS 'django-name:platform_position_hi_reports_to_id_b7ae6553_fk_platform_';


--
-- Name: platform_position_history fk_position_history__unit_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_position_history
    ADD CONSTRAINT fk_position_history__unit_id FOREIGN KEY (unit_id) REFERENCES public.platform_org_unit(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_position_history__unit_id ON platform_position_history; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_position_history__unit_id ON public.platform_position_history IS 'django-name:platform_position_hi_unit_id_97a76840_fk_platform_';


--
-- Name: platform_recovery_code fk_recovery_code__user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_recovery_code
    ADD CONSTRAINT fk_recovery_code__user_id FOREIGN KEY (user_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_recovery_code__user_id ON platform_recovery_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_recovery_code__user_id ON public.platform_recovery_code IS 'django-name:platform_recovery_code_user_id_825e6c8a_fk_platform_user_id';


--
-- Name: platform_role fk_role__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role
    ADD CONSTRAINT fk_role__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role__created_by_id ON platform_role; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role__created_by_id ON public.platform_role IS 'django-name:platform_role_created_by_id_669c0619_fk_platform_user_id';


--
-- Name: platform_role fk_role__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role
    ADD CONSTRAINT fk_role__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role__updated_by_id ON platform_role; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role__updated_by_id ON public.platform_role IS 'django-name:platform_role_updated_by_id_a9d63903_fk_platform_user_id';


--
-- Name: platform_role_assignment fk_role_assignment__approval_request_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_assignment
    ADD CONSTRAINT fk_role_assignment__approval_request_id FOREIGN KEY (approval_request_id) REFERENCES public.platform_approval_request(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role_assignment__approval_request_id ON platform_role_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role_assignment__approval_request_id ON public.platform_role_assignment IS 'django-name:platform_role_assign_approval_request_id_b4a5d415_fk_platform_';


--
-- Name: platform_role_assignment fk_role_assignment__granted_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_assignment
    ADD CONSTRAINT fk_role_assignment__granted_by_id FOREIGN KEY (granted_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role_assignment__granted_by_id ON platform_role_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role_assignment__granted_by_id ON public.platform_role_assignment IS 'django-name:platform_role_assign_granted_by_id_5aee1c47_fk_platform_';


--
-- Name: platform_role_assignment fk_role_assignment__revoked_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_assignment
    ADD CONSTRAINT fk_role_assignment__revoked_by_id FOREIGN KEY (revoked_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role_assignment__revoked_by_id ON platform_role_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role_assignment__revoked_by_id ON public.platform_role_assignment IS 'django-name:platform_role_assign_revoked_by_id_0339c17b_fk_platform_';


--
-- Name: platform_role_assignment fk_role_assignment__role_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_assignment
    ADD CONSTRAINT fk_role_assignment__role_id FOREIGN KEY (role_id) REFERENCES public.platform_role(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role_assignment__role_id ON platform_role_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role_assignment__role_id ON public.platform_role_assignment IS 'django-name:platform_role_assignment_role_id_59c8d410_fk_platform_role_id';


--
-- Name: platform_role_assignment fk_role_assignment__scope_unit_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_assignment
    ADD CONSTRAINT fk_role_assignment__scope_unit_id FOREIGN KEY (scope_unit_id) REFERENCES public.platform_org_unit(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role_assignment__scope_unit_id ON platform_role_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role_assignment__scope_unit_id ON public.platform_role_assignment IS 'django-name:platform_role_assign_scope_unit_id_d57451cc_fk_platform_';


--
-- Name: platform_role_assignment fk_role_assignment__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_assignment
    ADD CONSTRAINT fk_role_assignment__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role_assignment__updated_by_id ON platform_role_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role_assignment__updated_by_id ON public.platform_role_assignment IS 'django-name:platform_role_assign_updated_by_id_e2bc22c6_fk_platform_';


--
-- Name: platform_role_assignment fk_role_assignment__user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_assignment
    ADD CONSTRAINT fk_role_assignment__user_id FOREIGN KEY (user_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role_assignment__user_id ON platform_role_assignment; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role_assignment__user_id ON public.platform_role_assignment IS 'django-name:platform_role_assignment_user_id_e2307df7_fk_platform_user_id';


--
-- Name: platform_role_permission fk_role_permission__permission_action; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_permission
    ADD CONSTRAINT fk_role_permission__permission_action FOREIGN KEY (permission_action) REFERENCES public.platform_permission(action) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role_permission__permission_action ON platform_role_permission; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role_permission__permission_action ON public.platform_role_permission IS 'django-name:platform_role_permis_permission_action_38a38778_fk_platform_';


--
-- Name: platform_role_permission fk_role_permission__role_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_role_permission
    ADD CONSTRAINT fk_role_permission__role_id FOREIGN KEY (role_id) REFERENCES public.platform_role(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_role_permission__role_id ON platform_role_permission; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_role_permission__role_id ON public.platform_role_permission IS 'django-name:platform_role_permission_role_id_0f2c08dc_fk_platform_role_id';


--
-- Name: platform_session fk_session__revoked_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_session
    ADD CONSTRAINT fk_session__revoked_by_id FOREIGN KEY (revoked_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_session__revoked_by_id ON platform_session; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_session__revoked_by_id ON public.platform_session IS 'django-name:platform_session_revoked_by_id_deb3bdf0_fk_platform_user_id';


--
-- Name: platform_session fk_session__user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_session
    ADD CONSTRAINT fk_session__user_id FOREIGN KEY (user_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_session__user_id ON platform_session; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_session__user_id ON public.platform_session IS 'django-name:platform_session_user_id_068c793f_fk_platform_user_id';


--
-- Name: platform_user fk_user__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_user
    ADD CONSTRAINT fk_user__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_user__created_by_id ON platform_user; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_user__created_by_id ON public.platform_user IS 'django-name:platform_user_created_by_id_3d604985_fk_platform_user_id';


--
-- Name: platform_user fk_user__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_user
    ADD CONSTRAINT fk_user__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_user__updated_by_id ON platform_user; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_user__updated_by_id ON public.platform_user IS 'django-name:platform_user_updated_by_id_be367755_fk_platform_user_id';


--
-- Name: platform_work_task fk_work_task__assignee_position_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_work_task
    ADD CONSTRAINT fk_work_task__assignee_position_id FOREIGN KEY (assignee_position_id) REFERENCES public.platform_position(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_work_task__assignee_position_id ON platform_work_task; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_work_task__assignee_position_id ON public.platform_work_task IS 'django-name:platform_work_task_assignee_position_id_d07d6451_fk_platform_';


--
-- Name: platform_work_task fk_work_task__assignee_unit_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_work_task
    ADD CONSTRAINT fk_work_task__assignee_unit_id FOREIGN KEY (assignee_unit_id) REFERENCES public.platform_org_unit(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_work_task__assignee_unit_id ON platform_work_task; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_work_task__assignee_unit_id ON public.platform_work_task IS 'django-name:platform_work_task_assignee_unit_id_d7a35190_fk_platform_';


--
-- Name: platform_work_task fk_work_task__assignee_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_work_task
    ADD CONSTRAINT fk_work_task__assignee_user_id FOREIGN KEY (assignee_user_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_work_task__assignee_user_id ON platform_work_task; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_work_task__assignee_user_id ON public.platform_work_task IS 'django-name:platform_work_task_assignee_user_id_e9ece613_fk_platform_';


--
-- Name: platform_work_task fk_work_task__cancelled_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_work_task
    ADD CONSTRAINT fk_work_task__cancelled_by_id FOREIGN KEY (cancelled_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_work_task__cancelled_by_id ON platform_work_task; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_work_task__cancelled_by_id ON public.platform_work_task IS 'django-name:platform_work_task_cancelled_by_id_828bccc9_fk_platform_user_id';


--
-- Name: platform_work_task fk_work_task__closed_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_work_task
    ADD CONSTRAINT fk_work_task__closed_by_id FOREIGN KEY (closed_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_work_task__closed_by_id ON platform_work_task; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_work_task__closed_by_id ON public.platform_work_task IS 'django-name:platform_work_task_closed_by_id_0c654dd5_fk_platform_user_id';


--
-- Name: platform_work_task fk_work_task__completed_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_work_task
    ADD CONSTRAINT fk_work_task__completed_by_id FOREIGN KEY (completed_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_work_task__completed_by_id ON platform_work_task; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_work_task__completed_by_id ON public.platform_work_task IS 'django-name:platform_work_task_completed_by_id_d33a0286_fk_platform_user_id';


--
-- Name: platform_work_task fk_work_task__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_work_task
    ADD CONSTRAINT fk_work_task__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_work_task__created_by_id ON platform_work_task; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_work_task__created_by_id ON public.platform_work_task IS 'django-name:platform_work_task_created_by_id_d8fef8d4_fk_platform_user_id';


--
-- Name: platform_work_task fk_work_task__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_work_task
    ADD CONSTRAINT fk_work_task__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_work_task__updated_by_id ON platform_work_task; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_work_task__updated_by_id ON public.platform_work_task IS 'django-name:platform_work_task_updated_by_id_69f6ab87_fk_platform_user_id';


--
-- Name: platform_work_task fk_work_task__workflow_instance_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_work_task
    ADD CONSTRAINT fk_work_task__workflow_instance_id FOREIGN KEY (workflow_instance_id) REFERENCES public.platform_workflow_instance(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_work_task__workflow_instance_id ON platform_work_task; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_work_task__workflow_instance_id ON public.platform_work_task IS 'django-name:platform_work_task_workflow_instance_id_406334ee_fk_platform_';


--
-- Name: platform_workflow_instance fk_workflow_instance__cancel_requested_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_workflow_instance
    ADD CONSTRAINT fk_workflow_instance__cancel_requested_by_id FOREIGN KEY (cancel_requested_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_workflow_instance__cancel_requested_by_id ON platform_workflow_instance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_workflow_instance__cancel_requested_by_id ON public.platform_workflow_instance IS 'django-name:platform_workflow_in_cancel_requested_by__b831b9d0_fk_platform_';


--
-- Name: platform_workflow_instance fk_workflow_instance__definition_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_workflow_instance
    ADD CONSTRAINT fk_workflow_instance__definition_id FOREIGN KEY (definition_id) REFERENCES public.platform_workflow_definition(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_workflow_instance__definition_id ON platform_workflow_instance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_workflow_instance__definition_id ON public.platform_workflow_instance IS 'django-name:platform_workflow_in_definition_id_ab43b5d8_fk_platform_';


--
-- Name: platform_workflow_instance fk_workflow_instance__started_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_workflow_instance
    ADD CONSTRAINT fk_workflow_instance__started_by_id FOREIGN KEY (started_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_workflow_instance__started_by_id ON platform_workflow_instance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_workflow_instance__started_by_id ON public.platform_workflow_instance IS 'django-name:platform_workflow_in_started_by_id_3c29426f_fk_platform_';


--
-- Name: platform_workflow_step_event fk_workflow_step_event__actor_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_workflow_step_event
    ADD CONSTRAINT fk_workflow_step_event__actor_id FOREIGN KEY (actor_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_workflow_step_event__actor_id ON platform_workflow_step_event; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_workflow_step_event__actor_id ON public.platform_workflow_step_event IS 'django-name:platform_workflow_st_actor_id_679fa618_fk_platform_';


--
-- Name: platform_workflow_step_event fk_workflow_step_event__instance_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_workflow_step_event
    ADD CONSTRAINT fk_workflow_step_event__instance_id FOREIGN KEY (instance_id) REFERENCES public.platform_workflow_instance(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_workflow_step_event__instance_id ON platform_workflow_step_event; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_workflow_step_event__instance_id ON public.platform_workflow_step_event IS 'django-name:platform_workflow_st_instance_id_6b0cf7ff_fk_platform_';


--
-- Name: platform_conflict_item platform_conflict_it_batch_id_c92fb881_fk_platform_; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_conflict_item
    ADD CONSTRAINT platform_conflict_it_batch_id_c92fb881_fk_platform_ FOREIGN KEY (batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: platform_conflict_item platform_conflict_it_source_id_8a45872b_fk_platform_; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_conflict_item
    ADD CONSTRAINT platform_conflict_it_source_id_8a45872b_fk_platform_ FOREIGN KEY (source_id) REFERENCES public.platform_integration_source(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: platform_import_batch platform_import_batc_source_id_2e0caa3b_fk_platform_; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_import_batch
    ADD CONSTRAINT platform_import_batc_source_id_2e0caa3b_fk_platform_ FOREIGN KEY (source_id) REFERENCES public.platform_integration_source(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: platform_import_staging_row platform_import_stag_batch_id_ffe87cfc_fk_platform_; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_import_staging_row
    ADD CONSTRAINT platform_import_stag_batch_id_ffe87cfc_fk_platform_ FOREIGN KEY (batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: platform_integration_source platform_integration_last_success_batch_i_d00d7522_fk_platform_; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_integration_source
    ADD CONSTRAINT platform_integration_last_success_batch_i_d00d7522_fk_platform_ FOREIGN KEY (last_success_batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- PostgreSQL database dump complete
--


