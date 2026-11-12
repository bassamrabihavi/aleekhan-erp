"""DEC-057 (APPROVED 2026-11-12, option M-A): permission matrix v2.0 - the PHASE_02 permissions and roles
(reversible, additive seed). Source: control/decisions/DEC-057_PACKET.md table "as written"; the permission ids are
the ``x-aleekhan-permission`` values of the planned PHASE_02 operations (docs/api/openapi-draft.yaml 0.7.0-draft);
human-readable copy: docs/security/PERMISSION_MATRIX_DRAFT.md section 7.

* 22 permissions ``identity.*`` / ``commercial.*``. Fresh MFA exactly for ``identity.product_code.issue``,
  ``identity.code_rule.approve``, ``commercial.order.confirm`` and ``commercial.change.decide`` (DEC-057).
  Business approval (BA, implies maker-checker + MFA, ``ck_permission_ba_is_sod_and_mfa``): the three decisions
  ``identity.code_rule.approve``, ``commercial.order.confirm`` (planning confirms, serials in the same
  transaction, DEC-006 L-A) and ``commercial.change.decide``.
* Five new BUSINESS roles: ``commercial_officer``, ``commercial_manager``, ``planning_officer``,
  ``product_data_steward``, ``code_rule_approver`` (DRAFT -> grants -> ACTIVE, ``matrix_version`` 2.0). Customer
  scope = all customers (grant mode SCOPE; no per-officer customer assignment).
* ``management_viewer`` gets the read-only rows the packet lists (customer, product, serial, order, change);
  ``employee`` gets nothing; ``it_ops`` / ``security_auditor`` get nothing (DEC-003).
* ``owner_admin`` (TECHNICAL) decides directly on code-rule approval, order confirm and change-request decisions
  (extension of DEC-056). The explicit exception of ``ck_role_technical_no_business_approval`` grows from the three
  pairs of 0015 to exactly six pairs; maker != checker stays (never his own request: DB CHECKs on the PHASE_02
  tables + engine). ``owner_admin`` and ``management_viewer`` carry ``matrix_version = 2.0``.

Same owner-only bypass as 0014/0015/0017 for the ACTIVE roles (grants and ``matrix_version`` are frozen): the
schema owner disables the guard trigger for one statement inside the migration transaction; the runtime DB role
cannot (roles_check.sh).

Reverse: removes the grants, the five roles and the 22 permissions, puts ``owner_admin`` back to 1.3 and
``management_viewer`` back to 1.0, and restores the 0015 guard bodies byte-identically (empty schema diff after a
round trip). Refused by PROTECT FKs once a new role is assigned (the intended guard: rolling back a used matrix
needs a compensation plan).
Frozen data: no application code is imported (only the frozen SQL text of migration 0015).
"""

from importlib import import_module
from typing import Any

from django.db import migrations

MATRIX_VERSION = "2.0"
DECISION = "DEC-057"
SEED = "MIGRATION_SEED"
OWNER = "owner_admin"
VIEWER = "management_viewer"
PREVIOUS_VERSIONS = {OWNER: "1.3", VIEWER: "1.0"}

# action -> (description_fa, mfa_step_up, business_approval, maker_checker)
PERMISSIONS: dict[str, tuple[str, bool, bool, bool]] = {
    "identity.customer.read": ("مشاهده مشتری‌ها و برندها", False, False, False),
    "identity.customer.manage": ("ثبت و ویرایش مشتری و برند", False, False, False),
    "identity.product.read": ("مشاهده محصول، استایل و نسخه استایل", False, False, False),
    "identity.product.manage": ("ثبت و ویرایش محصول، استایل و نسخه استایل", False, False, False),
    "identity.product_code.read": ("مشاهده کدهای ۱۴ رقمی", False, False, False),
    "identity.product_code.issue": ("صدور و رزرو کد ۱۴ رقمی", True, False, False),
    "identity.code_rule.read": ("مشاهده نسخه‌های قاعده کد", False, False, False),
    "identity.code_rule.manage": ("پیش‌نویس و ارسال نسخه قاعده کد", False, False, False),
    "identity.code_rule.approve": ("تأیید، رد و فعال‌سازی نسخه قاعده کد", True, True, True),
    "identity.serial.read": ("مشاهده سریال‌ها و نسخه‌های آن", False, False, False),
    "identity.serial.allocate": ("ساخت سریال", False, False, False),
    "identity.external_ref.read": ("مشاهده مرجع‌های خارجی", False, False, False),
    "identity.external_ref.manage": ("ثبت مرجع خارجی و نوع مرجع", False, False, False),
    "identity.historical.read": ("مشاهده سوابق قدیمی سفارش", False, False, False),
    "commercial.order.read": ("مشاهده سفارش‌ها", False, False, False),
    "commercial.order.manage": ("ثبت و ویرایش پیش‌نویس سفارش", False, False, False),
    "commercial.order.confirm": ("تأیید سفارش همراه با ساخت سریال", True, True, True),
    "commercial.order.release": ("ارسال سفارش به برنامه‌ریزی", False, False, False),
    "commercial.change.read": ("مشاهده درخواست‌های تغییر", False, False, False),
    "commercial.change.request": ("ثبت درخواست تغییر", False, False, False),
    "commercial.change.decide": ("تصمیم درباره درخواست تغییر", True, True, True),
    "commercial.change.apply": ("اعمال درخواست تغییر تأییدشده", False, False, False),
}

# code -> name_fa (all BUSINESS)
ROLES: dict[str, str] = {
    "commercial_officer": "کارشناس بازرگانی",
    "commercial_manager": "مدیر بازرگانی",
    "planning_officer": "کارشناس برنامه‌ریزی",
    "product_data_steward": "مسئول داده محصول",
    "code_rule_approver": "تأییدکننده قاعده کد",
}

CO, CM, PO, PDS, CRA = ROLES
ALL5 = (CO, CM, PO, PDS, CRA)

# action -> role codes (grant mode SCOPE: all customers, DEC-057 answer 3). DEC-057_PACKET.md table cell by cell.
GRANTS: dict[str, tuple[str, ...]] = {
    "identity.customer.read": (*ALL5, VIEWER),
    "identity.customer.manage": (CO,),
    "identity.product.read": (*ALL5, VIEWER),
    "identity.product.manage": (PDS,),
    "identity.product_code.read": ALL5,
    "identity.product_code.issue": (PDS,),
    "identity.code_rule.read": (PDS, CRA, PO),
    "identity.code_rule.manage": (PDS,),
    "identity.code_rule.approve": (CRA, OWNER),
    "identity.serial.read": (*ALL5, VIEWER),
    "identity.serial.allocate": (PO,),
    "identity.external_ref.read": ALL5,
    "identity.external_ref.manage": (CO, PDS),
    "identity.historical.read": (PO, PDS),
    "commercial.order.read": (*ALL5, VIEWER),
    "commercial.order.manage": (CO,),
    "commercial.order.confirm": (PO, OWNER),
    "commercial.order.release": (PO,),
    "commercial.change.read": (*ALL5, VIEWER),
    "commercial.change.request": (CO, PO),
    "commercial.change.decide": (CM, OWNER),
    "commercial.change.apply": (PO,),
}

V12_OWNER_BA = (
    "'platform.workflow.approval.decide', 'platform.document.approve', 'platform.config.parameter.publish'"
)
V20_OWNER_BA = (
    "'platform.workflow.approval.decide', 'platform.document.approve', 'platform.config.parameter.publish',\n"
    "           'identity.code_rule.approve', 'commercial.order.confirm', 'commercial.change.decide'"
)

_v12 = import_module("platform_core.migrations.0015_dec056_matrix_v12")
REVERSE_SQL: str = _v12.FORWARD_SQL  # the guard bodies as 0015 left them (byte-identical)
assert REVERSE_SQL.count(V12_OWNER_BA) == 3
FORWARD_SQL = (
    REVERSE_SQL.replace(V12_OWNER_BA, V20_OWNER_BA)
    .replace(
        "-- DEC-003; explicit exception DEC-056 (matrix v1.2): owner_admin holds exactly these three permissions",
        "-- DEC-003; explicit exception DEC-056 + DEC-057 (matrix v2.0): owner_admin holds exactly these six",
    )
    .replace(
        "(DEC-056 v1.2: owner decide, document approve, parameter publish only).",
        "(DEC-056/DEC-057 v2.0: owner decide, document approve, parameter publish, code-rule approve, "
        "order confirm, change decide only).",
    )
)


def _owner_like(apps: Any, db: str) -> bool:
    return bool(apps.get_model("platform_core", "Role").objects.using(db).filter(code=OWNER).exists())


def seed(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    permission = apps.get_model("platform_core", "Permission")
    role = apps.get_model("platform_core", "Role")
    role_permission = apps.get_model("platform_core", "RolePermission")
    for action, (desc, mfa, ba, sod) in PERMISSIONS.items():
        permission.objects.using(db).create(
            action=action,
            module=action.split(".")[0],
            description_fa=desc,
            sensitivity="",
            mfa_step_up=mfa,
            business_approval=ba,
            maker_checker=sod,
            matrix_version=MATRIX_VERSION,
            decision_id=DECISION,
        )
    new_roles = {
        code: role.objects.using(db).create(
            code=code, name_fa=name, kind="BUSINESS", status="DRAFT", decision_id=DECISION, provenance=SEED
        )
        for code, name in ROLES.items()
    }
    for action, codes in GRANTS.items():
        for code in codes:
            if code in new_roles:
                role_permission.objects.using(db).create(
                    role=new_roles[code], permission_id=action, grant_mode="SCOPE", max_sensitivity=""
                )
    role.objects.using(db).filter(code__in=list(ROLES)).update(status="ACTIVE", matrix_version=MATRIX_VERSION)
    if not _owner_like(apps, db):  # PHASE_01 catalogue not seeded (keeps the migration total)
        return
    # existing ACTIVE roles: owner-only bypass of the frozen-grant guard (one statement, this transaction)
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # no pending FK events before ALTER
    schema_editor.execute("ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard")
    for action, codes in GRANTS.items():
        for code in codes:
            if code in PREVIOUS_VERSIONS:
                role_permission.objects.using(db).create(
                    role=role.objects.using(db).get(code=code),
                    permission_id=action,
                    grant_mode="SCOPE",
                    max_sensitivity="",
                )
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")  # flush deferred FK checks before ALTER
    schema_editor.execute("ALTER TABLE platform_role_permission ENABLE TRIGGER trg_role_permission_guard")
    schema_editor.execute("ALTER TABLE platform_role DISABLE TRIGGER trg_role_kind_guard")
    role.objects.using(db).filter(code__in=list(PREVIOUS_VERSIONS)).update(matrix_version=MATRIX_VERSION)
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    schema_editor.execute("ALTER TABLE platform_role ENABLE TRIGGER trg_role_kind_guard")


def unseed(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    role = apps.get_model("platform_core", "Role")
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    schema_editor.execute("ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard")
    schema_editor.execute(
        "DELETE FROM platform_role_permission WHERE permission_action = ANY(%s)", [list(PERMISSIONS)]
    )
    schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    schema_editor.execute("ALTER TABLE platform_role_permission ENABLE TRIGGER trg_role_permission_guard")
    # raw DELETE: the ORM collector of the historical models cannot follow the reverse relations here
    schema_editor.execute(
        "DELETE FROM platform_role WHERE code = ANY(%s) AND provenance = %s", [list(ROLES), SEED]
    )
    if _owner_like(apps, db):
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        schema_editor.execute("ALTER TABLE platform_role DISABLE TRIGGER trg_role_kind_guard")
        for code, version in PREVIOUS_VERSIONS.items():
            role.objects.using(db).filter(code=code).update(matrix_version=version)
        schema_editor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        schema_editor.execute("ALTER TABLE platform_role ENABLE TRIGGER trg_role_kind_guard")
    schema_editor.execute("DELETE FROM platform_permission WHERE action = ANY(%s)", [list(PERMISSIONS)])


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0021_phase02_seed_catalogue"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
        migrations.RunPython(seed, unseed),
    ]
