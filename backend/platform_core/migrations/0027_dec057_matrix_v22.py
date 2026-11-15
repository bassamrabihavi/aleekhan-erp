"""Permission matrix v2.2 (employer decision of 2026-11-15, DECISION_LOG "DEC-057 amendment (conflict queue
access)"; PHASE_02 / 02.6; reversible, additive seed).

* The three PHASE_00 integration actions enter the permission catalogue (they were checked by the 00.6 views
  but absent from the catalogue, so every caller was denied):
  ``platform.integration.freshness.read``, ``platform.integration.conflict.read``,
  ``platform.integration.conflict.resolve``.
* ``product_data_steward`` and ``owner_admin``: all three (read and resolve the Planning import conflict queue).
* ``management_viewer``: ``freshness.read`` only - data freshness and the per-source open-conflict COUNT of the
  freshness feed (contract 0.8.4-draft); never the conflict items (no ``conflict.read``).
* Flags: no permission is a business approval (resolving records a human decision, it writes no business row,
  integration/conflicts.py); ``conflict.resolve`` carries ``maker_checker`` (SoD, DEC-032 pattern: the resolver
  is never the user who raised the item; engine check in ``resolve_conflict``). No fresh MFA (not one of the
  DEC-057 MFA actions).
* ``product_data_steward``, ``owner_admin`` and ``management_viewer`` carry ``matrix_version = 2.2``; the new
  permissions carry 2.2 / DEC-057.

Same owner-only bypass as 0014/0015/0017/0022/0024 for the ACTIVE roles (grants and ``matrix_version`` are
frozen): the schema owner disables the guard trigger for one statement inside the migration transaction; the
runtime DB role cannot (roles_check.sh).

Reverse: removes the seven grants and the three permissions and puts each role back to its previous version
(exact inverse). Frozen data: this file must not import application code.
"""

from typing import Any

from django.db import migrations

MATRIX_VERSION = "2.2"
DECISION = "DEC-057"
OWNER = "owner_admin"
STEWARD = "product_data_steward"
VIEWER = "management_viewer"
FRESHNESS_READ = "platform.integration.freshness.read"
CONFLICT_READ = "platform.integration.conflict.read"
CONFLICT_RESOLVE = "platform.integration.conflict.resolve"

# action -> (description_fa, mfa_step_up, business_approval, maker_checker)
NEW_PERMISSIONS: dict[str, tuple[str, bool, bool, bool]] = {
    FRESHNESS_READ: ("مشاهده تازگی داده منابع و تعداد تعارض‌های باز", False, False, False),
    CONFLICT_READ: ("مشاهده صف تعارض‌های ورود داده", False, False, False),
    CONFLICT_RESOLVE: ("رسیدگی به تعارض ورود داده (ثبت تصمیم، بدون تغییر داده رسمی)", False, False, True),
}
# action -> role codes (grant mode SCOPE: all sources, GLOBAL assignments)
ADDED_GRANTS: dict[str, tuple[str, ...]] = {
    FRESHNESS_READ: (STEWARD, OWNER, VIEWER),
    CONFLICT_READ: (STEWARD, OWNER),
    CONFLICT_RESOLVE: (STEWARD, OWNER),
}
# role -> matrix version before v2.2 (0022 / 0024)
PREVIOUS_VERSIONS: dict[str, str] = {STEWARD: "2.0", OWNER: "2.1", VIEWER: "2.0"}
CHANGED_ROLES = tuple(PREVIOUS_VERSIONS)


def _seeded(apps: Any, db: str) -> bool:
    role = apps.get_model("platform_core", "Role")
    return bool(role.objects.using(db).filter(code__in=CHANGED_ROLES).count() == len(CHANGED_ROLES))


def forward(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    permission = apps.get_model("platform_core", "Permission")
    role = apps.get_model("platform_core", "Role")
    role_permission = apps.get_model("platform_core", "RolePermission")
    for action, (desc, mfa, ba, sod) in NEW_PERMISSIONS.items():
        permission.objects.using(db).create(
            action=action,
            module=action.split(".")[1],
            description_fa=desc,
            sensitivity="",
            mfa_step_up=mfa,
            business_approval=ba,
            maker_checker=sod,
            matrix_version=MATRIX_VERSION,
            decision_id=DECISION,
        )
    if not _seeded(apps, db):  # catalogue not seeded (keeps the migration total)
        return
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    schema_editor.execute("ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard")
    for action, codes in ADDED_GRANTS.items():
        for code in codes:
            role_permission.objects.using(db).create(
                role=role.objects.using(db).get(code=code),
                permission_id=action,
                grant_mode="SCOPE",
                max_sensitivity="",
            )
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # flush deferred FK checks before ALTER
    schema_editor.execute("ALTER TABLE platform_role_permission ENABLE TRIGGER trg_role_permission_guard")
    schema_editor.execute("ALTER TABLE platform_role DISABLE TRIGGER trg_role_kind_guard")
    role.objects.using(db).filter(code__in=CHANGED_ROLES).update(matrix_version=MATRIX_VERSION)
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    schema_editor.execute("ALTER TABLE platform_role ENABLE TRIGGER trg_role_kind_guard")


def backward(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    role = apps.get_model("platform_core", "Role")
    if _seeded(apps, db):
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        schema_editor.execute(
            "ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard"
        )
        for action, codes in ADDED_GRANTS.items():
            schema_editor.execute(
                "DELETE FROM platform_role_permission WHERE permission_action = %s AND role_id IN "
                "(SELECT id FROM platform_role WHERE code = ANY(%s))",
                [action, list(codes)],
            )
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        schema_editor.execute("ALTER TABLE platform_role_permission ENABLE TRIGGER trg_role_permission_guard")
        schema_editor.execute("ALTER TABLE platform_role DISABLE TRIGGER trg_role_kind_guard")
        for code, version in PREVIOUS_VERSIONS.items():
            role.objects.using(db).filter(code=code).update(matrix_version=version)
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        schema_editor.execute("ALTER TABLE platform_role ENABLE TRIGGER trg_role_kind_guard")
    schema_editor.execute("DELETE FROM platform_permission WHERE action = ANY(%s)", [list(NEW_PERMISSIONS)])


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0026_phase02_planning_catalogue_source"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
