"""PHASE_01 / 01.2 schema contract: naming, triggers, state CHECKs vs the API contract, seed integrity.

Traceability: the seeded permission matrix is compared cell by cell with
docs/security/PERMISSION_MATRIX_DRAFT.md (APPROVED v1.0, DEC-049) and with every ``x-aleekhan-permission`` /
``x-aleekhan-mfa-step-up`` of the contract.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest
from django.db import connection

from platform_core.identity.models import Permission, Role, RolePermission
from platform_core.params.models import ParameterValue

from . import openapi_contract as oc
from .test_schema import PHASE01_TABLES

pytestmark = pytest.mark.django_db
REPO = Path(__file__).resolve().parents[3]
MATRIX_DOC = REPO / "docs" / "security" / "PERMISSION_MATRIX_DRAFT.md"
ROLE_COLUMNS = {
    "OA": "owner_admin",
    "IT": "it_ops",
    "AUD": "security_auditor",
    "MGT": "management_viewer",
    "EMP": "employee",
    "MGR": "unit_manager",
    "DOCC": "document_controller",
    "DOCA": "document_approver",
    "CFGA": "config_approver",
    "APR": "workflow_approver",
    "OPT": "operator_terminal",
}
# matrix v2.0 (DEC-057, docs/security/PERMISSION_MATRIX_DRAFT.md section 7)
PHASE02_ROLE_COLUMNS = {
    "CO": "commercial_officer",
    "CM": "commercial_manager",
    "PO": "planning_officer",
    "PDS": "product_data_steward",
    "CRA": "code_rule_approver",
}


def _rows(sql: str, params: list[Any] | None = None) -> list[tuple[object, ...]]:
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        return list(cur.fetchall())


# ------------------------------------------------------------------------------------------ naming
def test_constraint_and_index_names_follow_convention() -> None:
    prefix = {"c": "ck_", "f": "fk_", "u": "uq_", "x": "ex_"}
    bad = []
    for name, table, kind in _rows(
        "SELECT c.conname, t.relname, c.contype FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
        "WHERE t.relname = ANY(%s)",
        [PHASE01_TABLES],
    ):
        ok = str(name).endswith("_pkey") if kind == "p" else str(name).startswith(prefix.get(str(kind), "?"))
        if not ok:
            bad.append((table, name))
    for name, table in _rows(
        "SELECT indexname, tablename FROM pg_indexes WHERE schemaname = 'public' AND tablename = ANY(%s)",
        [PHASE01_TABLES],
    ):
        if not re.match(r"^(ix|uq|ex)_|.*_pkey$", str(name)):
            bad.append((table, name))
    assert bad == []


def test_timestamps_are_timestamptz_and_codes_are_strings() -> None:
    types = {
        (t, c): d
        for t, c, d in _rows(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ANY(%s)",
            [PHASE01_TABLES],
        )
    }
    stamps = {d for (t, c), d in types.items() if str(c).endswith(("_at", "_from", "_to", "_until"))}
    assert stamps == {"timestamp with time zone"}
    for col in (("platform_user", "username"), ("platform_org_unit", "code"), ("platform_role", "code")):
        assert types[col] == "character varying"


def test_every_versioned_table_bumps_row_version_and_all_triggers_enabled() -> None:
    versioned = {
        str(t)
        for (t,) in _rows(
            "SELECT table_name FROM information_schema.columns WHERE column_name = 'row_version' "
            "AND table_name = ANY(%s)",
            [PHASE01_TABLES],
        )
    }
    touched = {
        str(t)
        for (t,) in _rows(
            "SELECT c.relname FROM pg_trigger g JOIN pg_class c ON c.oid = g.tgrelid "
            "WHERE NOT g.tgisinternal AND g.tgname LIKE 'trg\\_%%\\_touch'"
        )
    }
    assert versioned and versioned <= touched
    disabled = _rows(
        "SELECT g.tgname FROM pg_trigger g JOIN pg_class c ON c.oid = g.tgrelid "
        "WHERE NOT g.tgisinternal AND c.relname LIKE 'platform\\_%%' AND g.tgenabled <> 'O'"
    )
    assert disabled == []


def test_append_only_tables_have_mutation_guards() -> None:
    guarded = defaultdict(set)
    for table, name in _rows(
        "SELECT c.relname, g.tgname FROM pg_trigger g JOIN pg_class c ON c.oid = g.tgrelid "
        "WHERE NOT g.tgisinternal"
    ):
        guarded[str(table)].add(str(name))
    for table in (
        "platform_password_history",
        "platform_workflow_step_event",
        "platform_audit_integrity_run",
        "platform_login_attempt",
        "platform_org_unit_history",
        "platform_position_history",
        "platform_break_glass_usage",
        "platform_stored_object",
    ):
        assert any("append_only" in n or n.endswith("_guard") for n in guarded[table]), table


# ------------------------------------------------------------------------------------------ states
def _check_values(table: str, column: str) -> set[str]:
    defs = [
        str(d)
        for (d,) in _rows(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = %s AND c.contype = 'c' AND c.conname = %s",
            [table, f"ck_{table.removeprefix('platform_')}_{column}"],
        )
    ]
    assert len(defs) == 1, (table, column)
    return set(re.findall(r"'([A-Z_]+)'::character varying", defs[0])) - {""}


STATE_COLUMNS = [
    # (table, check suffix, OpenAPI schema, property)  - STATE_TRANSITIONS section 4
    ("platform_user", "status", "User", "status"),
    ("platform_session", "state", "SessionInfo", "state"),
    ("platform_session", "zone", "SessionInfo", "network_zone"),
    ("platform_role", "status", "Role", "status"),
    ("platform_role", "kind", "Role", "kind"),
    ("platform_role_assignment", "status", "RoleAssignment", "status"),
    ("platform_org_unit", "status", "OrgUnit", "status"),
    ("platform_position", "status", "Position", "status"),
    ("platform_position_assignment", "kind", "PositionAssignment", "kind"),
    ("platform_work_task", "status", "Task", "status"),
    ("platform_work_task", "assignee_kind", "Assignee", "kind"),
    ("platform_approval_request", "status", "Approval", "status"),
    ("platform_workflow_definition", "status", "WorkflowDefinition", "status"),
    ("platform_workflow_instance", "status", "WorkflowInstance", "status"),
    ("platform_job_run", "state", "Job", "state"),
    ("platform_document_revision", "status", "DocumentRevision", "status"),
    ("platform_document_revision", "scan", "DocumentRevision", "scan_status"),
    ("platform_parameter_value", "status", "ParameterValueRevision", "status"),
    ("platform_parameter_definition", "classification", "Parameter", "classification"),
    ("platform_user", "account_kind", "User", "account_kind"),
]


@pytest.mark.parametrize(("table", "column", "schema", "prop"), STATE_COLUMNS)
def test_state_checks_equal_contract_enums(table: str, column: str, schema: str, prop: str) -> None:
    enum = set(oc.spec()["components"]["schemas"][schema]["properties"][prop]["enum"])
    assert _check_values(table, column) == enum


# ------------------------------------------------------------------------------------------ seed
def _contract_permissions() -> dict[str, set[bool]]:
    """Permissions of the IMPLEMENTED operations. 0.7.0-draft (02.1): planned PHASE_02 operations carry
    proposed permission ids (DEC-057 OPEN) that are seeded only by the reviewed migration of 02.2."""
    flags: dict[str, set[bool]] = defaultdict(set)
    for _path, _method, op in oc.operations(planned=False):
        perm = op.get("x-aleekhan-permission")
        if perm and perm.startswith("platform."):  # PHASE_02 rows: test_api_phase02_contract.py
            flags[perm].add(bool(op.get("x-aleekhan-mfa-step-up", False)))
    return flags


def test_seeded_permissions_equal_contract_permissions_and_mfa_flags() -> None:
    """Platform permissions (matrix v1.x) = the implemented operations; the PHASE_02 rows of matrix v2.0
    (0022)
    are compared with the planned operations in test_api_phase02_contract.py."""
    contract = _contract_permissions()
    seeded = {p.action: p.mfa_step_up for p in Permission.objects.filter(action__startswith="platform.")}
    assert len(seeded) == 43
    assert set(seeded) == set(contract)
    assert {a: {m} for a, m in seeded.items()} == dict(contract)


def _matrix_doc() -> dict[str, tuple[set[str], dict[str, tuple[str, str]]]]:
    """Parse section 3 of the approved matrix: permission -> (flags, {role_code: (mode, max_sensitivity)})."""
    lines = MATRIX_DOC.read_text(encoding="utf-8").splitlines()
    header_idx = next(
        i for i, ln in enumerate(lines) if ln.startswith("| Permission (`x-aleekhan-permission`)")
    )
    header = [c.strip() for c in lines[header_idx].strip("|").split("|")]
    out = {}
    for ln in lines[header_idx + 2 :]:
        if not ln.startswith("| platform."):
            break
        cells = [c.strip() for c in ln.strip("|").split("|")]
        row = dict(zip(header, cells, strict=True))
        action = row[header[0]]
        flags = set(re.findall(r"\b(MFA|BA|SoD)\b", row["Flags"]))
        grants = {}
        for col, code in ROLE_COLUMNS.items():
            cell = row[col]
            if cell.startswith("—"):
                continue
            sens = "S2" if "S1–S2" in cell else "S1" if "(S1)" in cell else ""  # noqa: RUF001 - doc en dash
            if cell.startswith("●"):
                mode = "OWN_UNIT" if "own unit" in cell else "SCOPE"
            elif cell.startswith("○"):
                mode = "OWN_AND_OWN_UNIT" if "+ own unit" in cell else "OWN"
            else:
                raise AssertionError(f"unparsed matrix cell {cell!r} ({action}/{col})")
            grants[code] = (mode, sens)
        out[action] = (flags, grants)
    return out


def test_seeded_grants_equal_the_approved_matrix_document() -> None:
    doc = _matrix_doc()
    assert len(doc) == 43
    seeded: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    for rp in RolePermission.objects.select_related("role"):
        seeded[rp.permission_id][rp.role.code] = (rp.grant_mode, rp.max_sensitivity)
    for action, (flags, grants) in doc.items():
        assert seeded[action] == grants, action
        p = Permission.objects.get(action=action)
        assert (p.mfa_step_up, p.business_approval, p.maker_checker) == (
            "MFA" in flags,
            "BA" in flags,
            "SoD" in flags,
        )


def test_matrix_document_is_approved_v2_0() -> None:
    head = MATRIX_DOC.read_text(encoding="utf-8")[:700]
    assert "APPROVED v2.0" in head and "DEC-049" in head and "DEC-056" in head and "DEC-057" in head
    text = MATRIX_DOC.read_text(encoding="utf-8")
    assert "0017_dec056_matrix_v13" in text and "0022_dec057_matrix_v20" in text


def test_roles_seeded_active_v1_and_technical_roles_have_no_business_approval() -> None:
    roles = {r.code: r for r in Role.objects.all()}
    assert set(roles) == set(ROLE_COLUMNS.values()) | set(PHASE02_ROLE_COLUMNS.values())
    assert {r.status for r in roles.values()} == {"ACTIVE"}
    # DEC-056 (+ extensions): owner_admin moved v1.1 -> v1.2 -> v1.3; DEC-057 (matrix v2.0, 0022) moved
    # owner_admin and management_viewer to 2.0 and added five BUSINESS roles at 2.0; the rest keep v1.0;
    # matrix v2.1 (0024, amendments 2026-11-12) moved owner_admin (PHASE_02 reads) and planning_officer
    # (due-date planning approval) to 2.1
    changed = {c: r.matrix_version for c, r in roles.items() if r.matrix_version != "1.0"}
    assert changed == {
        "management_viewer": "2.0",
        **{code: "2.0" for code in PHASE02_ROLE_COLUMNS.values()},
        "owner_admin": "2.1",
        "planning_officer": "2.1",
    }
    technical = {c for c, r in roles.items() if r.kind == "TECHNICAL"}
    assert technical == {"owner_admin", "it_ops", "security_auditor"}
    # the explicit exception of DEC-003 (DEC-056 matrix v1.2 + DEC-057 matrix v2.0): owner_admin + exactly six
    ba_technical = set(
        RolePermission.objects.filter(role__kind="TECHNICAL", permission__business_approval=True).values_list(
            "role__code", "permission_id"
        )
    )
    assert ba_technical == {
        ("owner_admin", "platform.workflow.approval.decide"),
        ("owner_admin", "platform.document.approve"),
        ("owner_admin", "platform.config.parameter.publish"),
        ("owner_admin", "identity.code_rule.approve"),
        ("owner_admin", "commercial.order.confirm"),
        ("owner_admin", "commercial.change.decide"),
    }


EXPECTED_PARAMETERS = {
    # DEC-051
    "password_min_length": ("8", "DEC-051"),
    "password_require_uppercase": ("true", "DEC-051"),
    "password_require_digit": ("true", "DEC-051"),
    "password_require_symbol": ("true", "DEC-051"),
    "password_max_age_days": ("90", "DEC-051"),
    "password_initial_validity_hours": ("72", "DEC-051"),
    "password_change_at_first_login": ("true", "DEC-051"),
    "lockout_max_failures": ("5", "DEC-051"),
    "lockout_window_minutes": ("15", "DEC-051"),
    "lockout_duration_minutes": ("15", "DEC-051"),
    "session_user_idle_minutes": ("120", "DEC-051"),
    "session_user_absolute_hours": ("12", "DEC-051"),
    "session_operator_idle_minutes": ("480", "DEC-051"),
    "session_operator_internal_only": ("true", "DEC-051"),
    "session_max_concurrent": ("3", "DEC-051"),
    # employer answers 2026-11-05 (Q-0101 / Q-0102 / Q-0105)
    "session_limit_exceeded_action": ("END_OLDEST_SESSION", "DEC-051"),
    "session_operator_absolute_hours": ("12", "DEC-051"),
    "password_history_reuse_depth": ("5", "DEC-051"),
    "mfa_step_up_window_minutes": ("15", "DEC-051"),
    # DEC-049 / DEC-050 / DEC-052 / DEC-054
    "mfa_step_up_inside_network": ("true", "DEC-049"),
    "mfa_method": ("TOTP", "DEC-050"),
    "mfa_recovery_code_count": ("10", "DEC-050"),
    "network_unknown_is_external": ("true", "DEC-052"),
    "network_vpn_is_external": ("true", "DEC-052"),
    "break_glass_session_hours": ("2", "DEC-054"),
    # DEC-053
    "document_upload_max_bytes": ("26214400", "DEC-053"),
    "document_rejected_quarantine_days": ("30", "DEC-053"),
    "document_scanner": ("CLAMAV", "DEC-053"),
    # DEC-032 / DEC-048
    "approval_request_expiry_days": ("30", "DEC-032"),
    "retention_login_events_months": ("24", "DEC-032"),
    "retention_business_audit": ("KEEP_FOREVER_YEARLY_ARCHIVE", "DEC-032"),
    "org_tree_max_depth": ("6", "DEC-048"),
}


def test_seeded_parameters_carry_decision_values_and_provenance() -> None:
    seeded = {
        v.definition_id: (v.value, v.decision_id)
        for v in ParameterValue.objects.filter(provenance="MIGRATION_SEED").select_related("definition")
    }
    assert seeded == EXPECTED_PARAMETERS
    for v in ParameterValue.objects.filter(provenance="MIGRATION_SEED").select_related("definition"):
        assert v.status == "PUBLISHED" and v.definition.decision_id == v.decision_id
        assert v.definition.classification == "OWNER_POLICY"
    answered = ParameterValue.objects.filter(
        definition_id__in=[
            "session_limit_exceeded_action",
            "session_operator_absolute_hours",
            "password_history_reuse_depth",
        ]
    )
    assert {v.reason for v in answered} == {
        "DEC-051 (employer answer Q-0101/Q-0102/Q-0105, 2026-11-05) (seeded by migration 0010)"
    }


def test_seed_is_non_sensitive() -> None:
    """No users, org data, sessions, documents or network ranges are seeded (C-45, DEC-052)."""
    for table in (
        "platform_user",
        "platform_org_unit",
        "platform_position",
        "platform_role_assignment",
        "platform_session",
        "platform_document",
        "platform_stored_object",
    ):
        assert _rows(f"SELECT count(*) FROM {table}")[0][0] == 0, table  # noqa: S608 - fixed table names
    values = [str(v) for (v,) in _rows("SELECT value FROM platform_parameter_value")]
    cidr = re.compile(r"\b\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?\b")
    assert not [v for v in values if cidr.search(v)]


def test_upload_limit_carries_the_q0104_answer() -> None:
    v = ParameterValue.objects.get(definition_id="document_upload_max_bytes", provenance="MIGRATION_SEED")
    assert v.reason == "DEC-053 (employer answer Q-0104, 2026-11-05) (seeded by migration 0010)"
