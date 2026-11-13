"""Permission matrix v2.1 (employer amendments of 2026-11-12, DECISION_LOG "DEC-057 amendment (owner read) and
DEC-059 amendment (due-date approver, cancel from hold)"; reversible, additive seed).

* DEC-057 amendment: ``owner_admin`` gets every PHASE_02 ``identity.*`` / ``commercial.*`` **read** permission
  (the same fix v1.3 made for documents), so he can open what he decides. None of them is a business-approval
  permission: the explicit owner exception of ``ck_role_technical_no_business_approval`` stays the six pairs
  of 0022 (no guard function is replaced). Self-approval stays forbidden (engine + DB CHECKs).
* DEC-059 amendment: the planning approval of a due-date change gets its own permission
  ``commercial.change.planning_approve`` (final name set in 02.3, family ``commercial.change.*`` of the
  OpenAPI draft), granted to ``planning_officer`` only. Flags PROPOSED in 02.3 for the employer's confirmation:
  fresh MFA + business approval + maker-checker, like ``commercial.change.decide`` (a second approval of the
  same request). The approver is neither the requester nor the deciding manager (engine + CHECKs 0019/0023).
* ``owner_admin`` and ``planning_officer`` carry ``matrix_version = 2.1``; the new permission carries 2.1 /
  DEC-059. Every other role keeps its version.

Same owner-only bypass as 0014/0015/0017/0022 for the ACTIVE roles (grants and ``matrix_version`` are frozen):
the schema owner disables the guard trigger for one statement inside the migration transaction; the runtime DB
role cannot (roles_check.sh).

Reverse: removes the ten grants and the permission, and puts both roles back to 2.0 (exact inverse).
Frozen data: this file must not import application code.
"""

from typing import Any

from django.db import migrations

MATRIX_VERSION = "2.1"
PREVIOUS_MATRIX_VERSION = "2.0"
OWNER = "owner_admin"
PLANNER = "planning_officer"
PLANNING_APPROVE = "commercial.change.planning_approve"

# action -> (description_fa, mfa_step_up, business_approval, maker_checker, decision)
NEW_PERMISSIONS: dict[str, tuple[str, bool, bool, bool, str]] = {
    PLANNING_APPROVE: ("تأیید برنامه‌ریزی برای تغییر تاریخ تحویل", True, True, True, "DEC-059"),
}
OWNER_READS: tuple[str, ...] = (
    "identity.customer.read",
    "identity.product.read",
    "identity.product_code.read",
    "identity.code_rule.read",
    "identity.serial.read",
    "identity.external_ref.read",
    "identity.historical.read",
    "commercial.order.read",
    "commercial.change.read",
)
# action -> role codes (grant mode SCOPE: all customers, DEC-057 answer 3)
ADDED_GRANTS: dict[str, tuple[str, ...]] = {
    **{action: (OWNER,) for action in OWNER_READS},
    PLANNING_APPROVE: (PLANNER,),
}
CHANGED_ROLES = (OWNER, PLANNER)


def _seeded(apps: Any, db: str) -> bool:
    role = apps.get_model("platform_core", "Role")
    return bool(role.objects.using(db).filter(code__in=CHANGED_ROLES).count() == len(CHANGED_ROLES))


def forward(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    permission = apps.get_model("platform_core", "Permission")
    role = apps.get_model("platform_core", "Role")
    role_permission = apps.get_model("platform_core", "RolePermission")
    for action, (desc, mfa, ba, sod, decision) in NEW_PERMISSIONS.items():
        permission.objects.using(db).create(
            action=action,
            module=action.split(".")[0],
            description_fa=desc,
            sensitivity="",
            mfa_step_up=mfa,
            business_approval=ba,
            maker_checker=sod,
            matrix_version=MATRIX_VERSION,
            decision_id=decision,
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
        role.objects.using(db).filter(code__in=CHANGED_ROLES).update(matrix_version=PREVIOUS_MATRIX_VERSION)
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        schema_editor.execute("ALTER TABLE platform_role ENABLE TRIGGER trg_role_kind_guard")
    schema_editor.execute("DELETE FROM platform_permission WHERE action = ANY(%s)", [list(NEW_PERMISSIONS)])


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0023_phase02_engine"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
