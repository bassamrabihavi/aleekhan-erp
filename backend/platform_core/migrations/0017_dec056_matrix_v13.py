"""DEC-056 extension 2 (employer 2026-11-10, answer to the 01.6 question): permission matrix v1.3
(reversible, additive seed).

The owner role ``owner_admin`` (TECHNICAL) now also holds, directly:

* ``platform.document.read`` (``SCOPE``, no sensitivity cap; documents carry no org unit in PHASE_01 and the
  owner's assignment is GLOBAL -> every document and revision, S1-S3) - so he can open a document before he
  decides it;
* ``platform.document.download`` (``SCOPE``, no cap) - the engine serves CLEAN revisions only (DEC-053) and
  every download is audited (``platform.document.download``), unchanged.

Neither permission is flagged ``business_approval`` (0010 seed: ``mfa_step_up=False, business_approval=False,
maker_checker=False``), so the DB guard ``ck_role_technical_no_business_approval`` is **not** widened: its
owner exception stays exactly the three pairs of 0015. No guard function is replaced by this migration.

Same owner-only bypass as 0014 / 0015 (grants and ``matrix_version`` of an ACTIVE role are frozen): the schema
owner disables the guard trigger for one statement inside the migration transaction; the runtime DB role
cannot (roles_check.sh).

Reverse: removes the two grants and sets ``owner_admin.matrix_version`` back to 1.2. Downloads the owner
already made stay in the audit trail (append-only).
Frozen data: this file must not import application code.
"""

from typing import Any

from django.db import migrations

MATRIX_VERSION = "1.3"
PREVIOUS_MATRIX_VERSION = "1.2"
DECISION = "DEC-056"
OWNER = "owner_admin"

# action -> {role_code: grant_mode}  (cells added by matrix v1.3; v1.2 cells = 0015 ADDED_GRANTS)
ADDED_GRANTS: dict[str, dict[str, str]] = {
    "platform.document.read": {OWNER: "SCOPE"},
    "platform.document.download": {OWNER: "SCOPE"},
}


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
        ("platform_core", "0016_outbox_provenance_and_order"),
    ]

    operations = [
        migrations.RunPython(grant, ungrant),
    ]
