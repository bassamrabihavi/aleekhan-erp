"""PHASE_02 / 02.2 database guards (reversible). Design: docs/db/ERD.md section 7 "PHASE_02 guards".

Defence in depth under the 02.3 engine: the database refuses states the decisions forbid, even if application
code is wrong. Same conventions as 0008: fixed ``search_path``, tables qualified with ``public.``, immutability /
append-only -> SQLSTATE 23001 (restrict_violation), invariant -> 23514 (check_violation); the rule name is always
in the message. Generic functions of 0002/0008 are reused (``platform_touch_row``, ``platform_bump_row``,
``platform_reject_mutation``, ``platform_reject_terminal_update``, ``platform_immutable_columns``,
``platform_close_once_only``).

1. Row version / ``updated_at`` on every mutable table; no DELETE on any PHASE_02 business table (history is
   never removed: status ends instead). Append-only: ``identity_serial_snapshot``,
   ``commercial_customer_order_version``. Immutable key columns per table. Terminal states immutable.
2. Classification (DEC-005): a category hangs under a product type; a product belongs to a product type; a style
   pairs a product with a category of the same type; belt types require buckle + width. Code segments never
   change once written.
3. Product code registry (DEC-005, INV-02-07): a system-issued code needs an ACTIVE rule revision; a live code
   linked to a style equals ``02`` + the style's four segments; the style link is set once.
4. Serial (DEC-006, ID-02/03/04, INV-02-02/04/05): the counter moves by exactly +1 per allocation and its fixed
   columns never change; a serial number must have been drawn from the counter (start <= value < next);
   ALLOCATED -> CANCELLED only; snapshot versions are contiguous. **Deferred constraint triggers** (checked at
   COMMIT, so the allocation order inside the transaction is free): every counter step has its serial (gapless),
   every serial has its snapshot v1 and exactly one Commercial order line (REV-0201 pairing check).
5. Legacy (DEC-006 P-A): a plain-integer legacy serial must be below ``legacy_max_exclusive`` (63000) of the
   counter - the import must route a violation to the conflict queue (it cannot be stored). Legacy rows change
   only in their match columns and the duplicate flag.
6. Commercial (DEC-057/058/059): order status graph (single ON_HOLD resuming to the stored previous state;
   cancel only before release); confirmer != creator (CHECK); confirmed header data frozen except the due date
   with a version bump; after release only due date and hold/resume; brand of the same customer; line uom = the
   product type's unit (DEC-058); a CONFIRMED line changes only with the order's version bump; order versions
   contiguous; at COMMIT a confirmed order has no OPEN line and its ``current_version`` row exists; change
   requests only on confirmed orders, kinds after release limited (DEC-059), content frozen after DRAFT, APPLIED
   needs the matching new order version (deferred).
7. Every Django-generated FK / unique / index name of the PHASE_02 tables gets the ``fk_``/``uq_``/``ix_``
   convention (exactly reversible, same mechanism as 0009).

Frozen data: this file must not import application code.
"""

import hashlib
from typing import Any

from django.db import migrations

IDENTITY_TOUCH = (
    "identity_customer",
    "identity_customer_brand",
    "identity_product_class",
    "identity_product",
    "identity_style",
    "identity_style_revision",
    "identity_code_rule_revision",
    "identity_product_code",
    "identity_serial_counter",
    "identity_external_ref_type",
    "identity_external_ref",
    "identity_historical_order_record",
    "commercial_customer_order",
    "commercial_customer_order_line",
    "commercial_order_change_request",
)
BUMP = ("identity_serial",)
APPEND_ONLY = ("identity_serial_snapshot", "commercial_customer_order_version")
NO_DELETE = (
    *IDENTITY_TOUCH,
    *BUMP,
    "identity_code_rule_golden_case",
)
TERMINAL = {
    "identity_style_revision": ("status", "SUPERSEDED"),
    "identity_code_rule_revision": ("status", "RETIRED", "REJECTED"),
    "identity_serial": ("status", "CANCELLED"),
    "commercial_customer_order": ("status", "CANCELLED"),
    "commercial_customer_order_line": ("status", "REMOVED", "CANCELLED"),
    "commercial_order_change_request": ("status", "APPLIED", "REJECTED", "WITHDRAWN", "EXPIRED"),
}
IMMUTABLE = {
    "identity_customer": ("id", "customer_no", "provenance_kind", "import_batch_id", "staging_row_id"),
    "identity_customer_brand": ("id", "customer_id"),
    "identity_product_class": ("id", "level_key", "parent_id", "segment_value"),
    "identity_product": ("id", "product_type_id", "product_no", "buckle_type_code", "belt_width_code"),
    "identity_style": ("id", "product_id", "category_id", "style_no"),
    "identity_style_revision": ("id", "style_id", "revision_no"),
    "identity_code_rule_revision": ("id", "code_namespace", "revision_no", "created_by_id"),
    "identity_product_code": (
        "id",
        "code",
        "code_namespace",
        "rule_revision_id",
        "issue_idempotency_key",
        "issued_by_id",
        "issued_at",
        "provenance_kind",
    ),
    "identity_serial_counter": (
        "id",
        "namespace_key",
        "start_value",
        "legacy_max_exclusive",
        "number_pattern",
        "decision_id",
    ),
    "identity_serial": (
        "id",
        "serial_counter_id",
        "serial_number",
        "serial_value",
        "customer_id",
        "style_id",
        "allocation_idempotency_key",
        "allocated_by_id",
        "allocated_at",
    ),
    "identity_external_ref_type": ("key",),
    "identity_external_ref": ("id", "target_type", "target_id", "system", "namespace", "value"),
    "commercial_customer_order": ("id", "order_no", "created_by_id"),
    "commercial_customer_order_line": ("id", "order_id", "line_no", "style_id"),
    "commercial_order_change_request": ("id", "request_no", "order_id", "requested_by_id"),
}


def _generic_sql() -> tuple[str, str]:
    fwd, rev = [], []

    def add(name: str, table: str, when: str, call: str) -> None:
        fwd.append(f"CREATE TRIGGER {name} {when} ON public.{table} FOR EACH ROW EXECUTE FUNCTION {call};")
        rev.append(f"DROP TRIGGER IF EXISTS {name} ON public.{table};")

    for t in IDENTITY_TOUCH:
        add(f"trg_{t}_touch", t, "BEFORE UPDATE", "platform_touch_row()")
    for t in BUMP:
        add(f"trg_{t}_touch", t, "BEFORE UPDATE", "platform_bump_row()")
    for t in NO_DELETE:
        add(f"trg_{t}_no_delete", t, "BEFORE DELETE", "platform_reject_mutation()")
    for t in APPEND_ONLY:
        add(f"trg_{t}_append_only", t, "BEFORE UPDATE OR DELETE", "platform_reject_mutation()")
    add(
        "trg_identity_code_rule_golden_case_close_once",
        "identity_code_rule_golden_case",
        "BEFORE UPDATE",
        "platform_close_once_only('verified_by_id', 'verified_at')",
    )
    for t, (col, *states) in TERMINAL.items():
        args = ", ".join(f"'{a}'" for a in (col, *states))
        # "a_" prefix: fires first (BEFORE triggers run in name order)
        add(f"trg_{t}_a_terminal", t, "BEFORE UPDATE", f"platform_reject_terminal_update({args})")
    for t, cols in IMMUTABLE.items():
        args = ", ".join(f"'{c}'" for c in cols)
        add(f"trg_{t}_b_immutable", t, "BEFORE UPDATE", f"platform_immutable_columns({args})")
    return "\n".join(fwd), "\n".join(reversed(rev))


GENERIC_FWD, GENERIC_REV = _generic_sql()

GUARDS_SQL = r"""
-- ------------------------------------------------------------------------------------ classification (DEC-005)
CREATE FUNCTION identity_product_class_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_identity_product_class_guard BEFORE INSERT OR UPDATE ON public.identity_product_class
    FOR EACH ROW EXECUTE FUNCTION identity_product_class_guard();

CREATE FUNCTION identity_product_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_identity_product_guard BEFORE INSERT OR UPDATE ON public.identity_product
    FOR EACH ROW EXECUTE FUNCTION identity_product_guard();

CREATE FUNCTION identity_style_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_identity_style_guard BEFORE INSERT OR UPDATE ON public.identity_style
    FOR EACH ROW EXECUTE FUNCTION identity_style_guard();

-- an ACTIVE revision is immutable except ACTIVE -> SUPERSEDED (SUPERSEDED is terminal)
CREATE FUNCTION identity_style_revision_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_identity_style_revision_guard BEFORE UPDATE ON public.identity_style_revision
    FOR EACH ROW EXECUTE FUNCTION identity_style_revision_guard();

-- --------------------------------------------------------------------------------- code rule (DEC-005 Q-A)
CREATE FUNCTION identity_code_rule_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_identity_code_rule_revision_guard BEFORE INSERT OR UPDATE ON public.identity_code_rule_revision
    FOR EACH ROW EXECUTE FUNCTION identity_code_rule_guard();

-- ------------------------------------------------------------------------------ product codes (DEC-005, B1)
CREATE FUNCTION identity_product_code_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_identity_product_code_guard BEFORE INSERT OR UPDATE ON public.identity_product_code
    FOR EACH ROW EXECUTE FUNCTION identity_product_code_guard();

-- ------------------------------------------------------------------------------------ serial (DEC-006 G-B)
CREATE FUNCTION identity_serial_counter_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_identity_serial_counter_guard BEFORE INSERT OR UPDATE ON public.identity_serial_counter
    FOR EACH ROW EXECUTE FUNCTION identity_serial_counter_guard();

-- at COMMIT: every number the counter gave out belongs to a serial (no gap, DEC-006 G-B)
CREATE FUNCTION identity_serial_counter_gapless() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
BEGIN
    IF NEW.next_value > OLD.next_value AND NOT EXISTS (
        SELECT 1 FROM public.identity_serial s
         WHERE s.serial_counter_id = NEW.id AND s.serial_value = OLD.next_value) THEN
        RAISE EXCEPTION 'ck_identity_serial_counter_gapless: number % was drawn but no serial holds it', OLD.next_value
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END;
$fn$;
CREATE CONSTRAINT TRIGGER trg_identity_serial_counter_gapless AFTER UPDATE ON public.identity_serial_counter
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION identity_serial_counter_gapless();

CREATE FUNCTION identity_serial_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_identity_serial_guard BEFORE INSERT OR UPDATE ON public.identity_serial
    FOR EACH ROW EXECUTE FUNCTION identity_serial_guard();

-- at COMMIT: a serial has its snapshot v1 (INV-02-04) and exactly one Commercial line points to it (REV-0201)
CREATE FUNCTION identity_serial_committed() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE CONSTRAINT TRIGGER trg_identity_serial_committed AFTER INSERT ON public.identity_serial
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION identity_serial_committed();

CREATE FUNCTION identity_serial_snapshot_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_identity_serial_snapshot_guard BEFORE INSERT ON public.identity_serial_snapshot
    FOR EACH ROW EXECUTE FUNCTION identity_serial_snapshot_guard();

-- --------------------------------------------------------------------------------- legacy history (DEC-006)
CREATE FUNCTION identity_historical_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_identity_historical_order_record_guard BEFORE INSERT OR UPDATE ON public.identity_historical_order_record
    FOR EACH ROW EXECUTE FUNCTION identity_historical_guard();

-- ------------------------------------------------------------------------------- commercial order (DEC-059)
CREATE FUNCTION commercial_order_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
            OR (OLD.status = 'CONFIRMED' AND NEW.status = 'CANCELLED' AND step = 1), false) THEN
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
$fn$;
CREATE TRIGGER trg_commercial_customer_order_guard BEFORE INSERT OR UPDATE ON public.commercial_customer_order
    FOR EACH ROW EXECUTE FUNCTION commercial_order_guard();

-- at COMMIT: a versioned order has its current version row (and none above it); a confirmed order has no OPEN
-- line and at least one confirmed/cancelled line (DEC-006 L-A: every line got its serial at confirm)
-- (a deferred row trigger sees the row as it was at its event: the current row is read again)
CREATE FUNCTION commercial_order_committed() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE CONSTRAINT TRIGGER trg_commercial_customer_order_committed AFTER INSERT OR UPDATE ON public.commercial_customer_order
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION commercial_order_committed();

CREATE FUNCTION commercial_line_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_commercial_customer_order_line_guard BEFORE INSERT OR UPDATE ON public.commercial_customer_order_line
    FOR EACH ROW EXECUTE FUNCTION commercial_line_guard();

CREATE FUNCTION commercial_order_version_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE TRIGGER trg_commercial_customer_order_version_guard BEFORE INSERT ON public.commercial_customer_order_version
    FOR EACH ROW EXECUTE FUNCTION commercial_order_version_guard();

-- at COMMIT: a line is CANCELLED exactly when its serial is CANCELLED (DEC-059; each module writes its own row)
CREATE FUNCTION phase02_line_serial_cancel_paired() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE CONSTRAINT TRIGGER trg_commercial_customer_order_line_cancel_paired AFTER UPDATE ON public.commercial_customer_order_line
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION phase02_line_serial_cancel_paired();
CREATE CONSTRAINT TRIGGER trg_identity_serial_cancel_paired AFTER UPDATE ON public.identity_serial
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION phase02_line_serial_cancel_paired();

-- ------------------------------------------------------------------------------ change requests (DEC-059)
CREATE FUNCTION commercial_change_request_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
        OR (OLD.status = 'APPROVED' AND NEW.status IN ('APPLIED', 'EXPIRED'))) THEN
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
$fn$;
CREATE TRIGGER trg_commercial_order_change_request_guard BEFORE INSERT OR UPDATE ON public.commercial_order_change_request
    FOR EACH ROW EXECUTE FUNCTION commercial_change_request_guard();

-- at COMMIT: an APPLIED request has written exactly its new order version (INV-02-06)
CREATE FUNCTION commercial_change_request_applied() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;
CREATE CONSTRAINT TRIGGER trg_commercial_order_change_request_applied AFTER UPDATE ON public.commercial_order_change_request
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION commercial_change_request_applied();
"""

GUARDS_REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS trg_commercial_order_change_request_applied ON public.commercial_order_change_request;
DROP FUNCTION IF EXISTS commercial_change_request_applied();
DROP TRIGGER IF EXISTS trg_commercial_order_change_request_guard ON public.commercial_order_change_request;
DROP FUNCTION IF EXISTS commercial_change_request_guard();
DROP TRIGGER IF EXISTS trg_identity_serial_cancel_paired ON public.identity_serial;
DROP TRIGGER IF EXISTS trg_commercial_customer_order_line_cancel_paired ON public.commercial_customer_order_line;
DROP FUNCTION IF EXISTS phase02_line_serial_cancel_paired();
DROP TRIGGER IF EXISTS trg_commercial_customer_order_version_guard ON public.commercial_customer_order_version;
DROP FUNCTION IF EXISTS commercial_order_version_guard();
DROP TRIGGER IF EXISTS trg_commercial_customer_order_line_guard ON public.commercial_customer_order_line;
DROP FUNCTION IF EXISTS commercial_line_guard();
DROP TRIGGER IF EXISTS trg_commercial_customer_order_committed ON public.commercial_customer_order;
DROP FUNCTION IF EXISTS commercial_order_committed();
DROP TRIGGER IF EXISTS trg_commercial_customer_order_guard ON public.commercial_customer_order;
DROP FUNCTION IF EXISTS commercial_order_guard();
DROP TRIGGER IF EXISTS trg_identity_historical_order_record_guard ON public.identity_historical_order_record;
DROP FUNCTION IF EXISTS identity_historical_guard();
DROP TRIGGER IF EXISTS trg_identity_serial_snapshot_guard ON public.identity_serial_snapshot;
DROP FUNCTION IF EXISTS identity_serial_snapshot_guard();
DROP TRIGGER IF EXISTS trg_identity_serial_committed ON public.identity_serial;
DROP FUNCTION IF EXISTS identity_serial_committed();
DROP TRIGGER IF EXISTS trg_identity_serial_guard ON public.identity_serial;
DROP FUNCTION IF EXISTS identity_serial_guard();
DROP TRIGGER IF EXISTS trg_identity_serial_counter_gapless ON public.identity_serial_counter;
DROP FUNCTION IF EXISTS identity_serial_counter_gapless();
DROP TRIGGER IF EXISTS trg_identity_serial_counter_guard ON public.identity_serial_counter;
DROP FUNCTION IF EXISTS identity_serial_counter_guard();
DROP TRIGGER IF EXISTS trg_identity_product_code_guard ON public.identity_product_code;
DROP FUNCTION IF EXISTS identity_product_code_guard();
DROP TRIGGER IF EXISTS trg_identity_code_rule_revision_guard ON public.identity_code_rule_revision;
DROP FUNCTION IF EXISTS identity_code_rule_guard();
DROP TRIGGER IF EXISTS trg_identity_style_revision_guard ON public.identity_style_revision;
DROP FUNCTION IF EXISTS identity_style_revision_guard();
DROP TRIGGER IF EXISTS trg_identity_style_guard ON public.identity_style;
DROP FUNCTION IF EXISTS identity_style_guard();
DROP TRIGGER IF EXISTS trg_identity_product_guard ON public.identity_product;
DROP FUNCTION IF EXISTS identity_product_guard();
DROP TRIGGER IF EXISTS trg_identity_product_class_guard ON public.identity_product_class;
DROP FUNCTION IF EXISTS identity_product_class_guard();
"""

# ------------------------------------------------------------------------------------- naming (as 0009)
PHASE02_TABLES = (
    "identity_unit_of_measure",
    "identity_customer",
    "identity_customer_brand",
    "identity_product_class",
    "identity_product",
    "identity_style",
    "identity_style_revision",
    "identity_code_rule_revision",
    "identity_code_rule_golden_case",
    "identity_product_code",
    "identity_serial_counter",
    "identity_serial",
    "identity_serial_snapshot",
    "identity_external_ref_type",
    "identity_external_ref",
    "identity_historical_order_record",
    "commercial_order_type",
    "commercial_customer_order",
    "commercial_customer_order_line",
    "commercial_customer_order_version",
    "commercial_order_change_request",
)
COMMENT_PREFIX = "django-name:"

CONSTRAINTS_SQL = """
SELECT c.conname, t.relname, c.contype,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum) AS cols,
       obj_description(c.oid, 'pg_constraint') AS comment
  FROM pg_constraint c
  JOIN pg_class t ON t.oid = c.conrelid
  JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = 'public'
 WHERE c.contype IN ('f', 'u') AND t.relname = ANY(%s)
 ORDER BY t.relname, c.conname
"""

INDEXES_SQL = """
SELECT ic.relname, t.relname,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(i.indkey) WITH ORDINALITY k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum) AS cols,
       obj_description(ic.oid, 'pg_class') AS comment
  FROM pg_index i
  JOIN pg_class ic ON ic.oid = i.indexrelid
  JOIN pg_class t ON t.oid = i.indrelid
  JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = 'public'
 WHERE t.relname = ANY(%s)
   AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)
 ORDER BY t.relname, ic.relname
"""


def _conventional(prefix: str, table: str, cols: list[str], suffix: str = "") -> str:
    name = f"{prefix}_{table}__{'_'.join(cols)}{suffix}"
    if len(name) > 63:
        digest = hashlib.md5(name.encode(), usedforsecurity=False).hexdigest()[:8]
        name = f"{name[: 63 - 9 - len(suffix)]}_{digest}{suffix}"
    return name


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _lit(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def rename_forward(apps: Any, schema_editor: Any) -> None:
    with schema_editor.connection.cursor() as cur:
        cur.execute(CONSTRAINTS_SQL, [list(PHASE02_TABLES)])
        for conname, table, contype, cols, _comment in cur.fetchall():
            if conname.startswith(("fk_", "uq_")):
                continue
            new = _conventional("fk" if contype == "f" else "uq", table, list(cols))
            cur.execute(f"ALTER TABLE public.{_q(table)} RENAME CONSTRAINT {_q(conname)} TO {_q(new)}")
            cur.execute(
                f"COMMENT ON CONSTRAINT {_q(new)} ON public.{_q(table)} IS {_lit(COMMENT_PREFIX + conname)}"
            )
        cur.execute(INDEXES_SQL, [list(PHASE02_TABLES)])
        for idxname, table, cols, _comment in cur.fetchall():
            if idxname.startswith(("ix_", "uq_", "ex_")):
                continue
            new = _conventional("ix", table, list(cols), "_like" if idxname.endswith("_like") else "")
            cur.execute(f"ALTER INDEX public.{_q(idxname)} RENAME TO {_q(new)}")
            cur.execute(f"COMMENT ON INDEX public.{_q(new)} IS {_lit(COMMENT_PREFIX + idxname)}")


def rename_backward(apps: Any, schema_editor: Any) -> None:
    with schema_editor.connection.cursor() as cur:
        cur.execute(CONSTRAINTS_SQL, [list(PHASE02_TABLES)])
        for conname, table, _contype, _cols, comment in cur.fetchall():
            if comment and comment.startswith(COMMENT_PREFIX):
                old = comment.removeprefix(COMMENT_PREFIX)
                cur.execute(f"COMMENT ON CONSTRAINT {_q(conname)} ON public.{_q(table)} IS NULL")
                cur.execute(f"ALTER TABLE public.{_q(table)} RENAME CONSTRAINT {_q(conname)} TO {_q(old)}")
        cur.execute(INDEXES_SQL, [list(PHASE02_TABLES)])
        for idxname, _table, _cols, comment in cur.fetchall():
            if comment and comment.startswith(COMMENT_PREFIX):
                old = comment.removeprefix(COMMENT_PREFIX)
                cur.execute(f"COMMENT ON INDEX public.{_q(idxname)} IS NULL")
                cur.execute(f"ALTER INDEX public.{_q(idxname)} RENAME TO {_q(old)}")


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0019_phase02_identity_commercial_schema"),
    ]

    operations = [
        migrations.RunSQL(sql=GENERIC_FWD, reverse_sql=GENERIC_REV),
        migrations.RunSQL(sql=GUARDS_SQL, reverse_sql=GUARDS_REVERSE_SQL),
        migrations.RunPython(rename_forward, rename_backward),
    ]
