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
-- Name: commercial_change_request_applied(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.commercial_change_request_applied() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    cur record;
BEGIN
    SELECT id, order_id, request_no, status, applied_version INTO cur
      FROM public.commercial_order_change_request WHERE id = NEW.id;
    IF cur.status = 'APPLIED' AND NOT EXISTS (
        SELECT 1 FROM public.commercial_customer_order_version v
         WHERE v.order_id = cur.order_id AND v.version = cur.applied_version AND v.change_request_id = cur.id) THEN
        RAISE EXCEPTION 'ck_commercial_cr_applied_has_version: applied request % wrote no order version %', cur.request_no, cur.applied_version
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$;


--
-- Name: commercial_change_request_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.commercial_change_request_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    ord record;
    released boolean;
    content_cols text[] := ARRAY['kind', 'items', 'reason', 'base_order_version'];
    c text;
BEGIN
    SELECT status, current_version, status_before_hold INTO ord
      FROM public.commercial_customer_order WHERE id = NEW.order_id;
    released := ord.status = 'RELEASED_TO_PLAN' OR (ord.status = 'ON_HOLD' AND ord.status_before_hold = 'RELEASED_TO_PLAN');
    IF TG_OP = 'INSERT' THEN
        IF NEW.status NOT IN ('DRAFT', 'SUBMITTED') THEN
            RAISE EXCEPTION 'ck_commercial_cr_starts_draft: a change request starts DRAFT or SUBMITTED'
                USING ERRCODE = 'check_violation';
        END IF;
        IF ord.status NOT IN ('CONFIRMED', 'RELEASED_TO_PLAN', 'ON_HOLD') THEN
            RAISE EXCEPTION 'ck_commercial_cr_order_state: change requests exist only for confirmed orders (state %)', ord.status
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.base_order_version <> ord.current_version THEN
            RAISE EXCEPTION 'ck_commercial_cr_base_is_current: base version % is not the current version %', NEW.base_order_version, ord.current_version
                USING ERRCODE = 'check_violation';
        END IF;
        IF released AND NEW.kind NOT IN ('DUE_DATE_CHANGE', 'HOLD', 'RESUME') THEN
            RAISE EXCEPTION 'ck_commercial_cr_kind_after_release: after release only due date and hold/resume (DEC-059)'
                USING ERRCODE = 'check_violation';
        END IF;
        IF (NEW.kind = 'RESUME') <> (ord.status = 'ON_HOLD') AND NEW.kind IN ('HOLD', 'RESUME') THEN
            RAISE EXCEPTION 'ck_commercial_cr_hold_state: HOLD needs a running order, RESUME a held one'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
           (OLD.status = 'DRAFT' AND NEW.status IN ('SUBMITTED', 'WITHDRAWN'))
        OR (OLD.status = 'SUBMITTED' AND NEW.status IN ('APPROVED', 'REJECTED', 'WITHDRAWN', 'EXPIRED'))
        OR (OLD.status = 'APPROVED' AND NEW.status IN ('APPLIED', 'EXPIRED'))
        -- DEC-059 amendment 2026-11-14: planning rejects a due-date change after the manager approved it
        OR (OLD.status = 'APPROVED' AND NEW.status = 'REJECTED' AND NEW.planning_rejected_by_id IS NOT NULL)) THEN
        RAISE EXCEPTION 'ck_commercial_cr_lifecycle: % -> % is not allowed', OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status <> 'DRAFT' THEN
        FOREACH c IN ARRAY content_cols LOOP
            IF (to_jsonb(NEW) -> c) IS DISTINCT FROM (to_jsonb(OLD) -> c) THEN
                RAISE EXCEPTION 'ck_commercial_cr_content_frozen: %.% is frozen after DRAFT', TG_TABLE_NAME, c
                    USING ERRCODE = 'restrict_violation';
            END IF;
        END LOOP;
    END IF;
    IF NEW.status = 'APPLIED' AND ord.current_version <> NEW.applied_version THEN
        RAISE EXCEPTION 'ck_commercial_cr_apply_on_current: the order is at version %, not % (stale base, re-submit)', ord.current_version, NEW.applied_version
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: commercial_line_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.commercial_line_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    ord record;
    rev_style uuid;
    code_style uuid;
    type_uom text;
    released boolean;
    changed_cols text[] := ARRAY[]::text[];
    c text;
    o jsonb;
    n jsonb;
BEGIN
    SELECT status, current_version, status_before_hold INTO ord
      FROM public.commercial_customer_order WHERE id = NEW.order_id;
    SELECT style_id INTO rev_style FROM public.identity_style_revision WHERE id = NEW.style_revision_id;
    IF rev_style IS DISTINCT FROM NEW.style_id THEN
        RAISE EXCEPTION 'ck_commercial_line_revision_of_style: the style revision belongs to another style'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.product_code_id IS NOT NULL THEN
        SELECT style_id INTO code_style FROM public.identity_product_code WHERE id = NEW.product_code_id;
        IF code_style IS DISTINCT FROM NEW.style_id THEN
            RAISE EXCEPTION 'ck_commercial_line_code_of_style: the product code belongs to another style'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    SELECT t.uom_code INTO type_uom
      FROM public.identity_style s
      JOIN public.identity_product p ON p.id = s.product_id
      JOIN public.identity_product_class t ON t.id = p.product_type_id
     WHERE s.id = NEW.style_id;
    IF type_uom IS DISTINCT FROM NEW.uom_code THEN
        RAISE EXCEPTION 'ck_commercial_line_uom_of_type: the line unit is the product type''s unit (DEC-058)'
            USING ERRCODE = 'check_violation';
    END IF;
    released := ord.status = 'RELEASED_TO_PLAN' OR (ord.status = 'ON_HOLD' AND ord.status_before_hold = 'RELEASED_TO_PLAN');

    IF TG_OP = 'INSERT' THEN
        IF NOT ((ord.status = 'DRAFT' AND NEW.status = 'OPEN')
             OR (ord.status = 'CONFIRMED' AND NEW.status = 'CONFIRMED' AND NEW.order_version = ord.current_version
                 AND ord.current_version >= 2)) THEN
            RAISE EXCEPTION 'ck_commercial_line_insert_state: a line is added to a DRAFT order, or by an applied ADD_LINE change before release (DEC-059)'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.serial_id IS NOT NULL AND NEW.serial_id IS DISTINCT FROM OLD.serial_id THEN
        RAISE EXCEPTION 'ck_commercial_line_serial_set_once: a line never gets a second serial (DEC-006)'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.order_version < OLD.order_version THEN
        RAISE EXCEPTION 'ck_commercial_line_version_monotonic: the line version never goes back'
            USING ERRCODE = 'check_violation';
    END IF;
    o := to_jsonb(OLD);
    n := to_jsonb(NEW);
    FOREACH c IN ARRAY ARRAY['style_revision_id', 'product_code_id', 'quantity', 'uom_code', 'requested_due_date',
                             'status', 'serial_id', 'cancel_reason', 'order_version'] LOOP
        IF (n -> c) IS DISTINCT FROM (o -> c) THEN
            changed_cols := changed_cols || c;
        END IF;
    END LOOP;
    IF cardinality(changed_cols) = 0 THEN
        RETURN NEW;
    END IF;

    IF OLD.status = 'OPEN' THEN
        IF NEW.status = 'CONFIRMED' THEN
            -- confirm (DEC-006 L-A): serial + version 1, nothing else changes
            IF ord.status NOT IN ('VALIDATED', 'CONFIRMED') OR NEW.order_version <> 1
               OR NOT (changed_cols <@ ARRAY['status', 'serial_id', 'order_version']) THEN
                RAISE EXCEPTION 'ck_commercial_line_confirm: a line is confirmed with its order, gets its serial and version 1, nothing else'
                    USING ERRCODE = 'check_violation';
            END IF;
        ELSIF ord.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'ck_commercial_line_draft_only: an open line is edited only while its order is DRAFT'
                USING ERRCODE = 'restrict_violation';
        ELSIF NEW.status NOT IN ('OPEN', 'REMOVED') THEN
            RAISE EXCEPTION 'ck_commercial_line_transition: OPEN -> % is not allowed', NEW.status
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    -- OLD.status = 'CONFIRMED' (REMOVED / CANCELLED are terminal): only through an applied change request
    IF NEW.order_version <> ord.current_version OR NEW.order_version <= OLD.order_version THEN
        RAISE EXCEPTION 'ck_commercial_line_change_needs_version: a confirmed line changes only with a new order version (DEC-059)'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF 'style_revision_id' = ANY (changed_cols) OR 'uom_code' = ANY (changed_cols)
       OR (OLD.product_code_id IS NOT NULL AND 'product_code_id' = ANY (changed_cols)) THEN
        RAISE EXCEPTION 'ck_commercial_line_identity_frozen: style revision, unit and an existing code of a confirmed line never change'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status AND NEW.status <> 'CANCELLED' THEN
        RAISE EXCEPTION 'ck_commercial_line_transition: CONFIRMED -> % is not allowed', NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    IF released AND NOT (changed_cols <@ ARRAY['requested_due_date', 'order_version']) THEN
        RAISE EXCEPTION 'ck_commercial_line_frozen_after_release: after release only the due date changes (DEC-059)'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: commercial_order_committed(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.commercial_order_committed() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    cur record;
    top int;
BEGIN
    SELECT id, order_no, current_version INTO cur FROM public.commercial_customer_order WHERE id = NEW.id;
    SELECT max(version) INTO top FROM public.commercial_customer_order_version WHERE order_id = cur.id;
    IF coalesce(top, 0) <> cur.current_version THEN
        RAISE EXCEPTION 'ck_commercial_order_version_row: order % is at version % but its last version row is %', cur.order_no, cur.current_version, coalesce(top, 0)
            USING ERRCODE = 'check_violation';
    END IF;
    IF cur.current_version >= 1 THEN
        IF EXISTS (SELECT 1 FROM public.commercial_customer_order_line WHERE order_id = cur.id AND status = 'OPEN') THEN
            RAISE EXCEPTION 'ck_commercial_order_no_open_line: confirmed order % still has an OPEN line', cur.order_no
                USING ERRCODE = 'check_violation';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM public.commercial_customer_order_line
                        WHERE order_id = cur.id AND status IN ('CONFIRMED', 'CANCELLED')) THEN
            RAISE EXCEPTION 'ck_commercial_order_has_lines: confirmed order % has no confirmed line', cur.order_no
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NULL;
END;
$$;


--
-- Name: commercial_order_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.commercial_order_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    brand_customer uuid;
    frozen_cols text[] := ARRAY['customer_id', 'brand_id', 'external_po_number', 'order_type_code', 'program_ref',
                                'order_date', 'required_quality_requirement', 'customer_representative_name'];
    data_cols text[] := frozen_cols || ARRAY['requested_due_date'];
    o jsonb;
    n jsonb;
    c text;
    step int;
BEGIN
    IF NEW.brand_id IS NOT NULL THEN
        SELECT customer_id INTO brand_customer FROM public.identity_customer_brand WHERE id = NEW.brand_id;
        IF brand_customer IS DISTINCT FROM NEW.customer_id THEN
            RAISE EXCEPTION 'ck_commercial_order_brand_of_customer: the brand belongs to another customer (DEC-058)'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'ck_commercial_order_starts_draft: an order starts as DRAFT'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    step := NEW.current_version - OLD.current_version;
    IF step NOT IN (0, 1) THEN
        RAISE EXCEPTION 'ck_commercial_order_version_step: the order version moves by +1 only'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        -- coalesce: a NULL comparison (e.g. a missing status_before_hold) must refuse, not pass
        IF NOT coalesce(
               (OLD.status = 'DRAFT' AND NEW.status IN ('VALIDATED', 'CANCELLED') AND step = 0)
            OR (OLD.status = 'VALIDATED' AND NEW.status IN ('DRAFT', 'CANCELLED') AND step = 0)
            OR (OLD.status = 'VALIDATED' AND NEW.status = 'CONFIRMED' AND NEW.current_version = 1)
            OR (OLD.status = 'CONFIRMED' AND NEW.status = 'RELEASED_TO_PLAN' AND step = 0)
            OR (OLD.status IN ('CONFIRMED', 'RELEASED_TO_PLAN') AND NEW.status = 'ON_HOLD' AND step = 1
                AND NEW.status_before_hold = OLD.status)
            OR (OLD.status = 'ON_HOLD' AND NEW.status = OLD.status_before_hold AND step = 1)
            OR (OLD.status = 'CONFIRMED' AND NEW.status = 'CANCELLED' AND step = 1)
            -- DEC-059 amendment 2026-11-12: a held order whose stored state is before release
            OR (OLD.status = 'ON_HOLD' AND OLD.status_before_hold = 'CONFIRMED' AND NEW.status = 'CANCELLED'
                AND step = 1), false) THEN
            RAISE EXCEPTION 'ck_commercial_order_transition: % -> % is not allowed (DEC-059)', OLD.status, NEW.status
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    o := to_jsonb(OLD);
    n := to_jsonb(NEW);
    IF OLD.status <> 'DRAFT' THEN
        FOREACH c IN ARRAY CASE WHEN OLD.status = 'VALIDATED' THEN data_cols ELSE frozen_cols END LOOP
            IF (n -> c) IS DISTINCT FROM (o -> c) THEN
                RAISE EXCEPTION 'ck_commercial_order_frozen: %.% cannot change in state % (DEC-059: change request)', TG_TABLE_NAME, c, OLD.status
                    USING ERRCODE = 'restrict_violation';
            END IF;
        END LOOP;
        IF OLD.status NOT IN ('VALIDATED') AND NEW.requested_due_date IS DISTINCT FROM OLD.requested_due_date
           AND step <> 1 THEN
            RAISE EXCEPTION 'ck_commercial_order_frozen: a confirmed due date changes only with a new order version (DEC-059)'
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;
    -- cancel after release (DEC-059 C-A, waits for PHASE_05) is excluded by the transition list above
    RETURN NEW;
END;
$$;


--
-- Name: commercial_order_version_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.commercial_order_version_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    last_version int;
    cr_order uuid;
BEGIN
    PERFORM 1 FROM public.commercial_customer_order WHERE id = NEW.order_id FOR UPDATE;
    SELECT coalesce(max(version), 0) INTO last_version
      FROM public.commercial_customer_order_version WHERE order_id = NEW.order_id;
    IF NEW.version <> last_version + 1 THEN
        RAISE EXCEPTION 'ck_commercial_order_version_contiguous: next version is %, got %', last_version + 1, NEW.version
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.change_request_id IS NOT NULL THEN
        SELECT order_id INTO cr_order FROM public.commercial_order_change_request WHERE id = NEW.change_request_id;
        IF cr_order IS DISTINCT FROM NEW.order_id THEN
            RAISE EXCEPTION 'ck_commercial_order_version_cr_of_order: the change request belongs to another order'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: identity_code_rule_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_code_rule_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    content_cols text[] := ARRAY['scope', 'rule_spec', 'source_workbook_sha256', 'evidence_document_id',
                                 'golden_case_count', 'decision_id'];
    o jsonb;
    n jsonb;
    c text;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'DRAFT' THEN
            RAISE EXCEPTION 'ck_identity_code_rule_lifecycle: a rule revision starts as DRAFT'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
           (OLD.status = 'DRAFT' AND NEW.status = 'IN_REVIEW')
        OR (OLD.status = 'IN_REVIEW' AND NEW.status IN ('APPROVED', 'REJECTED'))
        OR (OLD.status = 'APPROVED' AND NEW.status = 'ACTIVE')
        OR (OLD.status = 'ACTIVE' AND NEW.status = 'RETIRED')) THEN
        RAISE EXCEPTION 'ck_identity_code_rule_lifecycle: % -> % is not allowed', OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status <> 'DRAFT' THEN
        o := to_jsonb(OLD);
        n := to_jsonb(NEW);
        FOREACH c IN ARRAY content_cols LOOP
            IF (n -> c) IS DISTINCT FROM (o -> c) THEN
                RAISE EXCEPTION 'ck_identity_code_rule_content_frozen: %.% is frozen after DRAFT', TG_TABLE_NAME, c
                    USING ERRCODE = 'restrict_violation';
            END IF;
        END LOOP;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: identity_historical_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_historical_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    legacy_ceiling bigint;
    mutable_cols text[] := ARRAY['match_status', 'matched_style_id', 'matched_product_code_id', 'matched_by_id',
                                 'matched_at', 'legacy_serial_duplicate', 'updated_at', 'row_version'];
BEGIN
    IF TG_OP = 'UPDATE' AND (to_jsonb(NEW) - mutable_cols) IS DISTINCT FROM (to_jsonb(OLD) - mutable_cols) THEN
        RAISE EXCEPTION 'ck_identity_historical_immutable: legacy evidence changes only in its match columns'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.legacy_serial_value IS NOT NULL THEN
        SELECT legacy_max_exclusive INTO legacy_ceiling FROM public.identity_serial_counter
         WHERE namespace_key = 'factory_serial';
        IF legacy_ceiling IS NULL OR NEW.legacy_serial_value >= legacy_ceiling THEN
            RAISE EXCEPTION 'ck_identity_historical_legacy_serial_below_system_range: legacy serial % is not below % (DEC-006); raise a conflict instead', NEW.legacy_serial_value, legacy_ceiling
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: identity_product_class_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_product_class_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    parent_level text;
BEGIN
    IF NEW.level_key = 'category' THEN
        SELECT level_key INTO parent_level FROM public.identity_product_class WHERE id = NEW.parent_id;
        IF parent_level IS DISTINCT FROM 'product_type' THEN
            RAISE EXCEPTION 'ck_identity_class_category_under_type: a category hangs under a product type'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: identity_product_code_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_product_code_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    rule_status text;
    rule_ns text;
    derived text;
BEGIN
    IF TG_OP = 'INSERT' AND NEW.provenance_kind = 'SYS' THEN
        SELECT status, code_namespace INTO rule_status, rule_ns
          FROM public.identity_code_rule_revision WHERE id = NEW.rule_revision_id FOR SHARE;
        IF rule_status IS DISTINCT FROM 'ACTIVE' OR rule_ns IS DISTINCT FROM NEW.code_namespace THEN
            RAISE EXCEPTION 'RULE_NOT_APPROVED: a product code is issued only under an ACTIVE rule revision (DEC-005)'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.status <> 'RESERVED' THEN
            RAISE EXCEPTION 'ck_identity_product_code_issued_reserved: an issued code starts RESERVED / ERP_PENDING (B1)'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.style_id IS NOT NULL AND NEW.style_id IS DISTINCT FROM OLD.style_id THEN
        RAISE EXCEPTION 'ck_identity_product_code_style_set_once: the style link of a code is set once'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.style_id IS NOT NULL AND NEW.status IN ('RESERVED', 'ACTIVE') THEN
        SELECT t.segment_value || c.segment_value || p.product_no || s.style_no INTO derived
          FROM public.identity_style s
          JOIN public.identity_product p ON p.id = s.product_id
          JOIN public.identity_product_class t ON t.id = p.product_type_id
          JOIN public.identity_product_class c ON c.id = s.category_id
         WHERE s.id = NEW.style_id;
        IF substr(NEW.code, 3) IS DISTINCT FROM derived THEN
            RAISE EXCEPTION 'ck_identity_product_code_matches_style: a live code equals its style''s segments (DEC-005)'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: identity_product_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_product_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    t record;
BEGIN
    SELECT level_key, product_no_scheme INTO t FROM public.identity_product_class WHERE id = NEW.product_type_id;
    IF t.level_key IS DISTINCT FROM 'product_type' THEN
        RAISE EXCEPTION 'ck_identity_product_of_type: a product belongs to a product type'
            USING ERRCODE = 'check_violation';
    END IF;
    IF (t.product_no_scheme = 'BELT_BUCKLE_WIDTH') <> (NEW.buckle_type_code IS NOT NULL) THEN
        RAISE EXCEPTION 'ck_identity_product_belt_scheme: buckle + width exactly for belt-scheme types (DEC-005)'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: identity_serial_committed(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_serial_committed() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    lines int;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.identity_serial_snapshot WHERE serial_id = NEW.id AND version = 1) THEN
        RAISE EXCEPTION 'ck_identity_serial_has_snapshot_v1: serial % has no snapshot version 1', NEW.serial_number
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT count(*) INTO lines FROM public.commercial_customer_order_line WHERE serial_id = NEW.id;
    IF lines <> 1 THEN
        RAISE EXCEPTION 'ck_identity_serial_one_line: serial % is referenced by % order lines (expected 1)', NEW.serial_number, lines
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$;


--
-- Name: identity_serial_counter_gapless(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_serial_counter_gapless() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    IF NEW.next_value > OLD.next_value AND NOT EXISTS (
        SELECT 1 FROM public.identity_serial s
         WHERE s.serial_counter_id = NEW.id AND s.serial_value = OLD.next_value) THEN
        RAISE EXCEPTION 'ck_identity_serial_counter_gapless: number % was drawn but no serial holds it', OLD.next_value
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$;


--
-- Name: identity_serial_counter_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_serial_counter_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.next_value <> NEW.start_value THEN
            RAISE EXCEPTION 'ck_identity_serial_counter_starts_at_start: a new counter starts at its start value'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.next_value <> OLD.next_value AND NEW.next_value <> OLD.next_value + 1 THEN
        RAISE EXCEPTION 'ck_identity_serial_counter_step: the counter moves by exactly +1 per allocation (gapless, DEC-006)'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: identity_serial_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_serial_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    c record;
    rev_style uuid;
    code_style uuid;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT start_value, next_value INTO c FROM public.identity_serial_counter WHERE id = NEW.serial_counter_id;
        IF NOT (NEW.serial_value >= c.start_value AND NEW.serial_value < c.next_value) THEN
            RAISE EXCEPTION 'ck_identity_serial_drawn_from_counter: % was not drawn from the counter (DEC-006)', NEW.serial_value
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.status <> 'ALLOCATED' THEN
            RAISE EXCEPTION 'ck_identity_serial_starts_allocated: a serial starts ALLOCATED'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.status IS DISTINCT FROM OLD.status AND NOT (OLD.status = 'ALLOCATED' AND NEW.status = 'CANCELLED') THEN
        -- PHASE_02 writes ALLOCATED / CANCELLED only; later phases extend this graph by migration
        RAISE EXCEPTION 'ck_identity_serial_lifecycle: % -> % is not allowed in PHASE_02', OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT style_id INTO rev_style FROM public.identity_style_revision WHERE id = NEW.style_revision_id;
    IF rev_style IS DISTINCT FROM NEW.style_id THEN
        RAISE EXCEPTION 'ck_identity_serial_revision_of_style: the style revision belongs to another style'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.product_code_id IS NOT NULL THEN
        SELECT style_id INTO code_style FROM public.identity_product_code WHERE id = NEW.product_code_id;
        IF code_style IS DISTINCT FROM NEW.style_id THEN
            RAISE EXCEPTION 'ck_identity_serial_code_of_style: the product code belongs to another style'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: identity_serial_snapshot_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_serial_snapshot_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    last_version int;
BEGIN
    PERFORM 1 FROM public.identity_serial WHERE id = NEW.serial_id FOR UPDATE;
    SELECT coalesce(max(version), 0) INTO last_version FROM public.identity_serial_snapshot WHERE serial_id = NEW.serial_id;
    IF NEW.version <> last_version + 1 THEN
        RAISE EXCEPTION 'ck_identity_serial_snapshot_contiguous: next version is %, got %', last_version + 1, NEW.version
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: identity_style_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_style_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    c record;
    product_type uuid;
BEGIN
    SELECT level_key, parent_id INTO c FROM public.identity_product_class WHERE id = NEW.category_id;
    SELECT product_type_id INTO product_type FROM public.identity_product WHERE id = NEW.product_id;
    IF c.level_key IS DISTINCT FROM 'category' OR c.parent_id IS DISTINCT FROM product_type THEN
        RAISE EXCEPTION 'ck_identity_style_category_of_type: the category must belong to the product''s type'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: identity_style_revision_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.identity_style_revision_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    volatile_cols text[] := ARRAY['status', 'updated_at', 'updated_by_id', 'row_version'];
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status
       AND NOT ((OLD.status = 'DRAFT' AND NEW.status = 'ACTIVE') OR (OLD.status = 'ACTIVE' AND NEW.status = 'SUPERSEDED')) THEN
        RAISE EXCEPTION 'ck_identity_style_revision_lifecycle: % -> % is not allowed', OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.status <> 'DRAFT' AND (to_jsonb(NEW) - volatile_cols) IS DISTINCT FROM (to_jsonb(OLD) - volatile_cols) THEN
        RAISE EXCEPTION 'ck_identity_style_revision_immutable: an % revision cannot change (new revision instead)', OLD.status
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: phase02_line_serial_cancel_paired(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.phase02_line_serial_cancel_paired() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    line_cancelled boolean;
    serial_cancelled boolean;
    sid uuid := (to_jsonb(NEW) ->> CASE WHEN TG_TABLE_NAME = 'identity_serial' THEN 'id' ELSE 'serial_id' END)::uuid;
BEGIN
    IF sid IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT l.status = 'CANCELLED' INTO line_cancelled FROM public.commercial_customer_order_line l WHERE l.serial_id = sid;
    SELECT s.status = 'CANCELLED' INTO serial_cancelled FROM public.identity_serial s WHERE s.id = sid;
    IF line_cancelled IS DISTINCT FROM serial_cancelled THEN
        RAISE EXCEPTION 'ck_phase02_line_serial_cancel_paired: line and serial are cancelled together (DEC-059)'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$$;


--
-- Name: platform_approval_request_bootstrap_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_approval_request_bootstrap_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
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
$$;


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
-- Name: platform_number_counter_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_number_counter_guard() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.last_value <> 1 THEN
            RAISE EXCEPTION 'ck_number_counter_starts_at_one: a counter row starts at 1'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'ck_number_counter_no_delete: a number counter is never deleted'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.kind IS DISTINCT FROM OLD.kind OR NEW.jalali_year IS DISTINCT FROM OLD.jalali_year
       OR NEW.last_value <> OLD.last_value + 1 THEN
        RAISE EXCEPTION 'ck_number_counter_forward_only: a number counter only moves forward by one'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: platform_number_counter_no_truncate(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_number_counter_no_truncate() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
BEGIN
    RAISE EXCEPTION 'ck_number_counter_no_truncate: number counters are never truncated'
        USING ERRCODE = 'restrict_violation';
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
    LANGUAGE sql STABLE
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
    SELECT public.platform_param_value_at(p_key, statement_timestamp());
$$;


--
-- Name: platform_param_value_at(text, timestamp with time zone); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.platform_param_value_at(p_key text, p_at timestamp with time zone) RETURNS text
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'pg_temp'
    AS $$
DECLARE
    v text;
BEGIN
    SELECT pv.value INTO v
      FROM public.platform_parameter_value pv
     WHERE pv.parameter_key = p_key
       AND (pv.status = 'PUBLISHED'
            OR (pv.status = 'SUPERSEDED' AND pv.superseded_at > pv.effective_from))
       AND pv.effective_from <= p_at
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
         WHERE rp.permission_action = NEW.action AND r.kind = 'TECHNICAL'
           AND NOT (r.code = 'owner_admin' AND NEW.action IN (
               'platform.workflow.approval.decide', 'platform.document.approve', 'platform.config.parameter.publish',
           'identity.code_rule.approve', 'commercial.order.confirm', 'commercial.change.decide'))) THEN
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
         WHERE rp.role_id = NEW.id AND p.business_approval
           AND NOT (NEW.code = 'owner_admin' AND p.action IN (
               'platform.workflow.approval.decide', 'platform.document.approve', 'platform.config.parameter.publish',
           'identity.code_rule.approve', 'commercial.order.confirm', 'commercial.change.decide'))) THEN
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
    -- DEC-003; explicit exception DEC-056 + DEC-057 (matrix v2.0): owner_admin holds exactly these six
    IF r.kind = 'TECHNICAL' AND is_ba
       AND NOT (r.code = 'owner_admin' AND NEW.permission_action IN (
           'platform.workflow.approval.decide', 'platform.document.approve', 'platform.config.parameter.publish',
           'identity.code_rule.approve', 'commercial.order.confirm', 'commercial.change.decide')) THEN
        RAISE EXCEPTION 'ck_role_technical_no_business_approval: TECHNICAL role cannot hold %', NEW.permission_action
            USING ERRCODE = 'check_violation',
                  HINT = 'DEC-003: admin rights are not business approval (DEC-056/DEC-057 v2.0: owner decide, document approve, parameter publish, code-rule approve, order confirm, change decide only).';
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
-- Name: commercial_customer_order; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commercial_customer_order (
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    order_no character varying(32) NOT NULL,
    external_po_number character varying(64) DEFAULT ''::character varying NOT NULL,
    program_ref character varying(64),
    order_date date NOT NULL,
    requested_due_date date,
    required_quality_requirement character varying(64),
    customer_representative_name character varying(200),
    status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    status_before_hold character varying(20),
    hold_reason character varying(500),
    cancel_reason character varying(500),
    cancelled_at timestamp with time zone,
    current_version integer DEFAULT 0 NOT NULL,
    confirmed_at timestamp with time zone,
    released_at timestamp with time zone,
    brand_id uuid,
    confirmed_by_id uuid,
    created_by_id uuid,
    customer_id uuid NOT NULL,
    released_by_id uuid,
    updated_by_id uuid,
    order_type_code character varying(64) NOT NULL,
    CONSTRAINT ck_commercial_order_cancel_after_confirm CHECK (((NOT ((current_version >= 1) AND ((status)::text = 'CANCELLED'::text))) OR (confirmed_by_id IS NOT NULL))),
    CONSTRAINT ck_commercial_order_cancel_has_reason CHECK (((NOT ((status)::text = 'CANCELLED'::text)) OR ((cancel_reason IS NOT NULL) AND (cancelled_at IS NOT NULL) AND (length((cancel_reason)::text) >= 3)))),
    CONSTRAINT ck_commercial_order_confirmed_versioned CHECK ((((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'VALIDATED'::character varying, 'CANCELLED'::character varying])::text[])) OR ((confirmed_at IS NOT NULL) AND (confirmed_by_id IS NOT NULL) AND (current_version >= 1)))),
    CONSTRAINT ck_commercial_order_confirmer_not_creator CHECK (((confirmed_by_id IS NULL) OR ((created_by_id IS NOT NULL) AND (NOT ((confirmed_by_id = created_by_id) AND (confirmed_by_id IS NOT NULL) AND (created_by_id IS NOT NULL)))))),
    CONSTRAINT ck_commercial_order_draft_unversioned CHECK (((NOT ((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'VALIDATED'::character varying])::text[]))) OR ((confirmed_by_id IS NULL) AND (current_version = 0)))),
    CONSTRAINT ck_commercial_order_due_after_order CHECK (((requested_due_date IS NULL) OR (requested_due_date >= order_date))),
    CONSTRAINT ck_commercial_order_hold_consistent CHECK ((((hold_reason IS NOT NULL) AND ((status)::text = 'ON_HOLD'::text) AND ((status_before_hold)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'RELEASED_TO_PLAN'::character varying])::text[])) AND (status_before_hold IS NOT NULL) AND (length((hold_reason)::text) >= 3)) OR ((NOT ((status)::text = 'ON_HOLD'::text)) AND (hold_reason IS NULL) AND (status_before_hold IS NULL)))),
    CONSTRAINT ck_commercial_order_no_fmt CHECK (((NOT ((order_no)::text = ''::text)) AND ((order_no)::text = TRIM(BOTH FROM order_no)))),
    CONSTRAINT ck_commercial_order_released_has_actor CHECK ((((NOT ((status)::text = 'RELEASED_TO_PLAN'::text)) AND (NOT (((status_before_hold)::text = 'RELEASED_TO_PLAN'::text) AND (status_before_hold IS NOT NULL)))) OR ((released_at IS NOT NULL) AND (released_by_id IS NOT NULL)))),
    CONSTRAINT ck_commercial_order_rep_name_nonempty CHECK (((customer_representative_name IS NULL) OR (NOT (((customer_representative_name)::text = ''::text) AND (customer_representative_name IS NOT NULL))))),
    CONSTRAINT ck_commercial_order_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_commercial_order_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'VALIDATED'::character varying, 'CONFIRMED'::character varying, 'RELEASED_TO_PLAN'::character varying, 'ON_HOLD'::character varying, 'CANCELLED'::character varying, 'PARTIAL_FULFILLED'::character varying, 'FULFILLED'::character varying, 'CLOSED'::character varying])::text[]))),
    CONSTRAINT ck_commercial_order_version_nonneg CHECK ((current_version >= 0))
);


--
-- Name: commercial_customer_order_line; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commercial_customer_order_line (
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    line_no integer NOT NULL,
    quantity integer NOT NULL,
    requested_due_date date,
    status character varying(12) DEFAULT 'OPEN'::character varying NOT NULL,
    order_version integer DEFAULT 0 NOT NULL,
    cancel_reason character varying(500),
    created_by_id uuid,
    order_id uuid NOT NULL,
    updated_by_id uuid,
    product_code_id uuid,
    serial_id uuid,
    style_id uuid NOT NULL,
    style_revision_id uuid NOT NULL,
    uom_code character varying(8) NOT NULL,
    CONSTRAINT ck_commercial_line_cancel_has_reason CHECK (((NOT ((status)::text = 'CANCELLED'::text)) OR ((cancel_reason IS NOT NULL) AND (length((cancel_reason)::text) >= 3)))),
    CONSTRAINT ck_commercial_line_no_pos CHECK ((line_no >= 1)),
    CONSTRAINT ck_commercial_line_quantity_pos CHECK ((quantity > 0)),
    CONSTRAINT ck_commercial_line_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_commercial_line_serial_by_status CHECK ((((order_version = 0) AND (serial_id IS NULL) AND ((status)::text = ANY ((ARRAY['OPEN'::character varying, 'REMOVED'::character varying])::text[]))) OR ((order_version >= 1) AND (serial_id IS NOT NULL) AND ((status)::text = 'CONFIRMED'::text)) OR ((order_version >= 1) AND (serial_id IS NOT NULL) AND ((status)::text = 'CANCELLED'::text)))),
    CONSTRAINT ck_commercial_line_status CHECK (((status)::text = ANY ((ARRAY['OPEN'::character varying, 'CONFIRMED'::character varying, 'REMOVED'::character varying, 'CANCELLED'::character varying])::text[])))
);


--
-- Name: commercial_customer_order_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commercial_customer_order_version (
    id uuid NOT NULL,
    version integer NOT NULL,
    image jsonb NOT NULL,
    reason character varying(16) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    created_by_id uuid NOT NULL,
    order_id uuid NOT NULL,
    change_request_id uuid,
    CONSTRAINT ck_commercial_order_version_image CHECK ((jsonb_typeof(image) = 'object'::text)),
    CONSTRAINT ck_commercial_order_version_pos CHECK ((version >= 1)),
    CONSTRAINT ck_commercial_order_version_reason CHECK (((reason)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'CHANGE_APPLIED'::character varying, 'CANCELLED'::character varying])::text[]))),
    CONSTRAINT ck_commercial_order_version_reason_by_no CHECK ((((change_request_id IS NULL) AND ((reason)::text = 'CONFIRMED'::text) AND (version = 1)) OR ((change_request_id IS NOT NULL) AND (version > 1) AND (NOT ((reason)::text = 'CONFIRMED'::text)))))
);


--
-- Name: commercial_order_change_request; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commercial_order_change_request (
    id uuid NOT NULL,
    request_no character varying(32) NOT NULL,
    base_order_version integer NOT NULL,
    kind character varying(16) NOT NULL,
    items jsonb NOT NULL,
    reason character varying(500) NOT NULL,
    status character varying(12) DEFAULT 'DRAFT'::character varying NOT NULL,
    impact jsonb,
    submitted_at timestamp with time zone,
    decided_at timestamp with time zone,
    planning_approved_at timestamp with time zone,
    applied_at timestamp with time zone,
    applied_version integer,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    applied_by_id uuid,
    approval_id uuid,
    decided_by_id uuid,
    order_id uuid NOT NULL,
    planning_approval_id uuid,
    planning_approved_by_id uuid,
    requested_by_id uuid NOT NULL,
    planning_rejected_at timestamp with time zone,
    planning_rejected_by_id uuid,
    CONSTRAINT ck_commercial_cr_applied_next_version CHECK (((NOT ((status)::text = 'APPLIED'::text)) OR ((applied_at IS NOT NULL) AND (applied_by_id IS NOT NULL) AND (applied_version = (base_order_version + 1)) AND (applied_version IS NOT NULL)))),
    CONSTRAINT ck_commercial_cr_base_version_pos CHECK ((base_order_version >= 1)),
    CONSTRAINT ck_commercial_cr_decided_has_decider CHECK ((((NOT ((status)::text = ANY ((ARRAY['APPROVED'::character varying, 'APPLIED'::character varying])::text[]))) OR (decided_by_id IS NOT NULL)) AND ((NOT ((status)::text = 'REJECTED'::text)) OR (decided_by_id IS NOT NULL) OR (planning_rejected_by_id IS NOT NULL)))),
    CONSTRAINT ck_commercial_cr_decided_pair CHECK ((((decided_at IS NULL) AND (decided_by_id IS NULL)) OR ((decided_at IS NOT NULL) AND (decided_by_id IS NOT NULL)))),
    CONSTRAINT ck_commercial_cr_decider_not_requester CHECK (((decided_by_id IS NULL) OR (NOT ((decided_by_id = requested_by_id) AND (decided_by_id IS NOT NULL))))),
    CONSTRAINT ck_commercial_cr_due_date_planning_approved CHECK (((NOT (((kind)::text = 'DUE_DATE_CHANGE'::text) AND ((status)::text = 'APPLIED'::text))) OR (planning_approved_by_id IS NOT NULL))),
    CONSTRAINT ck_commercial_cr_impact_object CHECK (((impact IS NULL) OR (jsonb_typeof(impact) = 'object'::text))),
    CONSTRAINT ck_commercial_cr_items_array CHECK ((jsonb_typeof(items) = 'array'::text)),
    CONSTRAINT ck_commercial_cr_kind CHECK (((kind)::text = ANY ((ARRAY['QTY_CHANGE'::character varying, 'DUE_DATE_CHANGE'::character varying, 'ADD_LINE'::character varying, 'CANCEL_LINE'::character varying, 'CANCEL_ORDER'::character varying, 'HOLD'::character varying, 'RESUME'::character varying])::text[]))),
    CONSTRAINT ck_commercial_cr_planner_not_decider CHECK (((planning_approved_by_id IS NULL) OR (decided_by_id IS NULL) OR (NOT ((planning_approved_by_id = decided_by_id) AND (planning_approved_by_id IS NOT NULL) AND (decided_by_id IS NOT NULL))))),
    CONSTRAINT ck_commercial_cr_planner_not_requester CHECK (((planning_approved_by_id IS NULL) OR (NOT ((planning_approved_by_id = requested_by_id) AND (planning_approved_by_id IS NOT NULL))))),
    CONSTRAINT ck_commercial_cr_planning_only_due_date CHECK ((((planning_approval_id IS NULL) AND (planning_approved_by_id IS NULL)) OR ((kind)::text = 'DUE_DATE_CHANGE'::text))),
    CONSTRAINT ck_commercial_cr_planning_pair CHECK ((((planning_approved_at IS NULL) AND (planning_approved_by_id IS NULL)) OR ((planning_approved_at IS NOT NULL) AND (planning_approved_by_id IS NOT NULL)))),
    CONSTRAINT ck_commercial_cr_planning_rejected_closes CHECK (((planning_rejected_by_id IS NULL) OR (((kind)::text = 'DUE_DATE_CHANGE'::text) AND (planning_approved_by_id IS NULL) AND ((status)::text = 'REJECTED'::text)))),
    CONSTRAINT ck_commercial_cr_planning_rejected_pair CHECK ((((planning_rejected_at IS NULL) AND (planning_rejected_by_id IS NULL)) OR ((planning_rejected_at IS NOT NULL) AND (planning_rejected_by_id IS NOT NULL)))),
    CONSTRAINT ck_commercial_cr_planning_rejecter_independent CHECK (((planning_rejected_by_id IS NULL) OR ((NOT ((planning_rejected_by_id = requested_by_id) AND (planning_rejected_by_id IS NOT NULL))) AND ((decided_by_id IS NULL) OR (NOT ((planning_rejected_by_id = decided_by_id) AND (planning_rejected_by_id IS NOT NULL) AND (decided_by_id IS NOT NULL))))))),
    CONSTRAINT ck_commercial_cr_reason_len CHECK ((length((reason)::text) >= 3)),
    CONSTRAINT ck_commercial_cr_request_no_fmt CHECK (((NOT ((request_no)::text = ''::text)) AND ((request_no)::text = TRIM(BOTH FROM request_no)))),
    CONSTRAINT ck_commercial_cr_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'SUBMITTED'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying, 'APPLIED'::character varying, 'WITHDRAWN'::character varying, 'EXPIRED'::character varying])::text[]))),
    CONSTRAINT ck_commercial_cr_submitted_has_ts CHECK (((NOT ((status)::text = ANY ((ARRAY['SUBMITTED'::character varying, 'APPROVED'::character varying, 'APPLIED'::character varying])::text[]))) OR (submitted_at IS NOT NULL))),
    CONSTRAINT ck_commercial_cr_unapplied_empty CHECK ((((status)::text = 'APPLIED'::text) OR ((applied_at IS NULL) AND (applied_by_id IS NULL) AND (applied_version IS NULL))))
);


--
-- Name: commercial_order_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commercial_order_type (
    code character varying(64) NOT NULL,
    label_fa character varying(100) NOT NULL,
    sort_order smallint NOT NULL,
    status character varying(8) DEFAULT 'ACTIVE'::character varying NOT NULL,
    decision_id character varying(7) NOT NULL,
    provenance character varying(16) DEFAULT 'SYS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    CONSTRAINT ck_commercial_order_type_code_fmt CHECK (((code)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text)),
    CONSTRAINT ck_commercial_order_type_decision CHECK (((decision_id)::text ~ '^DEC-[0-9]{3}$'::text)),
    CONSTRAINT ck_commercial_order_type_label_nonempty CHECK ((NOT ((label_fa)::text = ''::text))),
    CONSTRAINT ck_commercial_order_type_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'MIGRATION_SEED'::character varying])::text[]))),
    CONSTRAINT ck_commercial_order_type_sort_nonneg CHECK ((sort_order >= 0)),
    CONSTRAINT ck_commercial_order_type_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying])::text[])))
);


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
-- Name: identity_code_rule_golden_case; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_code_rule_golden_case (
    id uuid NOT NULL,
    product_type_code character varying(2) NOT NULL,
    inputs jsonb NOT NULL,
    expected_code character varying(14) NOT NULL,
    source_sheet character varying(100) NOT NULL,
    source_cell_ref character varying(32) NOT NULL,
    source_workbook_sha256 character varying(64) NOT NULL,
    verified_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    created_by_id uuid,
    verified_by_id uuid,
    rule_revision_id uuid NOT NULL,
    CONSTRAINT ck_identity_golden_case_code_fmt CHECK (((expected_code)::text ~ '^[0-9]{14}$'::text)),
    CONSTRAINT ck_identity_golden_case_family_fmt CHECK (((product_type_code)::text ~ '^[0-9]{2}$'::text)),
    CONSTRAINT ck_identity_golden_case_family_segment CHECK (((product_type_code)::text = "substring"((expected_code)::text, 3, 2))),
    CONSTRAINT ck_identity_golden_case_inputs_object CHECK ((jsonb_typeof(inputs) = 'object'::text)),
    CONSTRAINT ck_identity_golden_case_sha256_fmt CHECK (((source_workbook_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_identity_golden_case_source CHECK (((NOT ((source_sheet)::text = ''::text)) AND (NOT ((source_cell_ref)::text = ''::text)))),
    CONSTRAINT ck_identity_golden_case_verified_pair CHECK ((((verified_at IS NULL) AND (verified_by_id IS NULL)) OR ((verified_at IS NOT NULL) AND (verified_by_id IS NOT NULL))))
);


--
-- Name: identity_code_rule_revision; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_code_rule_revision (
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    code_namespace character varying(16) DEFAULT 'product_code'::character varying NOT NULL,
    revision_no integer NOT NULL,
    scope jsonb NOT NULL,
    rule_spec jsonb NOT NULL,
    source_workbook_sha256 character varying(64) NOT NULL,
    golden_case_count integer DEFAULT 0 NOT NULL,
    status character varying(12) DEFAULT 'DRAFT'::character varying NOT NULL,
    decision_id character varying(7) NOT NULL,
    approved_at timestamp with time zone,
    approval_id uuid,
    approved_by_id uuid,
    created_by_id uuid,
    evidence_document_id uuid,
    updated_by_id uuid,
    CONSTRAINT ck_identity_code_rule_approved_by_other CHECK (((NOT ((status)::text = ANY ((ARRAY['APPROVED'::character varying, 'ACTIVE'::character varying, 'RETIRED'::character varying])::text[]))) OR ((approved_at IS NOT NULL) AND (approved_by_id IS NOT NULL) AND (created_by_id IS NOT NULL) AND (NOT ((approved_by_id = created_by_id) AND (approved_by_id IS NOT NULL) AND (created_by_id IS NOT NULL)))))),
    CONSTRAINT ck_identity_code_rule_decision_fmt CHECK (((decision_id)::text ~ '^DEC-[0-9]{3}$'::text)),
    CONSTRAINT ck_identity_code_rule_golden_nonneg CHECK ((golden_case_count >= 0)),
    CONSTRAINT ck_identity_code_rule_namespace CHECK (((code_namespace)::text = 'product_code'::text)),
    CONSTRAINT ck_identity_code_rule_revision_pos CHECK ((revision_no >= 1)),
    CONSTRAINT ck_identity_code_rule_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_code_rule_scope_object CHECK ((jsonb_typeof(scope) = 'object'::text)),
    CONSTRAINT ck_identity_code_rule_sha256_fmt CHECK (((source_workbook_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_identity_code_rule_spec_object CHECK ((jsonb_typeof(rule_spec) = 'object'::text)),
    CONSTRAINT ck_identity_code_rule_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'IN_REVIEW'::character varying, 'APPROVED'::character varying, 'ACTIVE'::character varying, 'RETIRED'::character varying, 'REJECTED'::character varying])::text[])))
);


--
-- Name: identity_customer; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_customer (
    provenance_kind character varying(8) DEFAULT 'SYS'::character varying NOT NULL,
    source_sheet character varying(100) DEFAULT ''::character varying NOT NULL,
    source_cell_ref character varying(32) DEFAULT ''::character varying NOT NULL,
    source_raw_value text,
    source_formula text,
    transform_rule_version character varying(64) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    customer_no character varying(32) NOT NULL,
    display_name_fa character varying(200) NOT NULL,
    legal_name_fa character varying(300),
    status character varying(8) DEFAULT 'ACTIVE'::character varying NOT NULL,
    default_required_quality_ref character varying(64),
    created_by_id uuid,
    import_batch_id uuid,
    staging_row_id bigint,
    updated_by_id uuid,
    CONSTRAINT ck_identity_customer_name_nonempty CHECK ((NOT ((display_name_fa)::text = ''::text))),
    CONSTRAINT ck_identity_customer_no_fmt CHECK (((NOT ((customer_no)::text = ''::text)) AND ((customer_no)::text = TRIM(BOTH FROM customer_no)))),
    CONSTRAINT ck_identity_customer_prov_imp_has_row CHECK (((NOT ((provenance_kind)::text = ANY ((ARRAY['IMP'::character varying, 'LEG'::character varying])::text[]))) OR ((import_batch_id IS NOT NULL) AND (staging_row_id IS NOT NULL)))),
    CONSTRAINT ck_identity_customer_prov_kind CHECK (((provenance_kind)::text = ANY ((ARRAY['SYS'::character varying, 'IMP'::character varying, 'LEG'::character varying, 'EXT'::character varying])::text[]))),
    CONSTRAINT ck_identity_customer_prov_raw_len CHECK (((source_raw_value IS NULL) OR (length(source_raw_value) <= 4000))),
    CONSTRAINT ck_identity_customer_prov_sys_no_batch CHECK (((NOT ((provenance_kind)::text = 'SYS'::text)) OR ((import_batch_id IS NULL) AND (staging_row_id IS NULL)))),
    CONSTRAINT ck_identity_customer_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_customer_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying])::text[])))
);


--
-- Name: identity_customer_brand; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_customer_brand (
    provenance_kind character varying(8) DEFAULT 'SYS'::character varying NOT NULL,
    source_sheet character varying(100) DEFAULT ''::character varying NOT NULL,
    source_cell_ref character varying(32) DEFAULT ''::character varying NOT NULL,
    source_raw_value text,
    source_formula text,
    transform_rule_version character varying(64) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    brand_name_fa character varying(200) NOT NULL,
    status character varying(8) DEFAULT 'ACTIVE'::character varying NOT NULL,
    created_by_id uuid,
    customer_id uuid NOT NULL,
    import_batch_id uuid,
    staging_row_id bigint,
    updated_by_id uuid,
    CONSTRAINT ck_identity_brand_name_nonempty CHECK ((NOT ((brand_name_fa)::text = ''::text))),
    CONSTRAINT ck_identity_brand_prov_imp_has_row CHECK (((NOT ((provenance_kind)::text = ANY ((ARRAY['IMP'::character varying, 'LEG'::character varying])::text[]))) OR ((import_batch_id IS NOT NULL) AND (staging_row_id IS NOT NULL)))),
    CONSTRAINT ck_identity_brand_prov_kind CHECK (((provenance_kind)::text = ANY ((ARRAY['SYS'::character varying, 'IMP'::character varying, 'LEG'::character varying, 'EXT'::character varying])::text[]))),
    CONSTRAINT ck_identity_brand_prov_raw_len CHECK (((source_raw_value IS NULL) OR (length(source_raw_value) <= 4000))),
    CONSTRAINT ck_identity_brand_prov_sys_no_batch CHECK (((NOT ((provenance_kind)::text = 'SYS'::text)) OR ((import_batch_id IS NULL) AND (staging_row_id IS NULL)))),
    CONSTRAINT ck_identity_brand_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_brand_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying])::text[])))
);


--
-- Name: identity_external_ref; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_external_ref (
    provenance_kind character varying(8) DEFAULT 'SYS'::character varying NOT NULL,
    source_sheet character varying(100) DEFAULT ''::character varying NOT NULL,
    source_cell_ref character varying(32) DEFAULT ''::character varying NOT NULL,
    source_raw_value text,
    source_formula text,
    transform_rule_version character varying(64) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    target_type character varying(16) NOT NULL,
    target_id uuid NOT NULL,
    system character varying(16) NOT NULL,
    value character varying(64) NOT NULL,
    valid_from timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    valid_to timestamp with time zone,
    created_by_id uuid,
    import_batch_id uuid,
    staging_row_id bigint,
    updated_by_id uuid,
    namespace character varying(64) NOT NULL,
    CONSTRAINT ck_identity_ext_ref_prov_imp_has_row CHECK (((NOT ((provenance_kind)::text = ANY ((ARRAY['IMP'::character varying, 'LEG'::character varying])::text[]))) OR ((import_batch_id IS NOT NULL) AND (staging_row_id IS NOT NULL)))),
    CONSTRAINT ck_identity_ext_ref_prov_kind CHECK (((provenance_kind)::text = ANY ((ARRAY['SYS'::character varying, 'IMP'::character varying, 'LEG'::character varying, 'EXT'::character varying])::text[]))),
    CONSTRAINT ck_identity_ext_ref_prov_raw_len CHECK (((source_raw_value IS NULL) OR (length(source_raw_value) <= 4000))),
    CONSTRAINT ck_identity_ext_ref_prov_sys_no_batch CHECK (((NOT ((provenance_kind)::text = 'SYS'::text)) OR ((import_batch_id IS NULL) AND (staging_row_id IS NULL)))),
    CONSTRAINT ck_identity_ext_ref_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_ext_ref_system CHECK (((system)::text = ANY ((ARRAY['RAHKARAN'::character varying, 'CUSTOMER'::character varying, 'LEGACY_PLANNING'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT ck_identity_ext_ref_target CHECK (((target_type)::text = ANY ((ARRAY['customer'::character varying, 'product'::character varying, 'style'::character varying, 'customer_order'::character varying, 'order_line'::character varying, 'serial'::character varying])::text[]))),
    CONSTRAINT ck_identity_ext_ref_validity CHECK (((valid_to IS NULL) OR (valid_to > valid_from))),
    CONSTRAINT ck_identity_ext_ref_value_nonempty CHECK ((NOT ((value)::text = ''::text)))
);


--
-- Name: identity_external_ref_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_external_ref_type (
    key character varying(64) NOT NULL,
    label_fa character varying(200) NOT NULL,
    status character varying(8) DEFAULT 'ACTIVE'::character varying NOT NULL,
    decision_id character varying(7) DEFAULT ''::character varying NOT NULL,
    provenance character varying(16) DEFAULT 'SYS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    created_by_id uuid,
    updated_by_id uuid,
    CONSTRAINT ck_identity_ext_ref_type_decision_fmt CHECK ((((decision_id)::text = ''::text) OR ((decision_id)::text ~ '^DEC-[0-9]{3}$'::text))),
    CONSTRAINT ck_identity_ext_ref_type_key_fmt CHECK (((key)::text ~ '^[a-z][a-z0-9_]{2,63}$'::text)),
    CONSTRAINT ck_identity_ext_ref_type_label_nonempty CHECK ((NOT ((label_fa)::text = ''::text))),
    CONSTRAINT ck_identity_ext_ref_type_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'MIGRATION_SEED'::character varying])::text[]))),
    CONSTRAINT ck_identity_ext_ref_type_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_ext_ref_type_seed_has_decision CHECK (((NOT ((provenance)::text = 'MIGRATION_SEED'::text)) OR (NOT ((decision_id)::text = ''::text)))),
    CONSTRAINT ck_identity_ext_ref_type_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'INACTIVE'::character varying])::text[])))
);


--
-- Name: identity_historical_order_record; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_historical_order_record (
    provenance_kind character varying(8) DEFAULT 'SYS'::character varying NOT NULL,
    source_sheet character varying(100) DEFAULT ''::character varying NOT NULL,
    source_cell_ref character varying(32) DEFAULT ''::character varying NOT NULL,
    source_raw_value text,
    source_formula text,
    transform_rule_version character varying(64) DEFAULT ''::character varying NOT NULL,
    id uuid NOT NULL,
    legacy_order_ref character varying(64) DEFAULT ''::character varying NOT NULL,
    legacy_serial_text character varying(32),
    legacy_serial_value bigint,
    legacy_serial_duplicate boolean DEFAULT false NOT NULL,
    legacy_product_code_raw text,
    normalised_product_code character varying(14),
    code_flag character varying(8) NOT NULL,
    payload jsonb NOT NULL,
    match_status character varying(12) DEFAULT 'UNMATCHED'::character varying NOT NULL,
    matched_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    import_batch_id uuid,
    matched_by_id uuid,
    staging_row_id bigint,
    matched_product_code_id uuid,
    matched_style_id uuid,
    CONSTRAINT ck_identity_historical_absent_has_none CHECK (((NOT ((code_flag)::text = 'ABSENT'::text)) OR ((legacy_product_code_raw IS NULL) AND (normalised_product_code IS NULL)))),
    CONSTRAINT ck_identity_historical_code_flag CHECK (((code_flag)::text = ANY ((ARRAY['OK'::character varying, 'DISPUTED'::character varying, 'ABSENT'::character varying])::text[]))),
    CONSTRAINT ck_identity_historical_code_fmt CHECK (((normalised_product_code)::text ~ '^[0-9]{14}$'::text)),
    CONSTRAINT ck_identity_historical_confirmed_has_style CHECK (((NOT ((match_status)::text = 'CONFIRMED'::text)) OR (matched_style_id IS NOT NULL))),
    CONSTRAINT ck_identity_historical_decided_has_actor CHECK (((NOT ((match_status)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'REJECTED'::character varying])::text[]))) OR ((matched_at IS NOT NULL) AND (matched_by_id IS NOT NULL)))),
    CONSTRAINT ck_identity_historical_disputed_has_raw CHECK (((NOT ((code_flag)::text = 'DISPUTED'::text)) OR (legacy_product_code_raw IS NOT NULL))),
    CONSTRAINT ck_identity_historical_is_legacy CHECK (((provenance_kind)::text = 'LEG'::text)),
    CONSTRAINT ck_identity_historical_match_status CHECK (((match_status)::text = ANY ((ARRAY['UNMATCHED'::character varying, 'SUGGESTED'::character varying, 'CONFIRMED'::character varying, 'REJECTED'::character varying])::text[]))),
    CONSTRAINT ck_identity_historical_ok_has_code CHECK (((NOT ((code_flag)::text = 'OK'::text)) OR (normalised_product_code IS NOT NULL))),
    CONSTRAINT ck_identity_historical_payload_object CHECK ((jsonb_typeof(payload) = 'object'::text)),
    CONSTRAINT ck_identity_historical_plain_serial_has_value CHECK (((legacy_serial_text IS NULL) OR (NOT (((legacy_serial_text)::text ~ '^[1-9][0-9]{0,17}$'::text) AND (legacy_serial_text IS NOT NULL))) OR (legacy_serial_value IS NOT NULL))),
    CONSTRAINT ck_identity_historical_prov_imp_has_row CHECK (((NOT ((provenance_kind)::text = ANY ((ARRAY['IMP'::character varying, 'LEG'::character varying])::text[]))) OR ((import_batch_id IS NOT NULL) AND (staging_row_id IS NOT NULL)))),
    CONSTRAINT ck_identity_historical_prov_kind CHECK (((provenance_kind)::text = ANY ((ARRAY['SYS'::character varying, 'IMP'::character varying, 'LEG'::character varying, 'EXT'::character varying])::text[]))),
    CONSTRAINT ck_identity_historical_prov_raw_len CHECK (((source_raw_value IS NULL) OR (length(source_raw_value) <= 4000))),
    CONSTRAINT ck_identity_historical_prov_sys_no_batch CHECK (((NOT ((provenance_kind)::text = 'SYS'::text)) OR ((import_batch_id IS NULL) AND (staging_row_id IS NULL)))),
    CONSTRAINT ck_identity_historical_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_historical_serial_value_is_text CHECK (((legacy_serial_value IS NULL) OR (((legacy_serial_text)::text = ((legacy_serial_value)::character varying)::text) AND (legacy_serial_text IS NOT NULL))))
);


--
-- Name: identity_product; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_product (
    provenance_kind character varying(8) DEFAULT 'SYS'::character varying NOT NULL,
    source_sheet character varying(100) DEFAULT ''::character varying NOT NULL,
    source_cell_ref character varying(32) DEFAULT ''::character varying NOT NULL,
    source_raw_value text,
    source_formula text,
    transform_rule_version character varying(64) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    product_no character varying(4) NOT NULL,
    name_fa character varying(200) NOT NULL,
    buckle_type_code character varying(2),
    belt_width_code character varying(2),
    status character varying(8) DEFAULT 'DRAFT'::character varying NOT NULL,
    created_by_id uuid,
    import_batch_id uuid,
    staging_row_id bigint,
    updated_by_id uuid,
    product_type_id uuid NOT NULL,
    CONSTRAINT ck_identity_product_belt_no CHECK ((((belt_width_code IS NULL) AND (buckle_type_code IS NULL)) OR ((belt_width_code IS NOT NULL) AND ((belt_width_code)::text ~ '^[0-9]{2}$'::text) AND (buckle_type_code IS NOT NULL) AND ((buckle_type_code)::text ~ '^[0-9]{2}$'::text) AND ((product_no)::text = ((COALESCE(buckle_type_code, ''::character varying))::text || (COALESCE(belt_width_code, ''::character varying))::text))))),
    CONSTRAINT ck_identity_product_name_nonempty CHECK ((NOT ((name_fa)::text = ''::text))),
    CONSTRAINT ck_identity_product_no_fmt CHECK (((product_no)::text ~ '^[0-9]{4}$'::text)),
    CONSTRAINT ck_identity_product_prov_imp_has_row CHECK (((NOT ((provenance_kind)::text = ANY ((ARRAY['IMP'::character varying, 'LEG'::character varying])::text[]))) OR ((import_batch_id IS NOT NULL) AND (staging_row_id IS NOT NULL)))),
    CONSTRAINT ck_identity_product_prov_kind CHECK (((provenance_kind)::text = ANY ((ARRAY['SYS'::character varying, 'IMP'::character varying, 'LEG'::character varying, 'EXT'::character varying])::text[]))),
    CONSTRAINT ck_identity_product_prov_raw_len CHECK (((source_raw_value IS NULL) OR (length(source_raw_value) <= 4000))),
    CONSTRAINT ck_identity_product_prov_sys_no_batch CHECK (((NOT ((provenance_kind)::text = 'SYS'::text)) OR ((import_batch_id IS NULL) AND (staging_row_id IS NULL)))),
    CONSTRAINT ck_identity_product_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_product_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'ACTIVE'::character varying, 'RETIRED'::character varying])::text[])))
);


--
-- Name: identity_product_class; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_product_class (
    provenance_kind character varying(8) DEFAULT 'SYS'::character varying NOT NULL,
    source_sheet character varying(100) DEFAULT ''::character varying NOT NULL,
    source_cell_ref character varying(32) DEFAULT ''::character varying NOT NULL,
    source_raw_value text,
    source_formula text,
    transform_rule_version character varying(64) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    level_key character varying(16) NOT NULL,
    segment_value character varying(2) NOT NULL,
    label_fa character varying(200) NOT NULL,
    product_no_scheme character varying(24),
    status character varying(8) DEFAULT 'DRAFT'::character varying NOT NULL,
    created_by_id uuid,
    import_batch_id uuid,
    parent_id uuid,
    staging_row_id bigint,
    updated_by_id uuid,
    uom_code character varying(8),
    CONSTRAINT ck_identity_class_label_nonempty CHECK ((NOT ((label_fa)::text = ''::text))),
    CONSTRAINT ck_identity_class_level CHECK (((level_key)::text = ANY ((ARRAY['product_type'::character varying, 'category'::character varying])::text[]))),
    CONSTRAINT ck_identity_class_not_own_parent CHECK ((NOT ((parent_id = id) AND (parent_id IS NOT NULL)))),
    CONSTRAINT ck_identity_class_parent_by_level CHECK (((((level_key)::text = 'product_type'::text) AND (parent_id IS NULL)) OR (((level_key)::text = 'category'::text) AND (parent_id IS NOT NULL)))),
    CONSTRAINT ck_identity_class_prov_imp_has_row CHECK (((NOT ((provenance_kind)::text = ANY ((ARRAY['IMP'::character varying, 'LEG'::character varying])::text[]))) OR ((import_batch_id IS NOT NULL) AND (staging_row_id IS NOT NULL)))),
    CONSTRAINT ck_identity_class_prov_kind CHECK (((provenance_kind)::text = ANY ((ARRAY['SYS'::character varying, 'IMP'::character varying, 'LEG'::character varying, 'EXT'::character varying])::text[]))),
    CONSTRAINT ck_identity_class_prov_raw_len CHECK (((source_raw_value IS NULL) OR (length(source_raw_value) <= 4000))),
    CONSTRAINT ck_identity_class_prov_sys_no_batch CHECK (((NOT ((provenance_kind)::text = 'SYS'::text)) OR ((import_batch_id IS NULL) AND (staging_row_id IS NULL)))),
    CONSTRAINT ck_identity_class_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_class_scheme CHECK (((product_no_scheme IS NULL) OR ((product_no_scheme)::text = ANY ((ARRAY['SEQUENTIAL_PER_TYPE'::character varying, 'BELT_BUCKLE_WIDTH'::character varying])::text[])))),
    CONSTRAINT ck_identity_class_segment_fmt CHECK (((segment_value)::text ~ '^[0-9]{2}$'::text)),
    CONSTRAINT ck_identity_class_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'ACTIVE'::character varying, 'RETIRED'::character varying])::text[]))),
    CONSTRAINT ck_identity_class_type_attributes CHECK (((((level_key)::text = 'product_type'::text) AND (product_no_scheme IS NOT NULL) AND (uom_code IS NOT NULL)) OR (((level_key)::text = 'category'::text) AND (product_no_scheme IS NULL) AND (uom_code IS NULL))))
);


--
-- Name: identity_product_code; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_product_code (
    provenance_kind character varying(8) DEFAULT 'SYS'::character varying NOT NULL,
    source_sheet character varying(100) DEFAULT ''::character varying NOT NULL,
    source_cell_ref character varying(32) DEFAULT ''::character varying NOT NULL,
    source_raw_value text,
    source_formula text,
    transform_rule_version character varying(64) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    code character varying(14) NOT NULL,
    code_namespace character varying(16) DEFAULT 'product_code'::character varying NOT NULL,
    status character varying(12) NOT NULL,
    erp_status character varying(12) DEFAULT 'ERP_PENDING'::character varying NOT NULL,
    issue_idempotency_key uuid,
    issued_at timestamp with time zone,
    created_by_id uuid,
    erp_seen_batch_id uuid,
    import_batch_id uuid,
    issued_by_id uuid,
    rule_revision_id uuid,
    staging_row_id bigint,
    updated_by_id uuid,
    style_id uuid,
    CONSTRAINT ck_identity_product_code_active_matched CHECK (((NOT ((status)::text = 'ACTIVE'::text)) OR ((erp_status)::text = 'ERP_MATCHED'::text))),
    CONSTRAINT ck_identity_product_code_erp_status CHECK (((erp_status)::text = ANY ((ARRAY['ERP_PENDING'::character varying, 'ERP_MATCHED'::character varying, 'ERP_MISSING'::character varying])::text[]))),
    CONSTRAINT ck_identity_product_code_fmt CHECK (((code)::text ~ '^[0-9]{14}$'::text)),
    CONSTRAINT ck_identity_product_code_matched_has_batch CHECK (((NOT ((erp_status)::text = 'ERP_MATCHED'::text)) OR (erp_seen_batch_id IS NOT NULL))),
    CONSTRAINT ck_identity_product_code_namespace CHECK (((code_namespace)::text = 'product_code'::text)),
    CONSTRAINT ck_identity_product_code_prov_imp_has_row CHECK (((NOT ((provenance_kind)::text = ANY ((ARRAY['IMP'::character varying, 'LEG'::character varying])::text[]))) OR ((import_batch_id IS NOT NULL) AND (staging_row_id IS NOT NULL)))),
    CONSTRAINT ck_identity_product_code_prov_kind CHECK (((provenance_kind)::text = ANY ((ARRAY['SYS'::character varying, 'IMP'::character varying, 'LEG'::character varying, 'EXT'::character varying])::text[]))),
    CONSTRAINT ck_identity_product_code_prov_raw_len CHECK (((source_raw_value IS NULL) OR (length(source_raw_value) <= 4000))),
    CONSTRAINT ck_identity_product_code_prov_sys_no_batch CHECK (((NOT ((provenance_kind)::text = 'SYS'::text)) OR ((import_batch_id IS NULL) AND (staging_row_id IS NULL)))),
    CONSTRAINT ck_identity_product_code_reserved_pending CHECK (((NOT ((status)::text = 'RESERVED'::text)) OR ((erp_status)::text = 'ERP_PENDING'::text))),
    CONSTRAINT ck_identity_product_code_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_product_code_status CHECK (((status)::text = ANY ((ARRAY['RESERVED'::character varying, 'ACTIVE'::character varying, 'RETIRED'::character varying, 'DISPUTED'::character varying])::text[]))),
    CONSTRAINT ck_identity_product_code_sys_issued CHECK (((NOT ((provenance_kind)::text = 'SYS'::text)) OR (((code)::text ~~ '02%'::text) AND (issue_idempotency_key IS NOT NULL) AND (issued_at IS NOT NULL) AND (issued_by_id IS NOT NULL) AND (rule_revision_id IS NOT NULL) AND (style_id IS NOT NULL)))),
    CONSTRAINT ck_identity_product_code_sys_no_style_0000 CHECK (((NOT ((provenance_kind)::text = 'SYS'::text)) OR (NOT ((code)::text ~~ '%0000'::text))))
);


--
-- Name: identity_serial; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_serial (
    id uuid NOT NULL,
    serial_number character varying(32) NOT NULL,
    serial_value bigint NOT NULL,
    status character varying(20) DEFAULT 'ALLOCATED'::character varying NOT NULL,
    allocation_idempotency_key uuid NOT NULL,
    allocated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    cancelled_at timestamp with time zone,
    cancel_reason character varying(500),
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    allocated_by_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    product_code_id uuid,
    serial_counter_id uuid NOT NULL,
    style_id uuid NOT NULL,
    style_revision_id uuid NOT NULL,
    CONSTRAINT ck_identity_serial_cancel_has_reason CHECK (((NOT ((status)::text = 'CANCELLED'::text)) OR ((cancel_reason IS NOT NULL) AND (cancelled_at IS NOT NULL) AND (length((cancel_reason)::text) >= 3)))),
    CONSTRAINT ck_identity_serial_number_fmt CHECK (((serial_number)::text ~ '^[1-9][0-9]*$'::text)),
    CONSTRAINT ck_identity_serial_number_is_value CHECK (((serial_number)::text = ((serial_value)::character varying)::text)),
    CONSTRAINT ck_identity_serial_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_serial_status CHECK (((status)::text = ANY ((ARRAY['ALLOCATED'::character varying, 'CANCELLED'::character varying, 'IN_PRODUCTION'::character varying, 'PARTIALLY_DELIVERED'::character varying, 'DELIVERED'::character varying, 'CLOSED'::character varying])::text[])))
);


--
-- Name: identity_serial_counter; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_serial_counter (
    id uuid NOT NULL,
    namespace_key character varying(64) NOT NULL,
    start_value bigint NOT NULL,
    next_value bigint NOT NULL,
    legacy_max_exclusive bigint NOT NULL,
    number_pattern character varying(64) NOT NULL,
    decision_id character varying(7) NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    CONSTRAINT ck_identity_serial_counter_decision CHECK (((decision_id)::text ~ '^DEC-[0-9]{3}$'::text)),
    CONSTRAINT ck_identity_serial_counter_legacy_below_start CHECK ((legacy_max_exclusive < start_value)),
    CONSTRAINT ck_identity_serial_counter_next_ge_start CHECK ((next_value >= start_value)),
    CONSTRAINT ck_identity_serial_counter_pattern CHECK (((number_pattern)::text = '^[1-9][0-9]*$'::text)),
    CONSTRAINT ck_identity_serial_counter_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_serial_counter_single_ns CHECK (((namespace_key)::text = 'factory_serial'::text)),
    CONSTRAINT ck_identity_serial_counter_start_pos CHECK ((start_value >= 1))
);


--
-- Name: identity_serial_snapshot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_serial_snapshot (
    id uuid NOT NULL,
    version integer NOT NULL,
    snapshot jsonb NOT NULL,
    reason character varying(20) NOT NULL,
    order_version integer NOT NULL,
    change_request_id uuid,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    created_by_id uuid NOT NULL,
    serial_id uuid NOT NULL,
    CONSTRAINT ck_identity_serial_snapshot_change_has_cr CHECK (((NOT ((reason)::text = 'CHANGE_APPLIED'::text)) OR (change_request_id IS NOT NULL))),
    CONSTRAINT ck_identity_serial_snapshot_image_object CHECK ((jsonb_typeof(snapshot) = 'object'::text)),
    CONSTRAINT ck_identity_serial_snapshot_order_version CHECK ((order_version >= 1)),
    CONSTRAINT ck_identity_serial_snapshot_reason CHECK (((reason)::text = ANY ((ARRAY['ALLOCATED'::character varying, 'CHANGE_APPLIED'::character varying, 'TECH_PACKAGE_LINKED'::character varying])::text[]))),
    CONSTRAINT ck_identity_serial_snapshot_v1_allocated CHECK (((((reason)::text = 'ALLOCATED'::text) AND (version = 1)) OR ((version > 1) AND (NOT ((reason)::text = 'ALLOCATED'::text))))),
    CONSTRAINT ck_identity_serial_snapshot_version_pos CHECK ((version >= 1))
);


--
-- Name: identity_style; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_style (
    provenance_kind character varying(8) DEFAULT 'SYS'::character varying NOT NULL,
    source_sheet character varying(100) DEFAULT ''::character varying NOT NULL,
    source_cell_ref character varying(32) DEFAULT ''::character varying NOT NULL,
    source_raw_value text,
    source_formula text,
    transform_rule_version character varying(64) DEFAULT ''::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    style_no character varying(4) NOT NULL,
    name_fa character varying(200) NOT NULL,
    status character varying(8) DEFAULT 'DRAFT'::character varying NOT NULL,
    category_id uuid NOT NULL,
    created_by_id uuid,
    import_batch_id uuid,
    product_id uuid NOT NULL,
    staging_row_id bigint,
    updated_by_id uuid,
    CONSTRAINT ck_identity_style_name_nonempty CHECK ((NOT ((name_fa)::text = ''::text))),
    CONSTRAINT ck_identity_style_no_fmt CHECK ((((style_no)::text ~ '^[0-9]{4}$'::text) AND ((NOT ((style_no)::text = '0000'::text)) OR ((provenance_kind)::text = ANY ((ARRAY['IMP'::character varying, 'LEG'::character varying])::text[]))))),
    CONSTRAINT ck_identity_style_prov_imp_has_row CHECK (((NOT ((provenance_kind)::text = ANY ((ARRAY['IMP'::character varying, 'LEG'::character varying])::text[]))) OR ((import_batch_id IS NOT NULL) AND (staging_row_id IS NOT NULL)))),
    CONSTRAINT ck_identity_style_prov_kind CHECK (((provenance_kind)::text = ANY ((ARRAY['SYS'::character varying, 'IMP'::character varying, 'LEG'::character varying, 'EXT'::character varying])::text[]))),
    CONSTRAINT ck_identity_style_prov_raw_len CHECK (((source_raw_value IS NULL) OR (length(source_raw_value) <= 4000))),
    CONSTRAINT ck_identity_style_prov_sys_no_batch CHECK (((NOT ((provenance_kind)::text = 'SYS'::text)) OR ((import_batch_id IS NULL) AND (staging_row_id IS NULL)))),
    CONSTRAINT ck_identity_style_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_style_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'ACTIVE'::character varying, 'RETIRED'::character varying])::text[])))
);


--
-- Name: identity_style_revision; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_style_revision (
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    row_version bigint DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    revision_no integer NOT NULL,
    attributes jsonb NOT NULL,
    status character varying(12) DEFAULT 'DRAFT'::character varying NOT NULL,
    technical_package_revision_id uuid,
    created_by_id uuid,
    style_id uuid NOT NULL,
    updated_by_id uuid,
    CONSTRAINT ck_identity_style_revision_attrs_object CHECK ((jsonb_typeof(attributes) = 'object'::text)),
    CONSTRAINT ck_identity_style_revision_no_pos CHECK ((revision_no >= 1)),
    CONSTRAINT ck_identity_style_revision_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_identity_style_revision_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'ACTIVE'::character varying, 'SUPERSEDED'::character varying])::text[])))
);


--
-- Name: identity_unit_of_measure; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_unit_of_measure (
    code character varying(8) NOT NULL,
    label_fa character varying(50) NOT NULL,
    decision_id character varying(7) NOT NULL,
    provenance character varying(16) DEFAULT 'SYS'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT statement_timestamp() NOT NULL,
    CONSTRAINT ck_identity_uom_code_fmt CHECK (((code)::text ~ '^[A-Z][A-Z_]{1,7}$'::text)),
    CONSTRAINT ck_identity_uom_decision_fmt CHECK (((decision_id)::text ~ '^DEC-[0-9]{3}$'::text)),
    CONSTRAINT ck_identity_uom_label_nonempty CHECK ((NOT ((label_fa)::text = ''::text))),
    CONSTRAINT ck_identity_uom_provenance CHECK (((provenance)::text = ANY ((ARRAY['SYS'::character varying, 'MIGRATION_SEED'::character varying])::text[])))
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
    bootstrap_self_approval boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_approval_request_bootstrap_scope CHECK (((NOT bootstrap_self_approval) OR (((action)::text = 'platform.identity.assignment.grant'::text) AND ((resource_type)::text = 'role_assignment'::text) AND ((status)::text = 'APPROVED'::text)))),
    CONSTRAINT ck_approval_request_closed_at CHECK ((((closed_at IS NULL) AND ((status)::text = 'PENDING'::text)) OR ((NOT ((status)::text = 'PENDING'::text)) AND (closed_at IS NOT NULL)))),
    CONSTRAINT ck_approval_request_decided_has_decider CHECK (((NOT ((status)::text = ANY ((ARRAY['APPROVED'::character varying, 'REJECTED'::character varying])::text[]))) OR (decided_by_id IS NOT NULL))),
    CONSTRAINT ck_approval_request_expiry_after_request CHECK ((expires_at > requested_at)),
    CONSTRAINT ck_approval_request_maker_checker CHECK (((decided_by_id IS NULL) OR (NOT ((decided_by_id = requested_by_id) AND (decided_by_id IS NOT NULL))) OR (bootstrap_self_approval AND ((status)::text = 'APPROVED'::text)))),
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
    CONSTRAINT ck_login_attempt_outcome CHECK (((outcome)::text = ANY ((ARRAY['OK'::character varying, 'INVALID_CREDENTIALS'::character varying, 'LOCKED'::character varying, 'DISABLED'::character varying, 'ONE_TIME_EXPIRED'::character varying, 'NETWORK_POLICY_DENIED'::character varying, 'MFA_OK'::character varying, 'MFA_FAILED'::character varying, 'RECOVERY_CODE_USED'::character varying, 'MFA_ENROLMENT_REQUIRED'::character varying])::text[]))),
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
-- Name: platform_number_counter; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_number_counter (
    kind character varying(16) NOT NULL,
    jalali_year integer NOT NULL,
    last_value bigint NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_number_counter_kind CHECK (((kind)::text = ANY ((ARRAY['customer'::character varying, 'order'::character varying, 'change_request'::character varying])::text[]))),
    CONSTRAINT ck_number_counter_value CHECK ((last_value >= 1)),
    CONSTRAINT ck_number_counter_year CHECK (((jalali_year >= 1300) AND (jalali_year <= 1999)))
);


--
-- Name: TABLE platform_number_counter; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.platform_number_counter IS 'PHASE_02 technical numbers CU-/SO-/CR-<jalali year>-<n> (DEC-058 amendment 2026-11-14); forward only';


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
    build_commit character varying(12) DEFAULT ''::character varying NOT NULL,
    producer character varying(100) DEFAULT ''::character varying NOT NULL,
    schema_migration character varying(100) DEFAULT ''::character varying NOT NULL,
    discarded_at timestamp with time zone,
    CONSTRAINT ck_outbox_event_acked_has_ts CHECK (((NOT ((delivery_status)::text = 'ACKED'::text)) OR (acked_at IS NOT NULL))),
    CONSTRAINT ck_outbox_event_actor_id_for_user CHECK (((NOT ((actor_type)::text = 'USER'::text)) OR (actor_id IS NOT NULL))),
    CONSTRAINT ck_outbox_event_actor_type CHECK (((actor_type)::text = ANY ((ARRAY['USER'::character varying, 'SYSTEM'::character varying, 'ANONYMOUS'::character varying])::text[]))),
    CONSTRAINT ck_outbox_event_agg_version_nonneg CHECK ((aggregate_version >= 0)),
    CONSTRAINT ck_outbox_event_attempts_nonneg CHECK ((attempts >= 0)),
    CONSTRAINT ck_outbox_event_build_commit_fmt CHECK (((build_commit)::text ~ '^([0-9a-f]{7,12})?$'::text)),
    CONSTRAINT ck_outbox_event_delivery_status CHECK (((delivery_status)::text = ANY ((ARRAY['PENDING'::character varying, 'DISPATCHED'::character varying, 'ACKED'::character varying, 'FAILED'::character varying, 'DEAD_LETTER'::character varying, 'DISCARDED'::character varying])::text[]))),
    CONSTRAINT ck_outbox_event_discarded_has_ts CHECK (((NOT ((delivery_status)::text = 'DISCARDED'::text)) OR (discarded_at IS NOT NULL))),
    CONSTRAINT ck_outbox_event_dispatched_has_ts CHECK (((NOT ((delivery_status)::text = 'DISPATCHED'::text)) OR (dispatched_at IS NOT NULL))),
    CONSTRAINT ck_outbox_event_payload_object CHECK ((jsonb_typeof(payload) = 'object'::text)),
    CONSTRAINT ck_outbox_event_producer_fmt CHECK ((((producer)::text = ''::text) OR ((producer)::text ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$'::text))),
    CONSTRAINT ck_outbox_event_row_version_pos CHECK ((row_version >= 1)),
    CONSTRAINT ck_outbox_event_schema_migration_fmt CHECK ((((schema_migration)::text = ''::text) OR ((schema_migration)::text ~ '^[a-z][a-z0-9_]*\.[0-9]{4}_[a-z0-9_]+$'::text))),
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
-- Name: commercial_customer_order_line commercial_customer_order_line_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT commercial_customer_order_line_pkey PRIMARY KEY (id);


--
-- Name: commercial_customer_order commercial_customer_order_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order
    ADD CONSTRAINT commercial_customer_order_pkey PRIMARY KEY (id);


--
-- Name: commercial_customer_order_version commercial_customer_order_version_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_version
    ADD CONSTRAINT commercial_customer_order_version_pkey PRIMARY KEY (id);


--
-- Name: commercial_order_change_request commercial_order_change_request_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_change_request
    ADD CONSTRAINT commercial_order_change_request_pkey PRIMARY KEY (id);


--
-- Name: commercial_order_type commercial_order_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_type
    ADD CONSTRAINT commercial_order_type_pkey PRIMARY KEY (code);


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
-- Name: identity_code_rule_golden_case identity_code_rule_golden_case_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_golden_case
    ADD CONSTRAINT identity_code_rule_golden_case_pkey PRIMARY KEY (id);


--
-- Name: identity_code_rule_revision identity_code_rule_revision_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_revision
    ADD CONSTRAINT identity_code_rule_revision_pkey PRIMARY KEY (id);


--
-- Name: identity_customer_brand identity_customer_brand_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer_brand
    ADD CONSTRAINT identity_customer_brand_pkey PRIMARY KEY (id);


--
-- Name: identity_customer identity_customer_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer
    ADD CONSTRAINT identity_customer_pkey PRIMARY KEY (id);


--
-- Name: identity_external_ref identity_external_ref_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_external_ref
    ADD CONSTRAINT identity_external_ref_pkey PRIMARY KEY (id);


--
-- Name: identity_external_ref_type identity_external_ref_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_external_ref_type
    ADD CONSTRAINT identity_external_ref_type_pkey PRIMARY KEY (key);


--
-- Name: identity_historical_order_record identity_historical_order_record_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_historical_order_record
    ADD CONSTRAINT identity_historical_order_record_pkey PRIMARY KEY (id);


--
-- Name: identity_product_class identity_product_class_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_class
    ADD CONSTRAINT identity_product_class_pkey PRIMARY KEY (id);


--
-- Name: identity_product_code identity_product_code_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT identity_product_code_pkey PRIMARY KEY (id);


--
-- Name: identity_product identity_product_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product
    ADD CONSTRAINT identity_product_pkey PRIMARY KEY (id);


--
-- Name: identity_serial_counter identity_serial_counter_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial_counter
    ADD CONSTRAINT identity_serial_counter_pkey PRIMARY KEY (id);


--
-- Name: identity_serial identity_serial_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial
    ADD CONSTRAINT identity_serial_pkey PRIMARY KEY (id);


--
-- Name: identity_serial_snapshot identity_serial_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial_snapshot
    ADD CONSTRAINT identity_serial_snapshot_pkey PRIMARY KEY (id);


--
-- Name: identity_style identity_style_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style
    ADD CONSTRAINT identity_style_pkey PRIMARY KEY (id);


--
-- Name: identity_style_revision identity_style_revision_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style_revision
    ADD CONSTRAINT identity_style_revision_pkey PRIMARY KEY (id);


--
-- Name: identity_unit_of_measure identity_unit_of_measure_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_unit_of_measure
    ADD CONSTRAINT identity_unit_of_measure_pkey PRIMARY KEY (code);


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
-- Name: platform_number_counter platform_number_counter_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_number_counter
    ADD CONSTRAINT platform_number_counter_pkey PRIMARY KEY (kind, jalali_year);


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
-- Name: commercial_order_change_request uq_commercial_cr_request_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_change_request
    ADD CONSTRAINT uq_commercial_cr_request_no UNIQUE (request_no);


--
-- Name: commercial_customer_order_line uq_commercial_line_order_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT uq_commercial_line_order_no UNIQUE (order_id, line_no);


--
-- Name: commercial_customer_order_line uq_commercial_line_serial; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT uq_commercial_line_serial UNIQUE (serial_id);


--
-- Name: commercial_customer_order uq_commercial_order_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order
    ADD CONSTRAINT uq_commercial_order_no UNIQUE (order_no);


--
-- Name: commercial_customer_order_version uq_commercial_order_version_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_version
    ADD CONSTRAINT uq_commercial_order_version_no UNIQUE (order_id, version);


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
-- Name: identity_code_rule_revision uq_identity_code_rule_revision_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_revision
    ADD CONSTRAINT uq_identity_code_rule_revision_no UNIQUE (code_namespace, revision_no);


--
-- Name: identity_customer uq_identity_customer_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer
    ADD CONSTRAINT uq_identity_customer_no UNIQUE (customer_no);


--
-- Name: identity_external_ref uq_identity_ext_ref_target_value; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_external_ref
    ADD CONSTRAINT uq_identity_ext_ref_target_value UNIQUE (system, namespace, value, target_type, target_id);


--
-- Name: identity_code_rule_golden_case uq_identity_golden_case_source; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_golden_case
    ADD CONSTRAINT uq_identity_golden_case_source UNIQUE (rule_revision_id, source_sheet, source_cell_ref);


--
-- Name: identity_historical_order_record uq_identity_historical_staging_row; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_historical_order_record
    ADD CONSTRAINT uq_identity_historical_staging_row UNIQUE (staging_row_id);


--
-- Name: identity_product_code uq_identity_product_code_issue_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT uq_identity_product_code_issue_key UNIQUE (issue_idempotency_key);


--
-- Name: identity_product_code uq_identity_product_code_ns_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT uq_identity_product_code_ns_code UNIQUE (code_namespace, code);


--
-- Name: identity_product uq_identity_product_type_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product
    ADD CONSTRAINT uq_identity_product_type_no UNIQUE (product_type_id, product_no);


--
-- Name: identity_serial uq_identity_serial_allocation_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial
    ADD CONSTRAINT uq_identity_serial_allocation_key UNIQUE (allocation_idempotency_key);


--
-- Name: identity_serial_counter uq_identity_serial_counter_namespace; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial_counter
    ADD CONSTRAINT uq_identity_serial_counter_namespace UNIQUE (namespace_key);


--
-- Name: identity_serial uq_identity_serial_number; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial
    ADD CONSTRAINT uq_identity_serial_number UNIQUE (serial_counter_id, serial_number);


--
-- Name: identity_serial_snapshot uq_identity_serial_snapshot_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial_snapshot
    ADD CONSTRAINT uq_identity_serial_snapshot_version UNIQUE (serial_id, version);


--
-- Name: identity_serial uq_identity_serial_value; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial
    ADD CONSTRAINT uq_identity_serial_value UNIQUE (serial_counter_id, serial_value);


--
-- Name: identity_style uq_identity_style_product_category_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style
    ADD CONSTRAINT uq_identity_style_product_category_no UNIQUE (product_id, category_id, style_no);


--
-- Name: identity_style_revision uq_identity_style_revision_no; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style_revision
    ADD CONSTRAINT uq_identity_style_revision_no UNIQUE (style_id, revision_no);


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
-- Name: ix_ccr_applied_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ccr_applied_by ON public.commercial_order_change_request USING btree (applied_by_id);


--
-- Name: ix_ccr_approval; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ccr_approval ON public.commercial_order_change_request USING btree (approval_id);


--
-- Name: ix_ccr_decided_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ccr_decided_by ON public.commercial_order_change_request USING btree (decided_by_id);


--
-- Name: ix_ccr_order_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ccr_order_status ON public.commercial_order_change_request USING btree (order_id, status);


--
-- Name: ix_ccr_planning_approval; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ccr_planning_approval ON public.commercial_order_change_request USING btree (planning_approval_id);


--
-- Name: ix_ccr_planning_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ccr_planning_by ON public.commercial_order_change_request USING btree (planning_approved_by_id);


--
-- Name: ix_ccr_planning_rejected_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ccr_planning_rejected_by ON public.commercial_order_change_request USING btree (planning_rejected_by_id);


--
-- Name: ix_ccr_requested_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ccr_requested_by ON public.commercial_order_change_request USING btree (requested_by_id);


--
-- Name: ix_clin_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clin_created_by ON public.commercial_customer_order_line USING btree (created_by_id);


--
-- Name: ix_clin_product_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clin_product_code ON public.commercial_customer_order_line USING btree (product_code_id);


--
-- Name: ix_clin_style; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clin_style ON public.commercial_customer_order_line USING btree (style_id);


--
-- Name: ix_clin_style_revision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clin_style_revision ON public.commercial_customer_order_line USING btree (style_revision_id);


--
-- Name: ix_clin_uom; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clin_uom ON public.commercial_customer_order_line USING btree (uom_code);


--
-- Name: ix_clin_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clin_updated_by ON public.commercial_customer_order_line USING btree (updated_by_id);


--
-- Name: ix_commercial_order_type__code_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_commercial_order_type__code_like ON public.commercial_order_type USING btree (code varchar_pattern_ops);


--
-- Name: INDEX ix_commercial_order_type__code_like; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX public.ix_commercial_order_type__code_like IS 'django-name:commercial_order_type_code_e852cb30_like';


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
-- Name: ix_cord_brand; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cord_brand ON public.commercial_customer_order USING btree (brand_id);


--
-- Name: ix_cord_confirmed_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cord_confirmed_by ON public.commercial_customer_order USING btree (confirmed_by_id);


--
-- Name: ix_cord_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cord_created_by ON public.commercial_customer_order USING btree (created_by_id);


--
-- Name: ix_cord_customer_po; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cord_customer_po ON public.commercial_customer_order USING btree (customer_id, external_po_number);


--
-- Name: ix_cord_released_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cord_released_by ON public.commercial_customer_order USING btree (released_by_id);


--
-- Name: ix_cord_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cord_status ON public.commercial_customer_order USING btree (status, order_date);


--
-- Name: ix_cord_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cord_type ON public.commercial_customer_order USING btree (order_type_code);


--
-- Name: ix_cord_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cord_updated_by ON public.commercial_customer_order USING btree (updated_by_id);


--
-- Name: ix_credential_set_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credential_set_by ON public.platform_credential USING btree (set_by_id);


--
-- Name: ix_cver_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cver_by ON public.commercial_customer_order_version USING btree (created_by_id);


--
-- Name: ix_cver_cr; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cver_cr ON public.commercial_customer_order_version USING btree (change_request_id);


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
-- Name: ix_ibrd_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ibrd_created_by ON public.identity_customer_brand USING btree (created_by_id);


--
-- Name: ix_ibrd_customer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ibrd_customer ON public.identity_customer_brand USING btree (customer_id);


--
-- Name: ix_ibrd_prov_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ibrd_prov_batch ON public.identity_customer_brand USING btree (import_batch_id);


--
-- Name: ix_ibrd_prov_row; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ibrd_prov_row ON public.identity_customer_brand USING btree (staging_row_id);


--
-- Name: ix_ibrd_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ibrd_updated_by ON public.identity_customer_brand USING btree (updated_by_id);


--
-- Name: ix_icls_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icls_created_by ON public.identity_product_class USING btree (created_by_id);


--
-- Name: ix_icls_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icls_parent ON public.identity_product_class USING btree (parent_id);


--
-- Name: ix_icls_prov_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icls_prov_batch ON public.identity_product_class USING btree (import_batch_id);


--
-- Name: ix_icls_prov_row; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icls_prov_row ON public.identity_product_class USING btree (staging_row_id);


--
-- Name: ix_icls_uom; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icls_uom ON public.identity_product_class USING btree (uom_code);


--
-- Name: ix_icls_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icls_updated_by ON public.identity_product_class USING btree (updated_by_id);


--
-- Name: ix_icrr_approval; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icrr_approval ON public.identity_code_rule_revision USING btree (approval_id);


--
-- Name: ix_icrr_approved_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icrr_approved_by ON public.identity_code_rule_revision USING btree (approved_by_id);


--
-- Name: ix_icrr_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icrr_created_by ON public.identity_code_rule_revision USING btree (created_by_id);


--
-- Name: ix_icrr_evidence; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icrr_evidence ON public.identity_code_rule_revision USING btree (evidence_document_id);


--
-- Name: ix_icrr_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icrr_updated_by ON public.identity_code_rule_revision USING btree (updated_by_id);


--
-- Name: ix_icus_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icus_created_by ON public.identity_customer USING btree (created_by_id);


--
-- Name: ix_icus_name_lower; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icus_name_lower ON public.identity_customer USING btree (lower((display_name_fa)::text));


--
-- Name: ix_icus_prov_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icus_prov_batch ON public.identity_customer USING btree (import_batch_id);


--
-- Name: ix_icus_prov_row; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icus_prov_row ON public.identity_customer USING btree (staging_row_id);


--
-- Name: ix_icus_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_icus_updated_by ON public.identity_customer USING btree (updated_by_id);


--
-- Name: ix_idempotency_record_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_idempotency_record_expires ON public.platform_idempotency_record USING btree (expires_at);


--
-- Name: ix_identity_external_ref_type__key_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_identity_external_ref_type__key_like ON public.identity_external_ref_type USING btree (key varchar_pattern_ops);


--
-- Name: INDEX ix_identity_external_ref_type__key_like; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX public.ix_identity_external_ref_type__key_like IS 'django-name:identity_external_ref_type_key_edaa7081_like';


--
-- Name: ix_identity_unit_of_measure__code_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_identity_unit_of_measure__code_like ON public.identity_unit_of_measure USING btree (code varchar_pattern_ops);


--
-- Name: INDEX ix_identity_unit_of_measure__code_like; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON INDEX public.ix_identity_unit_of_measure__code_like IS 'django-name:identity_unit_of_measure_code_60a22475_like';


--
-- Name: ix_iert_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iert_created_by ON public.identity_external_ref_type USING btree (created_by_id);


--
-- Name: ix_iert_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iert_updated_by ON public.identity_external_ref_type USING btree (updated_by_id);


--
-- Name: ix_iext_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iext_created_by ON public.identity_external_ref USING btree (created_by_id);


--
-- Name: ix_iext_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iext_lookup ON public.identity_external_ref USING btree (system, namespace, value);


--
-- Name: ix_iext_prov_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iext_prov_batch ON public.identity_external_ref USING btree (import_batch_id);


--
-- Name: ix_iext_prov_row; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iext_prov_row ON public.identity_external_ref USING btree (staging_row_id);


--
-- Name: ix_iext_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iext_target ON public.identity_external_ref USING btree (target_type, target_id);


--
-- Name: ix_iext_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iext_type ON public.identity_external_ref USING btree (namespace);


--
-- Name: ix_iext_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iext_updated_by ON public.identity_external_ref USING btree (updated_by_id);


--
-- Name: ix_igld_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_igld_created_by ON public.identity_code_rule_golden_case USING btree (created_by_id);


--
-- Name: ix_igld_family; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_igld_family ON public.identity_code_rule_golden_case USING btree (rule_revision_id, product_type_code);


--
-- Name: ix_igld_verified_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_igld_verified_by ON public.identity_code_rule_golden_case USING btree (verified_by_id);


--
-- Name: ix_ihst_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ihst_batch ON public.identity_historical_order_record USING btree (import_batch_id);


--
-- Name: ix_ihst_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ihst_code ON public.identity_historical_order_record USING btree (normalised_product_code);


--
-- Name: ix_ihst_matched_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ihst_matched_by ON public.identity_historical_order_record USING btree (matched_by_id);


--
-- Name: ix_ihst_pcode; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ihst_pcode ON public.identity_historical_order_record USING btree (matched_product_code_id);


--
-- Name: ix_ihst_serial; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ihst_serial ON public.identity_historical_order_record USING btree (legacy_serial_text);


--
-- Name: ix_ihst_style; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ihst_style ON public.identity_historical_order_record USING btree (matched_style_id);


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
-- Name: ix_ipcd_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ipcd_created_by ON public.identity_product_code USING btree (created_by_id);


--
-- Name: ix_ipcd_erp_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ipcd_erp_batch ON public.identity_product_code USING btree (erp_seen_batch_id);


--
-- Name: ix_ipcd_issued_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ipcd_issued_by ON public.identity_product_code USING btree (issued_by_id);


--
-- Name: ix_ipcd_prov_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ipcd_prov_batch ON public.identity_product_code USING btree (import_batch_id);


--
-- Name: ix_ipcd_prov_row; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ipcd_prov_row ON public.identity_product_code USING btree (staging_row_id);


--
-- Name: ix_ipcd_rule; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ipcd_rule ON public.identity_product_code USING btree (rule_revision_id);


--
-- Name: ix_ipcd_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ipcd_status ON public.identity_product_code USING btree (status, erp_status);


--
-- Name: ix_ipcd_style; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ipcd_style ON public.identity_product_code USING btree (style_id);


--
-- Name: ix_ipcd_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ipcd_updated_by ON public.identity_product_code USING btree (updated_by_id);


--
-- Name: ix_iprd_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iprd_created_by ON public.identity_product USING btree (created_by_id);


--
-- Name: ix_iprd_name_lower; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iprd_name_lower ON public.identity_product USING btree (lower((name_fa)::text));


--
-- Name: ix_iprd_prov_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iprd_prov_batch ON public.identity_product USING btree (import_batch_id);


--
-- Name: ix_iprd_prov_row; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iprd_prov_row ON public.identity_product USING btree (staging_row_id);


--
-- Name: ix_iprd_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iprd_updated_by ON public.identity_product USING btree (updated_by_id);


--
-- Name: ix_iser_allocated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iser_allocated_at ON public.identity_serial USING btree (allocated_at);


--
-- Name: ix_iser_allocated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iser_allocated_by ON public.identity_serial USING btree (allocated_by_id);


--
-- Name: ix_iser_customer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iser_customer ON public.identity_serial USING btree (customer_id);


--
-- Name: ix_iser_product_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iser_product_code ON public.identity_serial USING btree (product_code_id);


--
-- Name: ix_iser_style; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iser_style ON public.identity_serial USING btree (style_id);


--
-- Name: ix_iser_style_revision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iser_style_revision ON public.identity_serial USING btree (style_revision_id);


--
-- Name: ix_isnp_cr; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_isnp_cr ON public.identity_serial_snapshot USING btree (change_request_id);


--
-- Name: ix_isnp_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_isnp_created_by ON public.identity_serial_snapshot USING btree (created_by_id);


--
-- Name: ix_isrv_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_isrv_created_by ON public.identity_style_revision USING btree (created_by_id);


--
-- Name: ix_isrv_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_isrv_updated_by ON public.identity_style_revision USING btree (updated_by_id);


--
-- Name: ix_isty_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_isty_category ON public.identity_style USING btree (category_id);


--
-- Name: ix_isty_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_isty_created_by ON public.identity_style USING btree (created_by_id);


--
-- Name: ix_isty_name_lower; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_isty_name_lower ON public.identity_style USING btree (lower((name_fa)::text));


--
-- Name: ix_isty_prov_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_isty_prov_batch ON public.identity_style USING btree (import_batch_id);


--
-- Name: ix_isty_prov_row; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_isty_prov_row ON public.identity_style USING btree (staging_row_id);


--
-- Name: ix_isty_updated_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_isty_updated_by ON public.identity_style USING btree (updated_by_id);


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
-- Name: ix_outbox_event_agg_open; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_outbox_event_agg_open ON public.platform_outbox_event USING btree (aggregate_type, aggregate_id, id) WHERE (NOT ((delivery_status)::text = ANY ((ARRAY['ACKED'::character varying, 'DISCARDED'::character varying])::text[])));


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
-- Name: uq_identity_brand_customer_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_identity_brand_customer_name ON public.identity_customer_brand USING btree (customer_id, lower((brand_name_fa)::text));


--
-- Name: uq_identity_class_category_segment; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_identity_class_category_segment ON public.identity_product_class USING btree (parent_id, segment_value) WHERE ((level_key)::text = 'category'::text);


--
-- Name: uq_identity_class_type_segment; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_identity_class_type_segment ON public.identity_product_class USING btree (segment_value) WHERE ((level_key)::text = 'product_type'::text);


--
-- Name: uq_identity_code_rule_one_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_identity_code_rule_one_active ON public.identity_code_rule_revision USING btree (code_namespace) WHERE ((status)::text = 'ACTIVE'::text);


--
-- Name: uq_identity_style_revision_one_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_identity_style_revision_one_active ON public.identity_style_revision USING btree (style_id) WHERE ((status)::text = 'ACTIVE'::text);


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
-- Name: platform_approval_request trg_approval_request_bootstrap_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_approval_request_bootstrap_guard BEFORE INSERT OR UPDATE ON public.platform_approval_request FOR EACH ROW EXECUTE FUNCTION public.platform_approval_request_bootstrap_guard();


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
-- Name: commercial_customer_order trg_commercial_customer_order_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_a_terminal BEFORE UPDATE ON public.commercial_customer_order FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'CANCELLED');


--
-- Name: commercial_customer_order trg_commercial_customer_order_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_b_immutable BEFORE UPDATE ON public.commercial_customer_order FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'order_no', 'created_by_id');


--
-- Name: commercial_customer_order trg_commercial_customer_order_committed; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER trg_commercial_customer_order_committed AFTER INSERT OR UPDATE ON public.commercial_customer_order DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.commercial_order_committed();


--
-- Name: commercial_customer_order trg_commercial_customer_order_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_guard BEFORE INSERT OR UPDATE ON public.commercial_customer_order FOR EACH ROW EXECUTE FUNCTION public.commercial_order_guard();


--
-- Name: commercial_customer_order_line trg_commercial_customer_order_line_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_line_a_terminal BEFORE UPDATE ON public.commercial_customer_order_line FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'REMOVED', 'CANCELLED');


--
-- Name: commercial_customer_order_line trg_commercial_customer_order_line_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_line_b_immutable BEFORE UPDATE ON public.commercial_customer_order_line FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'order_id', 'line_no', 'style_id');


--
-- Name: commercial_customer_order_line trg_commercial_customer_order_line_cancel_paired; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER trg_commercial_customer_order_line_cancel_paired AFTER UPDATE ON public.commercial_customer_order_line DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.phase02_line_serial_cancel_paired();


--
-- Name: commercial_customer_order_line trg_commercial_customer_order_line_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_line_guard BEFORE INSERT OR UPDATE ON public.commercial_customer_order_line FOR EACH ROW EXECUTE FUNCTION public.commercial_line_guard();


--
-- Name: commercial_customer_order_line trg_commercial_customer_order_line_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_line_no_delete BEFORE DELETE ON public.commercial_customer_order_line FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: commercial_customer_order_line trg_commercial_customer_order_line_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_line_touch BEFORE UPDATE ON public.commercial_customer_order_line FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: commercial_customer_order trg_commercial_customer_order_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_no_delete BEFORE DELETE ON public.commercial_customer_order FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: commercial_customer_order trg_commercial_customer_order_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_touch BEFORE UPDATE ON public.commercial_customer_order FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: commercial_customer_order_version trg_commercial_customer_order_version_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_version_append_only BEFORE DELETE OR UPDATE ON public.commercial_customer_order_version FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: commercial_customer_order_version trg_commercial_customer_order_version_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_customer_order_version_guard BEFORE INSERT ON public.commercial_customer_order_version FOR EACH ROW EXECUTE FUNCTION public.commercial_order_version_guard();


--
-- Name: commercial_order_change_request trg_commercial_order_change_request_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_order_change_request_a_terminal BEFORE UPDATE ON public.commercial_order_change_request FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'APPLIED', 'REJECTED', 'WITHDRAWN', 'EXPIRED');


--
-- Name: commercial_order_change_request trg_commercial_order_change_request_applied; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER trg_commercial_order_change_request_applied AFTER UPDATE ON public.commercial_order_change_request DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.commercial_change_request_applied();


--
-- Name: commercial_order_change_request trg_commercial_order_change_request_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_order_change_request_b_immutable BEFORE UPDATE ON public.commercial_order_change_request FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'request_no', 'order_id', 'requested_by_id');


--
-- Name: commercial_order_change_request trg_commercial_order_change_request_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_order_change_request_guard BEFORE INSERT OR UPDATE ON public.commercial_order_change_request FOR EACH ROW EXECUTE FUNCTION public.commercial_change_request_guard();


--
-- Name: commercial_order_change_request trg_commercial_order_change_request_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_order_change_request_no_delete BEFORE DELETE ON public.commercial_order_change_request FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: commercial_order_change_request trg_commercial_order_change_request_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_commercial_order_change_request_touch BEFORE UPDATE ON public.commercial_order_change_request FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


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
-- Name: identity_code_rule_golden_case trg_identity_code_rule_golden_case_close_once; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_code_rule_golden_case_close_once BEFORE UPDATE ON public.identity_code_rule_golden_case FOR EACH ROW EXECUTE FUNCTION public.platform_close_once_only('verified_by_id', 'verified_at');


--
-- Name: identity_code_rule_golden_case trg_identity_code_rule_golden_case_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_code_rule_golden_case_no_delete BEFORE DELETE ON public.identity_code_rule_golden_case FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_code_rule_revision trg_identity_code_rule_revision_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_code_rule_revision_a_terminal BEFORE UPDATE ON public.identity_code_rule_revision FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'RETIRED', 'REJECTED');


--
-- Name: identity_code_rule_revision trg_identity_code_rule_revision_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_code_rule_revision_b_immutable BEFORE UPDATE ON public.identity_code_rule_revision FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'code_namespace', 'revision_no', 'created_by_id');


--
-- Name: identity_code_rule_revision trg_identity_code_rule_revision_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_code_rule_revision_guard BEFORE INSERT OR UPDATE ON public.identity_code_rule_revision FOR EACH ROW EXECUTE FUNCTION public.identity_code_rule_guard();


--
-- Name: identity_code_rule_revision trg_identity_code_rule_revision_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_code_rule_revision_no_delete BEFORE DELETE ON public.identity_code_rule_revision FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_code_rule_revision trg_identity_code_rule_revision_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_code_rule_revision_touch BEFORE UPDATE ON public.identity_code_rule_revision FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_customer trg_identity_customer_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_customer_b_immutable BEFORE UPDATE ON public.identity_customer FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'customer_no', 'provenance_kind', 'import_batch_id', 'staging_row_id');


--
-- Name: identity_customer_brand trg_identity_customer_brand_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_customer_brand_b_immutable BEFORE UPDATE ON public.identity_customer_brand FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'customer_id');


--
-- Name: identity_customer_brand trg_identity_customer_brand_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_customer_brand_no_delete BEFORE DELETE ON public.identity_customer_brand FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_customer_brand trg_identity_customer_brand_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_customer_brand_touch BEFORE UPDATE ON public.identity_customer_brand FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_customer trg_identity_customer_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_customer_no_delete BEFORE DELETE ON public.identity_customer FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_customer trg_identity_customer_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_customer_touch BEFORE UPDATE ON public.identity_customer FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_external_ref trg_identity_external_ref_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_external_ref_b_immutable BEFORE UPDATE ON public.identity_external_ref FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'target_type', 'target_id', 'system', 'namespace', 'value');


--
-- Name: identity_external_ref trg_identity_external_ref_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_external_ref_no_delete BEFORE DELETE ON public.identity_external_ref FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_external_ref trg_identity_external_ref_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_external_ref_touch BEFORE UPDATE ON public.identity_external_ref FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_external_ref_type trg_identity_external_ref_type_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_external_ref_type_b_immutable BEFORE UPDATE ON public.identity_external_ref_type FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('key');


--
-- Name: identity_external_ref_type trg_identity_external_ref_type_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_external_ref_type_no_delete BEFORE DELETE ON public.identity_external_ref_type FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_external_ref_type trg_identity_external_ref_type_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_external_ref_type_touch BEFORE UPDATE ON public.identity_external_ref_type FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_historical_order_record trg_identity_historical_order_record_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_historical_order_record_guard BEFORE INSERT OR UPDATE ON public.identity_historical_order_record FOR EACH ROW EXECUTE FUNCTION public.identity_historical_guard();


--
-- Name: identity_historical_order_record trg_identity_historical_order_record_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_historical_order_record_no_delete BEFORE DELETE ON public.identity_historical_order_record FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_historical_order_record trg_identity_historical_order_record_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_historical_order_record_touch BEFORE UPDATE ON public.identity_historical_order_record FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_product trg_identity_product_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_b_immutable BEFORE UPDATE ON public.identity_product FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'product_type_id', 'product_no', 'buckle_type_code', 'belt_width_code');


--
-- Name: identity_product_class trg_identity_product_class_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_class_b_immutable BEFORE UPDATE ON public.identity_product_class FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'level_key', 'parent_id', 'segment_value');


--
-- Name: identity_product_class trg_identity_product_class_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_class_guard BEFORE INSERT OR UPDATE ON public.identity_product_class FOR EACH ROW EXECUTE FUNCTION public.identity_product_class_guard();


--
-- Name: identity_product_class trg_identity_product_class_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_class_no_delete BEFORE DELETE ON public.identity_product_class FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_product_class trg_identity_product_class_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_class_touch BEFORE UPDATE ON public.identity_product_class FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_product_code trg_identity_product_code_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_code_b_immutable BEFORE UPDATE ON public.identity_product_code FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'code', 'code_namespace', 'rule_revision_id', 'issue_idempotency_key', 'issued_by_id', 'issued_at', 'provenance_kind');


--
-- Name: identity_product_code trg_identity_product_code_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_code_guard BEFORE INSERT OR UPDATE ON public.identity_product_code FOR EACH ROW EXECUTE FUNCTION public.identity_product_code_guard();


--
-- Name: identity_product_code trg_identity_product_code_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_code_no_delete BEFORE DELETE ON public.identity_product_code FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_product_code trg_identity_product_code_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_code_touch BEFORE UPDATE ON public.identity_product_code FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_product trg_identity_product_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_guard BEFORE INSERT OR UPDATE ON public.identity_product FOR EACH ROW EXECUTE FUNCTION public.identity_product_guard();


--
-- Name: identity_product trg_identity_product_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_no_delete BEFORE DELETE ON public.identity_product FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_product trg_identity_product_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_product_touch BEFORE UPDATE ON public.identity_product FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_serial trg_identity_serial_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_a_terminal BEFORE UPDATE ON public.identity_serial FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'CANCELLED');


--
-- Name: identity_serial trg_identity_serial_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_b_immutable BEFORE UPDATE ON public.identity_serial FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'serial_counter_id', 'serial_number', 'serial_value', 'customer_id', 'style_id', 'allocation_idempotency_key', 'allocated_by_id', 'allocated_at');


--
-- Name: identity_serial trg_identity_serial_cancel_paired; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER trg_identity_serial_cancel_paired AFTER UPDATE ON public.identity_serial DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.phase02_line_serial_cancel_paired();


--
-- Name: identity_serial trg_identity_serial_committed; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER trg_identity_serial_committed AFTER INSERT ON public.identity_serial DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.identity_serial_committed();


--
-- Name: identity_serial_counter trg_identity_serial_counter_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_counter_b_immutable BEFORE UPDATE ON public.identity_serial_counter FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'namespace_key', 'start_value', 'legacy_max_exclusive', 'number_pattern', 'decision_id');


--
-- Name: identity_serial_counter trg_identity_serial_counter_gapless; Type: TRIGGER; Schema: public; Owner: -
--

CREATE CONSTRAINT TRIGGER trg_identity_serial_counter_gapless AFTER UPDATE ON public.identity_serial_counter DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.identity_serial_counter_gapless();


--
-- Name: identity_serial_counter trg_identity_serial_counter_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_counter_guard BEFORE INSERT OR UPDATE ON public.identity_serial_counter FOR EACH ROW EXECUTE FUNCTION public.identity_serial_counter_guard();


--
-- Name: identity_serial_counter trg_identity_serial_counter_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_counter_no_delete BEFORE DELETE ON public.identity_serial_counter FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_serial_counter trg_identity_serial_counter_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_counter_touch BEFORE UPDATE ON public.identity_serial_counter FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_serial trg_identity_serial_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_guard BEFORE INSERT OR UPDATE ON public.identity_serial FOR EACH ROW EXECUTE FUNCTION public.identity_serial_guard();


--
-- Name: identity_serial trg_identity_serial_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_no_delete BEFORE DELETE ON public.identity_serial FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_serial_snapshot trg_identity_serial_snapshot_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_snapshot_append_only BEFORE DELETE OR UPDATE ON public.identity_serial_snapshot FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_serial_snapshot trg_identity_serial_snapshot_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_snapshot_guard BEFORE INSERT ON public.identity_serial_snapshot FOR EACH ROW EXECUTE FUNCTION public.identity_serial_snapshot_guard();


--
-- Name: identity_serial trg_identity_serial_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_serial_touch BEFORE UPDATE ON public.identity_serial FOR EACH ROW EXECUTE FUNCTION public.platform_bump_row();


--
-- Name: identity_style trg_identity_style_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_style_b_immutable BEFORE UPDATE ON public.identity_style FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'product_id', 'category_id', 'style_no');


--
-- Name: identity_style trg_identity_style_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_style_guard BEFORE INSERT OR UPDATE ON public.identity_style FOR EACH ROW EXECUTE FUNCTION public.identity_style_guard();


--
-- Name: identity_style trg_identity_style_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_style_no_delete BEFORE DELETE ON public.identity_style FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_style_revision trg_identity_style_revision_a_terminal; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_style_revision_a_terminal BEFORE UPDATE ON public.identity_style_revision FOR EACH ROW EXECUTE FUNCTION public.platform_reject_terminal_update('status', 'SUPERSEDED');


--
-- Name: identity_style_revision trg_identity_style_revision_b_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_style_revision_b_immutable BEFORE UPDATE ON public.identity_style_revision FOR EACH ROW EXECUTE FUNCTION public.platform_immutable_columns('id', 'style_id', 'revision_no');


--
-- Name: identity_style_revision trg_identity_style_revision_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_style_revision_guard BEFORE UPDATE ON public.identity_style_revision FOR EACH ROW EXECUTE FUNCTION public.identity_style_revision_guard();


--
-- Name: identity_style_revision trg_identity_style_revision_no_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_style_revision_no_delete BEFORE DELETE ON public.identity_style_revision FOR EACH ROW EXECUTE FUNCTION public.platform_reject_mutation();


--
-- Name: identity_style_revision trg_identity_style_revision_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_style_revision_touch BEFORE UPDATE ON public.identity_style_revision FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


--
-- Name: identity_style trg_identity_style_touch; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_identity_style_touch BEFORE UPDATE ON public.identity_style FOR EACH ROW EXECUTE FUNCTION public.platform_touch_row();


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
-- Name: platform_number_counter trg_platform_number_counter_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_platform_number_counter_guard BEFORE INSERT OR DELETE OR UPDATE ON public.platform_number_counter FOR EACH ROW EXECUTE FUNCTION public.platform_number_counter_guard();


--
-- Name: platform_number_counter trg_platform_number_counter_no_truncate; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_platform_number_counter_no_truncate BEFORE TRUNCATE ON public.platform_number_counter FOR EACH STATEMENT EXECUTE FUNCTION public.platform_number_counter_no_truncate();


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
-- Name: commercial_customer_order fk_commercial_customer_order__brand_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order
    ADD CONSTRAINT fk_commercial_customer_order__brand_id FOREIGN KEY (brand_id) REFERENCES public.identity_customer_brand(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order__brand_id ON commercial_customer_order; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order__brand_id ON public.commercial_customer_order IS 'django-name:commercial_customer__brand_id_9a81c58a_fk_identity_';


--
-- Name: commercial_customer_order fk_commercial_customer_order__confirmed_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order
    ADD CONSTRAINT fk_commercial_customer_order__confirmed_by_id FOREIGN KEY (confirmed_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order__confirmed_by_id ON commercial_customer_order; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order__confirmed_by_id ON public.commercial_customer_order IS 'django-name:commercial_customer__confirmed_by_id_3432f073_fk_platform_';


--
-- Name: commercial_customer_order fk_commercial_customer_order__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order
    ADD CONSTRAINT fk_commercial_customer_order__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order__created_by_id ON commercial_customer_order; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order__created_by_id ON public.commercial_customer_order IS 'django-name:commercial_customer__created_by_id_2e3a6231_fk_platform_';


--
-- Name: commercial_customer_order fk_commercial_customer_order__customer_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order
    ADD CONSTRAINT fk_commercial_customer_order__customer_id FOREIGN KEY (customer_id) REFERENCES public.identity_customer(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order__customer_id ON commercial_customer_order; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order__customer_id ON public.commercial_customer_order IS 'django-name:commercial_customer__customer_id_4917fbc7_fk_identity_';


--
-- Name: commercial_customer_order fk_commercial_customer_order__order_type_code; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order
    ADD CONSTRAINT fk_commercial_customer_order__order_type_code FOREIGN KEY (order_type_code) REFERENCES public.commercial_order_type(code) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order__order_type_code ON commercial_customer_order; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order__order_type_code ON public.commercial_customer_order IS 'django-name:commercial_customer__order_type_code_eaedd1b3_fk_commercia';


--
-- Name: commercial_customer_order fk_commercial_customer_order__released_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order
    ADD CONSTRAINT fk_commercial_customer_order__released_by_id FOREIGN KEY (released_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order__released_by_id ON commercial_customer_order; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order__released_by_id ON public.commercial_customer_order IS 'django-name:commercial_customer__released_by_id_1a6339c0_fk_platform_';


--
-- Name: commercial_customer_order fk_commercial_customer_order__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order
    ADD CONSTRAINT fk_commercial_customer_order__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order__updated_by_id ON commercial_customer_order; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order__updated_by_id ON public.commercial_customer_order IS 'django-name:commercial_customer__updated_by_id_9aa16a5a_fk_platform_';


--
-- Name: commercial_customer_order_line fk_commercial_customer_order_line__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT fk_commercial_customer_order_line__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_line__created_by_id ON commercial_customer_order_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_line__created_by_id ON public.commercial_customer_order_line IS 'django-name:commercial_customer__created_by_id_2861d029_fk_platform_';


--
-- Name: commercial_customer_order_line fk_commercial_customer_order_line__order_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT fk_commercial_customer_order_line__order_id FOREIGN KEY (order_id) REFERENCES public.commercial_customer_order(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_line__order_id ON commercial_customer_order_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_line__order_id ON public.commercial_customer_order_line IS 'django-name:commercial_customer__order_id_b535cfce_fk_commercia';


--
-- Name: commercial_customer_order_line fk_commercial_customer_order_line__product_code_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT fk_commercial_customer_order_line__product_code_id FOREIGN KEY (product_code_id) REFERENCES public.identity_product_code(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_line__product_code_id ON commercial_customer_order_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_line__product_code_id ON public.commercial_customer_order_line IS 'django-name:commercial_customer__product_code_id_3828d488_fk_identity_';


--
-- Name: commercial_customer_order_line fk_commercial_customer_order_line__serial_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT fk_commercial_customer_order_line__serial_id FOREIGN KEY (serial_id) REFERENCES public.identity_serial(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_line__serial_id ON commercial_customer_order_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_line__serial_id ON public.commercial_customer_order_line IS 'django-name:commercial_customer__serial_id_df31eaa4_fk_identity_';


--
-- Name: commercial_customer_order_line fk_commercial_customer_order_line__style_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT fk_commercial_customer_order_line__style_id FOREIGN KEY (style_id) REFERENCES public.identity_style(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_line__style_id ON commercial_customer_order_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_line__style_id ON public.commercial_customer_order_line IS 'django-name:commercial_customer__style_id_08b969c8_fk_identity_';


--
-- Name: commercial_customer_order_line fk_commercial_customer_order_line__style_revision_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT fk_commercial_customer_order_line__style_revision_id FOREIGN KEY (style_revision_id) REFERENCES public.identity_style_revision(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_line__style_revision_id ON commercial_customer_order_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_line__style_revision_id ON public.commercial_customer_order_line IS 'django-name:commercial_customer__style_revision_id_153918c1_fk_identity_';


--
-- Name: commercial_customer_order_line fk_commercial_customer_order_line__uom_code; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT fk_commercial_customer_order_line__uom_code FOREIGN KEY (uom_code) REFERENCES public.identity_unit_of_measure(code) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_line__uom_code ON commercial_customer_order_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_line__uom_code ON public.commercial_customer_order_line IS 'django-name:commercial_customer__uom_code_649cfede_fk_identity_';


--
-- Name: commercial_customer_order_line fk_commercial_customer_order_line__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_line
    ADD CONSTRAINT fk_commercial_customer_order_line__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_line__updated_by_id ON commercial_customer_order_line; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_line__updated_by_id ON public.commercial_customer_order_line IS 'django-name:commercial_customer__updated_by_id_58f837a4_fk_platform_';


--
-- Name: commercial_customer_order_version fk_commercial_customer_order_version__change_request_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_version
    ADD CONSTRAINT fk_commercial_customer_order_version__change_request_id FOREIGN KEY (change_request_id) REFERENCES public.commercial_order_change_request(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_version__change_request_id ON commercial_customer_order_version; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_version__change_request_id ON public.commercial_customer_order_version IS 'django-name:commercial_customer__change_request_id_f1ea8451_fk_commercia';


--
-- Name: commercial_customer_order_version fk_commercial_customer_order_version__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_version
    ADD CONSTRAINT fk_commercial_customer_order_version__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_version__created_by_id ON commercial_customer_order_version; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_version__created_by_id ON public.commercial_customer_order_version IS 'django-name:commercial_customer__created_by_id_5db24648_fk_platform_';


--
-- Name: commercial_customer_order_version fk_commercial_customer_order_version__order_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_customer_order_version
    ADD CONSTRAINT fk_commercial_customer_order_version__order_id FOREIGN KEY (order_id) REFERENCES public.commercial_customer_order(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_customer_order_version__order_id ON commercial_customer_order_version; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_customer_order_version__order_id ON public.commercial_customer_order_version IS 'django-name:commercial_customer__order_id_00fee341_fk_commercia';


--
-- Name: commercial_order_change_request fk_commercial_order_change_request__applied_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_change_request
    ADD CONSTRAINT fk_commercial_order_change_request__applied_by_id FOREIGN KEY (applied_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_order_change_request__applied_by_id ON commercial_order_change_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_order_change_request__applied_by_id ON public.commercial_order_change_request IS 'django-name:commercial_order_cha_applied_by_id_4be9fb0a_fk_platform_';


--
-- Name: commercial_order_change_request fk_commercial_order_change_request__approval_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_change_request
    ADD CONSTRAINT fk_commercial_order_change_request__approval_id FOREIGN KEY (approval_id) REFERENCES public.platform_approval_request(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_order_change_request__approval_id ON commercial_order_change_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_order_change_request__approval_id ON public.commercial_order_change_request IS 'django-name:commercial_order_cha_approval_id_541ac81e_fk_platform_';


--
-- Name: commercial_order_change_request fk_commercial_order_change_request__decided_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_change_request
    ADD CONSTRAINT fk_commercial_order_change_request__decided_by_id FOREIGN KEY (decided_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_order_change_request__decided_by_id ON commercial_order_change_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_order_change_request__decided_by_id ON public.commercial_order_change_request IS 'django-name:commercial_order_cha_decided_by_id_5913ffaa_fk_platform_';


--
-- Name: commercial_order_change_request fk_commercial_order_change_request__order_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_change_request
    ADD CONSTRAINT fk_commercial_order_change_request__order_id FOREIGN KEY (order_id) REFERENCES public.commercial_customer_order(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_order_change_request__order_id ON commercial_order_change_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_order_change_request__order_id ON public.commercial_order_change_request IS 'django-name:commercial_order_cha_order_id_355fb983_fk_commercia';


--
-- Name: commercial_order_change_request fk_commercial_order_change_request__planning_approval_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_change_request
    ADD CONSTRAINT fk_commercial_order_change_request__planning_approval_id FOREIGN KEY (planning_approval_id) REFERENCES public.platform_approval_request(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_order_change_request__planning_approval_id ON commercial_order_change_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_order_change_request__planning_approval_id ON public.commercial_order_change_request IS 'django-name:commercial_order_cha_planning_approval_id_70dd6394_fk_platform_';


--
-- Name: commercial_order_change_request fk_commercial_order_change_request__planning_approved_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_change_request
    ADD CONSTRAINT fk_commercial_order_change_request__planning_approved_by_id FOREIGN KEY (planning_approved_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_order_change_request__planning_approved_by_id ON commercial_order_change_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_order_change_request__planning_approved_by_id ON public.commercial_order_change_request IS 'django-name:commercial_order_cha_planning_approved_by_cd6fb282_fk_platform_';


--
-- Name: commercial_order_change_request fk_commercial_order_change_request__planning_rejected_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_change_request
    ADD CONSTRAINT fk_commercial_order_change_request__planning_rejected_by_id FOREIGN KEY (planning_rejected_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_order_change_request__planning_rejected_by_id ON commercial_order_change_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_order_change_request__planning_rejected_by_id ON public.commercial_order_change_request IS 'django-name:commercial_order_cha_planning_rejected_by_a4ec55c0_fk_platform_';


--
-- Name: commercial_order_change_request fk_commercial_order_change_request__requested_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commercial_order_change_request
    ADD CONSTRAINT fk_commercial_order_change_request__requested_by_id FOREIGN KEY (requested_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_commercial_order_change_request__requested_by_id ON commercial_order_change_request; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_commercial_order_change_request__requested_by_id ON public.commercial_order_change_request IS 'django-name:commercial_order_cha_requested_by_id_3c286d41_fk_platform_';


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
-- Name: identity_code_rule_golden_case fk_identity_code_rule_golden_case__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_golden_case
    ADD CONSTRAINT fk_identity_code_rule_golden_case__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_code_rule_golden_case__created_by_id ON identity_code_rule_golden_case; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_code_rule_golden_case__created_by_id ON public.identity_code_rule_golden_case IS 'django-name:identity_code_rule_g_created_by_id_aecd46bf_fk_platform_';


--
-- Name: identity_code_rule_golden_case fk_identity_code_rule_golden_case__rule_revision_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_golden_case
    ADD CONSTRAINT fk_identity_code_rule_golden_case__rule_revision_id FOREIGN KEY (rule_revision_id) REFERENCES public.identity_code_rule_revision(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_code_rule_golden_case__rule_revision_id ON identity_code_rule_golden_case; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_code_rule_golden_case__rule_revision_id ON public.identity_code_rule_golden_case IS 'django-name:identity_code_rule_g_rule_revision_id_9acd9a86_fk_identity_';


--
-- Name: identity_code_rule_golden_case fk_identity_code_rule_golden_case__verified_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_golden_case
    ADD CONSTRAINT fk_identity_code_rule_golden_case__verified_by_id FOREIGN KEY (verified_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_code_rule_golden_case__verified_by_id ON identity_code_rule_golden_case; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_code_rule_golden_case__verified_by_id ON public.identity_code_rule_golden_case IS 'django-name:identity_code_rule_g_verified_by_id_43b0e7a6_fk_platform_';


--
-- Name: identity_code_rule_revision fk_identity_code_rule_revision__approval_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_revision
    ADD CONSTRAINT fk_identity_code_rule_revision__approval_id FOREIGN KEY (approval_id) REFERENCES public.platform_approval_request(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_code_rule_revision__approval_id ON identity_code_rule_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_code_rule_revision__approval_id ON public.identity_code_rule_revision IS 'django-name:identity_code_rule_r_approval_id_3c8809e1_fk_platform_';


--
-- Name: identity_code_rule_revision fk_identity_code_rule_revision__approved_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_revision
    ADD CONSTRAINT fk_identity_code_rule_revision__approved_by_id FOREIGN KEY (approved_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_code_rule_revision__approved_by_id ON identity_code_rule_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_code_rule_revision__approved_by_id ON public.identity_code_rule_revision IS 'django-name:identity_code_rule_r_approved_by_id_07f9ba24_fk_platform_';


--
-- Name: identity_code_rule_revision fk_identity_code_rule_revision__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_revision
    ADD CONSTRAINT fk_identity_code_rule_revision__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_code_rule_revision__created_by_id ON identity_code_rule_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_code_rule_revision__created_by_id ON public.identity_code_rule_revision IS 'django-name:identity_code_rule_r_created_by_id_2e1e0d61_fk_platform_';


--
-- Name: identity_code_rule_revision fk_identity_code_rule_revision__evidence_document_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_revision
    ADD CONSTRAINT fk_identity_code_rule_revision__evidence_document_id FOREIGN KEY (evidence_document_id) REFERENCES public.platform_document(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_code_rule_revision__evidence_document_id ON identity_code_rule_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_code_rule_revision__evidence_document_id ON public.identity_code_rule_revision IS 'django-name:identity_code_rule_r_evidence_document_id_fe309f4d_fk_platform_';


--
-- Name: identity_code_rule_revision fk_identity_code_rule_revision__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_code_rule_revision
    ADD CONSTRAINT fk_identity_code_rule_revision__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_code_rule_revision__updated_by_id ON identity_code_rule_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_code_rule_revision__updated_by_id ON public.identity_code_rule_revision IS 'django-name:identity_code_rule_r_updated_by_id_5fe4d196_fk_platform_';


--
-- Name: identity_customer fk_identity_customer__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer
    ADD CONSTRAINT fk_identity_customer__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_customer__created_by_id ON identity_customer; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_customer__created_by_id ON public.identity_customer IS 'django-name:identity_customer_created_by_id_921f8c64_fk_platform_user_id';


--
-- Name: identity_customer fk_identity_customer__import_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer
    ADD CONSTRAINT fk_identity_customer__import_batch_id FOREIGN KEY (import_batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_customer__import_batch_id ON identity_customer; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_customer__import_batch_id ON public.identity_customer IS 'django-name:identity_customer_import_batch_id_d5c21f36_fk_platform_';


--
-- Name: identity_customer fk_identity_customer__staging_row_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer
    ADD CONSTRAINT fk_identity_customer__staging_row_id FOREIGN KEY (staging_row_id) REFERENCES public.platform_import_staging_row(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_customer__staging_row_id ON identity_customer; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_customer__staging_row_id ON public.identity_customer IS 'django-name:identity_customer_staging_row_id_496dce79_fk_platform_';


--
-- Name: identity_customer fk_identity_customer__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer
    ADD CONSTRAINT fk_identity_customer__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_customer__updated_by_id ON identity_customer; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_customer__updated_by_id ON public.identity_customer IS 'django-name:identity_customer_updated_by_id_daedcccb_fk_platform_user_id';


--
-- Name: identity_customer_brand fk_identity_customer_brand__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer_brand
    ADD CONSTRAINT fk_identity_customer_brand__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_customer_brand__created_by_id ON identity_customer_brand; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_customer_brand__created_by_id ON public.identity_customer_brand IS 'django-name:identity_customer_br_created_by_id_5fece7b6_fk_platform_';


--
-- Name: identity_customer_brand fk_identity_customer_brand__customer_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer_brand
    ADD CONSTRAINT fk_identity_customer_brand__customer_id FOREIGN KEY (customer_id) REFERENCES public.identity_customer(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_customer_brand__customer_id ON identity_customer_brand; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_customer_brand__customer_id ON public.identity_customer_brand IS 'django-name:identity_customer_br_customer_id_e8aa0ac9_fk_identity_';


--
-- Name: identity_customer_brand fk_identity_customer_brand__import_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer_brand
    ADD CONSTRAINT fk_identity_customer_brand__import_batch_id FOREIGN KEY (import_batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_customer_brand__import_batch_id ON identity_customer_brand; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_customer_brand__import_batch_id ON public.identity_customer_brand IS 'django-name:identity_customer_br_import_batch_id_5687cb6e_fk_platform_';


--
-- Name: identity_customer_brand fk_identity_customer_brand__staging_row_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer_brand
    ADD CONSTRAINT fk_identity_customer_brand__staging_row_id FOREIGN KEY (staging_row_id) REFERENCES public.platform_import_staging_row(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_customer_brand__staging_row_id ON identity_customer_brand; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_customer_brand__staging_row_id ON public.identity_customer_brand IS 'django-name:identity_customer_br_staging_row_id_bcf0e5d3_fk_platform_';


--
-- Name: identity_customer_brand fk_identity_customer_brand__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_customer_brand
    ADD CONSTRAINT fk_identity_customer_brand__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_customer_brand__updated_by_id ON identity_customer_brand; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_customer_brand__updated_by_id ON public.identity_customer_brand IS 'django-name:identity_customer_br_updated_by_id_3d72a51e_fk_platform_';


--
-- Name: identity_external_ref fk_identity_external_ref__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_external_ref
    ADD CONSTRAINT fk_identity_external_ref__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_external_ref__created_by_id ON identity_external_ref; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_external_ref__created_by_id ON public.identity_external_ref IS 'django-name:identity_external_re_created_by_id_c683a88b_fk_platform_';


--
-- Name: identity_external_ref fk_identity_external_ref__import_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_external_ref
    ADD CONSTRAINT fk_identity_external_ref__import_batch_id FOREIGN KEY (import_batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_external_ref__import_batch_id ON identity_external_ref; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_external_ref__import_batch_id ON public.identity_external_ref IS 'django-name:identity_external_re_import_batch_id_fa423ac7_fk_platform_';


--
-- Name: identity_external_ref fk_identity_external_ref__namespace; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_external_ref
    ADD CONSTRAINT fk_identity_external_ref__namespace FOREIGN KEY (namespace) REFERENCES public.identity_external_ref_type(key) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_external_ref__namespace ON identity_external_ref; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_external_ref__namespace ON public.identity_external_ref IS 'django-name:identity_external_re_namespace_d0bb392d_fk_identity_';


--
-- Name: identity_external_ref fk_identity_external_ref__staging_row_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_external_ref
    ADD CONSTRAINT fk_identity_external_ref__staging_row_id FOREIGN KEY (staging_row_id) REFERENCES public.platform_import_staging_row(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_external_ref__staging_row_id ON identity_external_ref; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_external_ref__staging_row_id ON public.identity_external_ref IS 'django-name:identity_external_re_staging_row_id_cb61491b_fk_platform_';


--
-- Name: identity_external_ref fk_identity_external_ref__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_external_ref
    ADD CONSTRAINT fk_identity_external_ref__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_external_ref__updated_by_id ON identity_external_ref; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_external_ref__updated_by_id ON public.identity_external_ref IS 'django-name:identity_external_re_updated_by_id_a57ade21_fk_platform_';


--
-- Name: identity_external_ref_type fk_identity_external_ref_type__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_external_ref_type
    ADD CONSTRAINT fk_identity_external_ref_type__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_external_ref_type__created_by_id ON identity_external_ref_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_external_ref_type__created_by_id ON public.identity_external_ref_type IS 'django-name:identity_external_re_created_by_id_c584a6fc_fk_platform_';


--
-- Name: identity_external_ref_type fk_identity_external_ref_type__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_external_ref_type
    ADD CONSTRAINT fk_identity_external_ref_type__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_external_ref_type__updated_by_id ON identity_external_ref_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_external_ref_type__updated_by_id ON public.identity_external_ref_type IS 'django-name:identity_external_re_updated_by_id_3882a6eb_fk_platform_';


--
-- Name: identity_historical_order_record fk_identity_historical_order_record__import_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_historical_order_record
    ADD CONSTRAINT fk_identity_historical_order_record__import_batch_id FOREIGN KEY (import_batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_historical_order_record__import_batch_id ON identity_historical_order_record; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_historical_order_record__import_batch_id ON public.identity_historical_order_record IS 'django-name:identity_historical__import_batch_id_47041c80_fk_platform_';


--
-- Name: identity_historical_order_record fk_identity_historical_order_record__matched_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_historical_order_record
    ADD CONSTRAINT fk_identity_historical_order_record__matched_by_id FOREIGN KEY (matched_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_historical_order_record__matched_by_id ON identity_historical_order_record; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_historical_order_record__matched_by_id ON public.identity_historical_order_record IS 'django-name:identity_historical__matched_by_id_c50adbd5_fk_platform_';


--
-- Name: identity_historical_order_record fk_identity_historical_order_record__matched_product_code_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_historical_order_record
    ADD CONSTRAINT fk_identity_historical_order_record__matched_product_code_id FOREIGN KEY (matched_product_code_id) REFERENCES public.identity_product_code(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_historical_order_record__matched_product_code_id ON identity_historical_order_record; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_historical_order_record__matched_product_code_id ON public.identity_historical_order_record IS 'django-name:identity_historical__matched_product_code_8c3023b9_fk_identity_';


--
-- Name: identity_historical_order_record fk_identity_historical_order_record__matched_style_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_historical_order_record
    ADD CONSTRAINT fk_identity_historical_order_record__matched_style_id FOREIGN KEY (matched_style_id) REFERENCES public.identity_style(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_historical_order_record__matched_style_id ON identity_historical_order_record; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_historical_order_record__matched_style_id ON public.identity_historical_order_record IS 'django-name:identity_historical__matched_style_id_71a4ba02_fk_identity_';


--
-- Name: identity_historical_order_record fk_identity_historical_order_record__staging_row_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_historical_order_record
    ADD CONSTRAINT fk_identity_historical_order_record__staging_row_id FOREIGN KEY (staging_row_id) REFERENCES public.platform_import_staging_row(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_historical_order_record__staging_row_id ON identity_historical_order_record; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_historical_order_record__staging_row_id ON public.identity_historical_order_record IS 'django-name:identity_historical__staging_row_id_f7073c56_fk_platform_';


--
-- Name: identity_product fk_identity_product__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product
    ADD CONSTRAINT fk_identity_product__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product__created_by_id ON identity_product; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product__created_by_id ON public.identity_product IS 'django-name:identity_product_created_by_id_4a339101_fk_platform_user_id';


--
-- Name: identity_product fk_identity_product__import_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product
    ADD CONSTRAINT fk_identity_product__import_batch_id FOREIGN KEY (import_batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product__import_batch_id ON identity_product; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product__import_batch_id ON public.identity_product IS 'django-name:identity_product_import_batch_id_f69ecadd_fk_platform_';


--
-- Name: identity_product fk_identity_product__product_type_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product
    ADD CONSTRAINT fk_identity_product__product_type_id FOREIGN KEY (product_type_id) REFERENCES public.identity_product_class(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product__product_type_id ON identity_product; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product__product_type_id ON public.identity_product IS 'django-name:identity_product_product_type_id_cbe0abd9_fk_identity_';


--
-- Name: identity_product fk_identity_product__staging_row_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product
    ADD CONSTRAINT fk_identity_product__staging_row_id FOREIGN KEY (staging_row_id) REFERENCES public.platform_import_staging_row(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product__staging_row_id ON identity_product; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product__staging_row_id ON public.identity_product IS 'django-name:identity_product_staging_row_id_1bf2538f_fk_platform_';


--
-- Name: identity_product fk_identity_product__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product
    ADD CONSTRAINT fk_identity_product__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product__updated_by_id ON identity_product; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product__updated_by_id ON public.identity_product IS 'django-name:identity_product_updated_by_id_856bf3da_fk_platform_user_id';


--
-- Name: identity_product_class fk_identity_product_class__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_class
    ADD CONSTRAINT fk_identity_product_class__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_class__created_by_id ON identity_product_class; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_class__created_by_id ON public.identity_product_class IS 'django-name:identity_product_cla_created_by_id_81f315c4_fk_platform_';


--
-- Name: identity_product_class fk_identity_product_class__import_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_class
    ADD CONSTRAINT fk_identity_product_class__import_batch_id FOREIGN KEY (import_batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_class__import_batch_id ON identity_product_class; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_class__import_batch_id ON public.identity_product_class IS 'django-name:identity_product_cla_import_batch_id_3300b807_fk_platform_';


--
-- Name: identity_product_class fk_identity_product_class__parent_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_class
    ADD CONSTRAINT fk_identity_product_class__parent_id FOREIGN KEY (parent_id) REFERENCES public.identity_product_class(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_class__parent_id ON identity_product_class; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_class__parent_id ON public.identity_product_class IS 'django-name:identity_product_cla_parent_id_6b08a305_fk_identity_';


--
-- Name: identity_product_class fk_identity_product_class__staging_row_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_class
    ADD CONSTRAINT fk_identity_product_class__staging_row_id FOREIGN KEY (staging_row_id) REFERENCES public.platform_import_staging_row(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_class__staging_row_id ON identity_product_class; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_class__staging_row_id ON public.identity_product_class IS 'django-name:identity_product_cla_staging_row_id_5f9b0577_fk_platform_';


--
-- Name: identity_product_class fk_identity_product_class__uom_code; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_class
    ADD CONSTRAINT fk_identity_product_class__uom_code FOREIGN KEY (uom_code) REFERENCES public.identity_unit_of_measure(code) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_class__uom_code ON identity_product_class; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_class__uom_code ON public.identity_product_class IS 'django-name:identity_product_cla_uom_code_30b945b2_fk_identity_';


--
-- Name: identity_product_class fk_identity_product_class__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_class
    ADD CONSTRAINT fk_identity_product_class__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_class__updated_by_id ON identity_product_class; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_class__updated_by_id ON public.identity_product_class IS 'django-name:identity_product_cla_updated_by_id_54525200_fk_platform_';


--
-- Name: identity_product_code fk_identity_product_code__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT fk_identity_product_code__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_code__created_by_id ON identity_product_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_code__created_by_id ON public.identity_product_code IS 'django-name:identity_product_cod_created_by_id_61e35d6d_fk_platform_';


--
-- Name: identity_product_code fk_identity_product_code__erp_seen_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT fk_identity_product_code__erp_seen_batch_id FOREIGN KEY (erp_seen_batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_code__erp_seen_batch_id ON identity_product_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_code__erp_seen_batch_id ON public.identity_product_code IS 'django-name:identity_product_cod_erp_seen_batch_id_87d9c706_fk_platform_';


--
-- Name: identity_product_code fk_identity_product_code__import_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT fk_identity_product_code__import_batch_id FOREIGN KEY (import_batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_code__import_batch_id ON identity_product_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_code__import_batch_id ON public.identity_product_code IS 'django-name:identity_product_cod_import_batch_id_f6a0a5b3_fk_platform_';


--
-- Name: identity_product_code fk_identity_product_code__issued_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT fk_identity_product_code__issued_by_id FOREIGN KEY (issued_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_code__issued_by_id ON identity_product_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_code__issued_by_id ON public.identity_product_code IS 'django-name:identity_product_code_issued_by_id_65fd3445_fk_platform_user_id';


--
-- Name: identity_product_code fk_identity_product_code__rule_revision_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT fk_identity_product_code__rule_revision_id FOREIGN KEY (rule_revision_id) REFERENCES public.identity_code_rule_revision(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_code__rule_revision_id ON identity_product_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_code__rule_revision_id ON public.identity_product_code IS 'django-name:identity_product_cod_rule_revision_id_2cf9e3c6_fk_identity_';


--
-- Name: identity_product_code fk_identity_product_code__staging_row_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT fk_identity_product_code__staging_row_id FOREIGN KEY (staging_row_id) REFERENCES public.platform_import_staging_row(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_code__staging_row_id ON identity_product_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_code__staging_row_id ON public.identity_product_code IS 'django-name:identity_product_cod_staging_row_id_4c2a789c_fk_platform_';


--
-- Name: identity_product_code fk_identity_product_code__style_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT fk_identity_product_code__style_id FOREIGN KEY (style_id) REFERENCES public.identity_style(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_code__style_id ON identity_product_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_code__style_id ON public.identity_product_code IS 'django-name:identity_product_code_style_id_7848c57d_fk_identity_style_id';


--
-- Name: identity_product_code fk_identity_product_code__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_product_code
    ADD CONSTRAINT fk_identity_product_code__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_product_code__updated_by_id ON identity_product_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_product_code__updated_by_id ON public.identity_product_code IS 'django-name:identity_product_cod_updated_by_id_49863cd2_fk_platform_';


--
-- Name: identity_serial fk_identity_serial__allocated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial
    ADD CONSTRAINT fk_identity_serial__allocated_by_id FOREIGN KEY (allocated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_serial__allocated_by_id ON identity_serial; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_serial__allocated_by_id ON public.identity_serial IS 'django-name:identity_serial_allocated_by_id_43431ec5_fk_platform_user_id';


--
-- Name: identity_serial fk_identity_serial__customer_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial
    ADD CONSTRAINT fk_identity_serial__customer_id FOREIGN KEY (customer_id) REFERENCES public.identity_customer(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_serial__customer_id ON identity_serial; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_serial__customer_id ON public.identity_serial IS 'django-name:identity_serial_customer_id_30049b4d_fk_identity_customer_id';


--
-- Name: identity_serial fk_identity_serial__product_code_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial
    ADD CONSTRAINT fk_identity_serial__product_code_id FOREIGN KEY (product_code_id) REFERENCES public.identity_product_code(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_serial__product_code_id ON identity_serial; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_serial__product_code_id ON public.identity_serial IS 'django-name:identity_serial_product_code_id_35da9ecc_fk_identity_';


--
-- Name: identity_serial fk_identity_serial__serial_counter_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial
    ADD CONSTRAINT fk_identity_serial__serial_counter_id FOREIGN KEY (serial_counter_id) REFERENCES public.identity_serial_counter(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_serial__serial_counter_id ON identity_serial; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_serial__serial_counter_id ON public.identity_serial IS 'django-name:identity_serial_serial_counter_id_f7f158d5_fk_identity_';


--
-- Name: identity_serial fk_identity_serial__style_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial
    ADD CONSTRAINT fk_identity_serial__style_id FOREIGN KEY (style_id) REFERENCES public.identity_style(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_serial__style_id ON identity_serial; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_serial__style_id ON public.identity_serial IS 'django-name:identity_serial_style_id_73d0b8b8_fk_identity_style_id';


--
-- Name: identity_serial fk_identity_serial__style_revision_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial
    ADD CONSTRAINT fk_identity_serial__style_revision_id FOREIGN KEY (style_revision_id) REFERENCES public.identity_style_revision(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_serial__style_revision_id ON identity_serial; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_serial__style_revision_id ON public.identity_serial IS 'django-name:identity_serial_style_revision_id_c42dafcb_fk_identity_';


--
-- Name: identity_serial_snapshot fk_identity_serial_snapshot__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial_snapshot
    ADD CONSTRAINT fk_identity_serial_snapshot__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_serial_snapshot__created_by_id ON identity_serial_snapshot; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_serial_snapshot__created_by_id ON public.identity_serial_snapshot IS 'django-name:identity_serial_snap_created_by_id_f92eb133_fk_platform_';


--
-- Name: identity_serial_snapshot fk_identity_serial_snapshot__serial_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_serial_snapshot
    ADD CONSTRAINT fk_identity_serial_snapshot__serial_id FOREIGN KEY (serial_id) REFERENCES public.identity_serial(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_serial_snapshot__serial_id ON identity_serial_snapshot; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_serial_snapshot__serial_id ON public.identity_serial_snapshot IS 'django-name:identity_serial_snap_serial_id_1bdb6a4f_fk_identity_';


--
-- Name: identity_style fk_identity_style__category_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style
    ADD CONSTRAINT fk_identity_style__category_id FOREIGN KEY (category_id) REFERENCES public.identity_product_class(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_style__category_id ON identity_style; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_style__category_id ON public.identity_style IS 'django-name:identity_style_category_id_f07f9058_fk_identity_';


--
-- Name: identity_style fk_identity_style__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style
    ADD CONSTRAINT fk_identity_style__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_style__created_by_id ON identity_style; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_style__created_by_id ON public.identity_style IS 'django-name:identity_style_created_by_id_f0dd2b6a_fk_platform_user_id';


--
-- Name: identity_style fk_identity_style__import_batch_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style
    ADD CONSTRAINT fk_identity_style__import_batch_id FOREIGN KEY (import_batch_id) REFERENCES public.platform_import_batch(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_style__import_batch_id ON identity_style; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_style__import_batch_id ON public.identity_style IS 'django-name:identity_style_import_batch_id_91bab762_fk_platform_';


--
-- Name: identity_style fk_identity_style__product_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style
    ADD CONSTRAINT fk_identity_style__product_id FOREIGN KEY (product_id) REFERENCES public.identity_product(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_style__product_id ON identity_style; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_style__product_id ON public.identity_style IS 'django-name:identity_style_product_id_b507aaf9_fk_identity_product_id';


--
-- Name: identity_style fk_identity_style__staging_row_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style
    ADD CONSTRAINT fk_identity_style__staging_row_id FOREIGN KEY (staging_row_id) REFERENCES public.platform_import_staging_row(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_style__staging_row_id ON identity_style; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_style__staging_row_id ON public.identity_style IS 'django-name:identity_style_staging_row_id_f7be49c2_fk_platform_';


--
-- Name: identity_style fk_identity_style__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style
    ADD CONSTRAINT fk_identity_style__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_style__updated_by_id ON identity_style; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_style__updated_by_id ON public.identity_style IS 'django-name:identity_style_updated_by_id_b5fa8afa_fk_platform_user_id';


--
-- Name: identity_style_revision fk_identity_style_revision__created_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style_revision
    ADD CONSTRAINT fk_identity_style_revision__created_by_id FOREIGN KEY (created_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_style_revision__created_by_id ON identity_style_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_style_revision__created_by_id ON public.identity_style_revision IS 'django-name:identity_style_revis_created_by_id_ddbfddfc_fk_platform_';


--
-- Name: identity_style_revision fk_identity_style_revision__style_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style_revision
    ADD CONSTRAINT fk_identity_style_revision__style_id FOREIGN KEY (style_id) REFERENCES public.identity_style(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_style_revision__style_id ON identity_style_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_style_revision__style_id ON public.identity_style_revision IS 'django-name:identity_style_revision_style_id_9bc810b6_fk_identity_style_id';


--
-- Name: identity_style_revision fk_identity_style_revision__updated_by_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_style_revision
    ADD CONSTRAINT fk_identity_style_revision__updated_by_id FOREIGN KEY (updated_by_id) REFERENCES public.platform_user(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: CONSTRAINT fk_identity_style_revision__updated_by_id ON identity_style_revision; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON CONSTRAINT fk_identity_style_revision__updated_by_id ON public.identity_style_revision IS 'django-name:identity_style_revis_updated_by_id_98e6dcf6_fk_platform_';


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


