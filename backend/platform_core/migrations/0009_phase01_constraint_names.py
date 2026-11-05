"""Give every Django-generated FK / unique constraint and index of the PHASE_01 tables a conventional name.

Django names CHECK/UNIQUE/INDEX objects declared in ``Meta`` explicitly (``ck_``/``uq_``/``ix_``), but it
generates names for foreign keys (``<table>_<col>_<hash>_fk_<target>``), for ``unique=True`` fields
(``<table>_<col>_key``) and for ``varchar_pattern_ops`` helper indexes (``..._like``). This migration renames
them to ``fk_<table>__<cols>``, ``uq_<table>__<cols>`` and ``ix_<table>__<cols>[_like]`` (``<table>`` without the
``platform_`` prefix; ``__`` marks a generated rename; >63 characters -> shortened with an md5 suffix).

Exactly reversible: the original name is stored in the object's catalog comment (``django-name:<name>``) and
the reverse renames back. Django's schema editor finds FKs/indexes by introspection (columns), not by name, so
later migrations keep working. Test: ``test_phase01_schema.py::test_constraint_and_index_names_follow_convention``.
"""

import hashlib
from typing import Any

from django.db import migrations

PHASE01_TABLES = (
    "platform_user",
    "platform_credential",
    "platform_password_history",
    "platform_mfa_factor",
    "platform_recovery_code",
    "platform_session",
    "platform_login_attempt",
    "platform_permission",
    "platform_role",
    "platform_role_permission",
    "platform_role_assignment",
    "platform_break_glass_usage",
    "platform_org_unit_type",
    "platform_org_unit",
    "platform_org_unit_history",
    "platform_position",
    "platform_position_history",
    "platform_position_assignment",
    "platform_workflow_definition",
    "platform_workflow_instance",
    "platform_workflow_step_event",
    "platform_approval_request",
    "platform_work_task",
    "platform_upload_type",
    "platform_stored_object",
    "platform_document",
    "platform_document_revision",
    "platform_parameter_definition",
    "platform_parameter_value",
    "platform_dynamic_field_definition",
    "platform_job_definition",
    "platform_job_run",
    "platform_audit_integrity_run",
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
    short = table.removeprefix("platform_")
    name = f"{prefix}_{short}__{'_'.join(cols)}{suffix}"
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
        cur.execute(CONSTRAINTS_SQL, [list(PHASE01_TABLES)])
        for conname, table, contype, cols, _comment in cur.fetchall():
            if conname.startswith(("fk_", "uq_")):
                continue
            new = _conventional("fk" if contype == "f" else "uq", table, list(cols))
            cur.execute(f"ALTER TABLE public.{_q(table)} RENAME CONSTRAINT {_q(conname)} TO {_q(new)}")
            cur.execute(
                f"COMMENT ON CONSTRAINT {_q(new)} ON public.{_q(table)} IS {_lit(COMMENT_PREFIX + conname)}"
            )
        cur.execute(INDEXES_SQL, [list(PHASE01_TABLES)])
        for idxname, table, cols, _comment in cur.fetchall():
            if idxname.startswith(("ix_", "uq_", "ex_")):
                continue
            new = _conventional("ix", table, list(cols), "_like" if idxname.endswith("_like") else "")
            cur.execute(f"ALTER INDEX public.{_q(idxname)} RENAME TO {_q(new)}")
            cur.execute(f"COMMENT ON INDEX public.{_q(new)} IS {_lit(COMMENT_PREFIX + idxname)}")


def rename_backward(apps: Any, schema_editor: Any) -> None:
    with schema_editor.connection.cursor() as cur:
        cur.execute(CONSTRAINTS_SQL, [list(PHASE01_TABLES)])
        for conname, table, _contype, _cols, comment in cur.fetchall():
            if comment and comment.startswith(COMMENT_PREFIX):
                old = comment.removeprefix(COMMENT_PREFIX)
                cur.execute(f"COMMENT ON CONSTRAINT {_q(conname)} ON public.{_q(table)} IS NULL")
                cur.execute(f"ALTER TABLE public.{_q(table)} RENAME CONSTRAINT {_q(conname)} TO {_q(old)}")
        cur.execute(INDEXES_SQL, [list(PHASE01_TABLES)])
        for idxname, _table, _cols, comment in cur.fetchall():
            if comment and comment.startswith(COMMENT_PREFIX):
                old = comment.removeprefix(COMMENT_PREFIX)
                cur.execute(f"COMMENT ON INDEX public.{_q(idxname)} IS NULL")
                cur.execute(f"ALTER INDEX public.{_q(idxname)} RENAME TO {_q(old)}")


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0008_phase01_db_guards"),
    ]

    operations = [
        migrations.RunPython(rename_forward, rename_backward),
    ]
