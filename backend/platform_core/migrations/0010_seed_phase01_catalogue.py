"""Non-sensitive PHASE_01 seed (reviewed catalogue only - no users, no org data, no CIDR ranges, no secrets).

* Permission matrix v1.0 (DEC-049 APPROVED 2026-11-04; docs/security/PERMISSION_MATRIX_DRAFT.md, now
  APPROVED v1.0): 43 permissions (= every ``x-aleekhan-permission`` of docs/api/openapi-draft.yaml), 11 roles
  and their grants. Roles are created DRAFT, granted, then set ACTIVE (grants can only change while DRAFT).
  The owner starts with ``owner_admin`` only (DEC-049 item 4) - that assignment is made by the console
  bootstrap command (01.3/01.4), never by a migration.
* Org unit types COMPANY / DEPARTMENT / SECTION / LINE (DEC-048 item 1; the admin may add more).
* Upload allow-list PDF, PNG, JPG, DXF, XLSX (DEC-053). ``jpeg`` is the same JPEG format as ``jpg``.
* Protected job types (migrations, backup, restore): never cancellable (SECURITY_BASELINE 4; full list DEC-024).
* Versioned parameters with decision provenance (DEC-032/048/049/050/051/052/053/054). Values are canonical
  strings; classification OWNER_POLICY. Numbers live here, not in code or trigger SQL.

Reverse: deletes exactly these seed rows (only while no user data references them - PROTECT FKs refuse
otherwise, which is the intended guard: rolling back a used catalogue needs a compensation plan).
Frozen data: this file must not import application code (it describes the reviewed v1.0 state).
"""

from typing import Any

from django.db import migrations
from django.utils import timezone

MATRIX_VERSION = "1.0"
MATRIX_DECISION = "DEC-049"
SEED = "MIGRATION_SEED"

# action -> (description_fa, mfa_step_up, business_approval, maker_checker)
PERMISSIONS: dict[str, tuple[str, bool, bool, bool]] = {
    "platform.identity.user.read": ("مشاهده کاربران و دسترسی‌های مؤثر آن‌ها", False, False, False),
    "platform.identity.user.create": ("ایجاد کاربر (فقط داخل سامانه)", True, False, False),
    "platform.identity.user.update": ("ویرایش مشخصات کاربر", True, False, False),
    "platform.identity.user.disable": ("غیرفعال/فعال کردن کاربر", True, False, False),
    "platform.identity.user.unlock": ("باز کردن قفل کاربر", True, False, False),
    "platform.identity.user.reset_password": ("بازنشانی رمز کاربر", True, False, False),
    "platform.identity.user.reset_mfa": ("بازنشانی ورود دومرحله‌ای کاربر", True, False, False),
    "platform.identity.session.read": ("مشاهده جلسه‌های کاربران", False, False, False),
    "platform.identity.session.revoke": ("ابطال جلسه‌های کاربر", True, False, False),
    "platform.identity.role.read": ("مشاهده نقش‌ها و فهرست مجوزها", False, False, False),
    "platform.identity.role.manage": ("ایجاد، ویرایش، فعال و بازنشسته کردن نقش", True, False, False),
    "platform.identity.assignment.read": ("مشاهده انتساب نقش‌ها", False, False, False),
    "platform.identity.assignment.grant": ("انتساب و لغو نقش", True, False, False),
    "platform.org.read": ("مشاهده درخت سازمانی", False, False, False),
    "platform.org.manage": ("مدیریت واحدها، سمت‌ها و انتساب سمت", True, False, False),
    "platform.workflow.task.read": ("مشاهده کارها", False, False, False),
    "platform.workflow.task.create": ("ایجاد کار", False, False, False),
    "platform.workflow.task.work": ("شروع، انجام، توقف و ادامه کار", False, False, False),
    "platform.workflow.task.assign": ("واگذاری دوباره کار", False, False, False),
    "platform.workflow.task.verify": ("تأیید و بستن کار (غیر از انجام‌دهنده)", False, False, True),
    "platform.workflow.task.cancel": ("لغو کار", False, False, False),
    "platform.workflow.approval.read": ("مشاهده درخواست‌های تأیید و گردش‌ها", False, False, False),
    "platform.workflow.approval.request": ("پس گرفتن درخواست تأیید خود", False, False, False),
    "platform.workflow.approval.decide": ("تصمیم درباره درخواست تأیید", True, True, True),
    "platform.workflow.definition.read": ("مشاهده تعریف گردش‌کار", False, False, False),
    "platform.workflow.instance.cancel": ("لغو نمونه گردش‌کار", True, False, False),
    "platform.audit.read": ("مشاهده رخدادهای ممیزی", True, False, False),
    "platform.audit.integrity.read": ("مشاهده نتیجه بررسی یکپارچگی ممیزی", False, False, False),
    "platform.ops.health.read": ("مشاهده جزئیات سلامت سامانه", False, False, False),
    "platform.ops.job.read": ("مشاهده کارهای پس‌زمینه", False, False, False),
    "platform.ops.job.cancel": ("درخواست لغو امن کار پس‌زمینه", True, False, False),
    "platform.document.read": ("مشاهده اسناد و نسخه‌ها", False, False, False),
    "platform.document.download": ("دانلود نسخه پاک سند", False, False, False),
    "platform.document.create": ("ثبت سند", False, False, False),
    "platform.document.update": ("ویرایش سند و ارسال نسخه برای بازبینی", False, False, False),
    "platform.document.upload": ("بارگذاری نسخه سند (قرنطینه)", False, False, False),
    "platform.document.approve": ("تأیید یا رد نسخه سند", True, True, True),
    "platform.config.parameter.read": ("مشاهده پارامترها", False, False, False),
    "platform.config.parameter.define": ("تعریف پارامتر", True, False, False),
    "platform.config.parameter.propose": ("پیشنهاد مقدار پارامتر", False, False, False),
    "platform.config.parameter.publish": ("انتشار مقدار پارامتر", True, True, True),
    "platform.config.field.read": ("مشاهده تعریف فیلدهای پویا", False, False, False),
    "platform.config.field.define": ("تعریف پیش‌نویس فیلد پویا", False, False, False),
}

# code -> (kind, name_fa)
ROLES: dict[str, tuple[str, str]] = {
    "owner_admin": ("TECHNICAL", "مالک سامانه / مدیر اصلی"),
    "it_ops": ("TECHNICAL", "عملیات فناوری اطلاعات"),
    "security_auditor": ("TECHNICAL", "ممیز امنیت (فقط مشاهده)"),
    "management_viewer": ("BUSINESS", "مدیریت (فقط مشاهده)"),
    "employee": ("BUSINESS", "کارمند"),
    "unit_manager": ("BUSINESS", "مدیر واحد"),
    "document_controller": ("BUSINESS", "مسئول اسناد"),
    "document_approver": ("BUSINESS", "تأییدکننده اسناد"),
    "config_approver": ("BUSINESS", "تأییدکننده پارامترها"),
    "workflow_approver": ("BUSINESS", "تأییدکننده درخواست‌ها"),
    "operator_terminal": ("BUSINESS", "اپراتور خط تولید"),
}

S, OWN, U, OU = "SCOPE", "OWN", "OWN_UNIT", "OWN_AND_OWN_UNIT"
_ADMIN3 = {"owner_admin": S, "it_ops": S, "security_auditor": S}
# action -> {role_code: grant_mode or (grant_mode, max_sensitivity)}  (matrix v1.0 section 3, cell by cell)
GRANTS: dict[str, dict[str, Any]] = {
    "platform.identity.user.read": dict(_ADMIN3),
    "platform.identity.user.create": {"owner_admin": S},
    "platform.identity.user.update": {"owner_admin": S},
    "platform.identity.user.disable": {"owner_admin": S},
    "platform.identity.user.unlock": {"owner_admin": S, "it_ops": S},  # DEC-049 item 2
    "platform.identity.user.reset_password": {"owner_admin": S},
    "platform.identity.user.reset_mfa": {"owner_admin": S},
    "platform.identity.session.read": dict(_ADMIN3),
    "platform.identity.session.revoke": {"owner_admin": S, "it_ops": S},
    "platform.identity.role.read": dict(_ADMIN3),
    "platform.identity.role.manage": {"owner_admin": S},
    "platform.identity.assignment.read": {"owner_admin": S, "security_auditor": S},
    "platform.identity.assignment.grant": {"owner_admin": S},
    "platform.org.read": {
        r: S
        for r in (
            "owner_admin",
            "security_auditor",
            "management_viewer",
            "employee",
            "unit_manager",
            "document_controller",
            "document_approver",
            "config_approver",
            "workflow_approver",
        )
    },
    "platform.org.manage": {"owner_admin": S},
    "platform.workflow.task.read": {
        "employee": OU,
        "unit_manager": S,
        "document_controller": OWN,
        "document_approver": OWN,
        "config_approver": OWN,
        "workflow_approver": OWN,
        "operator_terminal": OWN,
    },
    "platform.workflow.task.create": {"employee": U, "unit_manager": S},
    "platform.workflow.task.work": {
        r: OWN
        for r in (
            "employee",
            "unit_manager",
            "document_controller",
            "document_approver",
            "config_approver",
            "workflow_approver",
            "operator_terminal",
        )
    },
    "platform.workflow.task.assign": {"unit_manager": S},
    "platform.workflow.task.verify": {"unit_manager": S},
    "platform.workflow.task.cancel": {"employee": OWN, "unit_manager": S},
    "platform.workflow.approval.read": {
        "security_auditor": S,
        "management_viewer": S,
        "employee": OWN,
        "unit_manager": S,
        "document_controller": OWN,
        "document_approver": S,
        "config_approver": S,
        "workflow_approver": S,
    },
    "platform.workflow.approval.request": {
        r: OWN
        for r in (
            "employee",
            "unit_manager",
            "document_controller",
            "document_approver",
            "config_approver",
            "workflow_approver",
        )
    },
    "platform.workflow.approval.decide": {"workflow_approver": S},
    "platform.workflow.definition.read": {
        "owner_admin": S,
        "security_auditor": S,
        "unit_manager": S,
        "workflow_approver": S,
    },
    "platform.workflow.instance.cancel": {"unit_manager": S},
    "platform.audit.read": {"owner_admin": S, "security_auditor": S},
    "platform.audit.integrity.read": dict(_ADMIN3),
    "platform.ops.health.read": {"owner_admin": S, "it_ops": S, "management_viewer": S},
    "platform.ops.job.read": {"owner_admin": S, "it_ops": S},
    "platform.ops.job.cancel": {"owner_admin": S, "it_ops": S},
    "platform.document.read": {
        "management_viewer": (S, "S2"),
        "employee": (S, "S1"),
        "unit_manager": (S, "S2"),
        "document_controller": S,
        "document_approver": S,
        "operator_terminal": OWN,
    },
    "platform.document.download": {
        "management_viewer": (S, "S2"),
        "employee": (S, "S1"),
        "unit_manager": (S, "S2"),
        "document_controller": S,
        "document_approver": S,
        "operator_terminal": OWN,
    },
    "platform.document.create": {"document_controller": S},
    "platform.document.update": {"document_controller": S},
    "platform.document.upload": {"document_controller": S},
    "platform.document.approve": {"document_approver": S},
    "platform.config.parameter.read": {
        "owner_admin": S,
        "it_ops": S,
        "security_auditor": S,
        "config_approver": S,
    },
    "platform.config.parameter.define": {"owner_admin": S},
    "platform.config.parameter.propose": {"owner_admin": S, "it_ops": S},
    "platform.config.parameter.publish": {"config_approver": S},
    "platform.config.field.read": {"owner_admin": S, "it_ops": S},
    "platform.config.field.define": {"owner_admin": S},
}

UNIT_TYPES = (
    ("COMPANY", "شرکت", 10),
    ("DEPARTMENT", "معاونت / دپارتمان", 20),
    ("SECTION", "بخش", 30),
    ("LINE", "خط", 40),
)

UPLOAD_TYPES = (
    ("pdf", "application/pdf", "PDF", "PDF"),
    ("png", "image/png", "تصویر PNG", "PNG"),
    ("jpg", "image/jpeg", "تصویر JPG", "JPEG"),
    ("jpeg", "image/jpeg", "تصویر JPG", "JPEG"),
    ("dxf", "image/vnd.dxf", "نقشه DXF", "DXF"),
    (
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "اکسل بدون ماکرو",
        "OOXML_NO_MACRO",
    ),
)

JOB_TYPES = (
    ("db_migrate", "اجرای Migration پایگاه داده"),
    ("db_backup", "پشتیبان‌گیری پایگاه داده"),
    ("db_restore", "بازیابی پایگاه داده"),
)

# key -> (label_fa, datatype, unit, owner_module, decision_id, min, max, allowed_values, value)
PARAMETERS: dict[str, tuple[str, str, str, str, str, int | None, int | None, list[str] | None, str]] = {
    # DEC-051 password, lockout and session policy
    "password_min_length": (
        "حداقل طول رمز",
        "INTEGER",
        "characters",
        "identity",
        "DEC-051",
        8,
        128,
        None,
        "8",
    ),
    "password_require_uppercase": (
        "رمز: حرف بزرگ اجباری",
        "BOOLEAN",
        "",
        "identity",
        "DEC-051",
        None,
        None,
        None,
        "true",
    ),
    "password_require_digit": (
        "رمز: عدد اجباری",
        "BOOLEAN",
        "",
        "identity",
        "DEC-051",
        None,
        None,
        None,
        "true",
    ),
    "password_require_symbol": (
        "رمز: نماد اجباری",
        "BOOLEAN",
        "",
        "identity",
        "DEC-051",
        None,
        None,
        None,
        "true",
    ),
    "password_max_age_days": (
        "دوره تعویض رمز",
        "INTEGER",
        "days",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "90",
    ),
    "password_initial_validity_hours": (
        "اعتبار رمز یک‌بارمصرف اولیه",
        "INTEGER",
        "hours",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "72",
    ),
    "password_change_at_first_login": (
        "تعویض اجباری رمز در اولین ورود",
        "BOOLEAN",
        "",
        "identity",
        "DEC-051",
        None,
        None,
        None,
        "true",
    ),
    "lockout_max_failures": (
        "تعداد ورود ناموفق تا قفل",
        "INTEGER",
        "count",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "5",
    ),
    "lockout_window_minutes": (
        "پنجره شمارش ورود ناموفق",
        "INTEGER",
        "minutes",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "15",
    ),
    "lockout_duration_minutes": (
        "مدت قفل خودکار",
        "INTEGER",
        "minutes",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "15",
    ),
    "session_user_idle_minutes": (
        "جلسه کاربر عادی: بی‌کاری",
        "INTEGER",
        "minutes",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "120",
    ),
    "session_user_absolute_hours": (
        "جلسه کاربر عادی: حداکثر",
        "INTEGER",
        "hours",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "12",
    ),
    "session_operator_idle_minutes": (
        "جلسه اپراتور: بی‌کاری",
        "INTEGER",
        "minutes",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "480",
    ),
    "session_operator_absolute_hours": (
        "جلسه اپراتور: حداکثر",
        "INTEGER",
        "hours",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "12",
    ),
    "session_operator_internal_only": (
        "جلسه اپراتور فقط از شبکه داخلی",
        "BOOLEAN",
        "",
        "identity",
        "DEC-051",
        None,
        None,
        None,
        "true",
    ),
    "session_limit_exceeded_action": (
        "رفتار در ورود چهارم: پایان قدیمی‌ترین جلسه",
        "ENUM",
        "",
        "identity",
        "DEC-051",
        None,
        None,
        ["END_OLDEST_SESSION"],
        "END_OLDEST_SESSION",
    ),
    "password_history_reuse_depth": (
        "تعداد رمزهای قبلی غیرقابل تکرار",
        "INTEGER",
        "count",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "5",
    ),
    "session_max_concurrent": (
        "حداکثر جلسه همزمان",
        "INTEGER",
        "count",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "3",
    ),
    "mfa_step_up_window_minutes": (
        "پنجره تأیید دومرحله‌ای تازه",
        "INTEGER",
        "minutes",
        "identity",
        "DEC-051",
        1,
        None,
        None,
        "15",
    ),
    # DEC-049 item 5, DEC-050
    "mfa_step_up_inside_network": (
        "تأیید دومرحله‌ای تازه حتی داخل شبکه کارخانه",
        "BOOLEAN",
        "",
        "identity",
        "DEC-049",
        None,
        None,
        None,
        "true",
    ),
    "mfa_method": ("روش ورود دومرحله‌ای", "ENUM", "", "identity", "DEC-050", None, None, ["TOTP"], "TOTP"),
    "mfa_recovery_code_count": (
        "تعداد کد بازیابی یک‌بارمصرف",
        "INTEGER",
        "count",
        "identity",
        "DEC-050",
        1,
        None,
        None,
        "10",
    ),
    # DEC-052 network zones (the CIDR list itself lives only in server config, never in the DB or Git)
    "network_unknown_is_external": (
        "شبکه نامعلوم = بیرون",
        "BOOLEAN",
        "",
        "identity",
        "DEC-052",
        None,
        None,
        None,
        "true",
    ),
    "network_vpn_is_external": (
        "VPN = بیرون",
        "BOOLEAN",
        "",
        "identity",
        "DEC-052",
        None,
        None,
        None,
        "true",
    ),
    # DEC-054 (A, before production): sealed emergency account session
    "break_glass_session_hours": (
        "جلسه حساب اضطراری",
        "INTEGER",
        "hours",
        "identity",
        "DEC-054",
        1,
        None,
        None,
        "2",
    ),
    # DEC-053 uploads; 25 MB = 26 214 400 bytes (binary, as Windows shows it - employer answer Q-0104, 2026-11-05)
    "document_upload_max_bytes": (
        "حداکثر حجم فایل بارگذاری",
        "INTEGER",
        "bytes",
        "document",
        "DEC-053",
        1,
        None,
        None,
        "26214400",
    ),
    "document_rejected_quarantine_days": (
        "نگهداری فایل ردشده در قرنطینه",
        "INTEGER",
        "days",
        "document",
        "DEC-053",
        1,
        None,
        None,
        "30",
    ),
    "document_scanner": ("ضدبدافزار", "ENUM", "", "document", "DEC-053", None, None, ["CLAMAV"], "CLAMAV"),
    # DEC-032 approvals and retention
    "approval_request_expiry_days": (
        "انقضای درخواست تأیید",
        "INTEGER",
        "days",
        "workflow",
        "DEC-032",
        1,
        None,
        None,
        "30",
    ),
    "retention_login_events_months": (
        "نگهداری رخدادهای ورود",
        "INTEGER",
        "months",
        "audit",
        "DEC-032",
        1,
        None,
        None,
        "24",
    ),
    "retention_business_audit": (
        "نگهداری ممیزی کسب‌وکار و دسترسی",
        "ENUM",
        "",
        "audit",
        "DEC-032",
        None,
        None,
        ["KEEP_FOREVER_YEARLY_ARCHIVE"],
        "KEEP_FOREVER_YEARLY_ARCHIVE",
    ),
    # DEC-048 org tree
    "org_tree_max_depth": (
        "حداکثر عمق درخت سازمانی",
        "INTEGER",
        "levels",
        "org",
        "DEC-048",
        1,
        None,
        None,
        "6",
    ),
}

# Employer answers to the 01.2 open questions (STATE_TRANSITIONS 4.12), same decision DEC-051.
_ANS = "DEC-051 (employer answer Q-0101/Q-0102/Q-0105, 2026-11-05)"
EMPLOYER_ANSWERS = {
    "session_limit_exceeded_action": _ANS,  # Q-0101
    "session_operator_absolute_hours": _ANS,  # Q-0102
    "password_history_reuse_depth": _ANS,  # Q-0105
    "document_upload_max_bytes": "DEC-053 (employer answer Q-0104, 2026-11-05)",
}

SCHEMA_CONTRACT = "PHASE_01.2"
SEEDED_BY = "platform_core.0010_seed_phase01_catalogue"
PREVIOUS_META = ("PHASE_00.2", "platform_core.0003_seed_schema_meta")


def seed(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    permission = apps.get_model("platform_core", "Permission")
    role = apps.get_model("platform_core", "Role")
    role_permission = apps.get_model("platform_core", "RolePermission")
    unit_type = apps.get_model("platform_core", "OrgUnitType")
    upload_type = apps.get_model("platform_core", "UploadType")
    job_definition = apps.get_model("platform_core", "JobDefinition")
    definition = apps.get_model("platform_core", "ParameterDefinition")
    value = apps.get_model("platform_core", "ParameterValue")
    schema_meta = apps.get_model("platform_core", "SchemaMeta")
    now = timezone.now()

    for action, (desc, mfa, ba, sod) in PERMISSIONS.items():
        permission.objects.using(db).create(
            action=action,
            module=action.split(".")[1],
            description_fa=desc,
            sensitivity="",
            mfa_step_up=mfa,
            business_approval=ba,
            maker_checker=sod,
            matrix_version=MATRIX_VERSION,
            decision_id=MATRIX_DECISION,
        )
    roles = {}
    for code, (kind, name_fa) in ROLES.items():
        roles[code] = role.objects.using(db).create(
            code=code,
            name_fa=name_fa,
            kind=kind,
            status="DRAFT",
            decision_id=MATRIX_DECISION,
            provenance=SEED,
        )
    for action, cells in GRANTS.items():
        for code, cell in cells.items():
            mode, max_sens = cell if isinstance(cell, tuple) else (cell, "")
            role_permission.objects.using(db).create(
                role=roles[code], permission_id=action, grant_mode=mode, max_sensitivity=max_sens
            )
    role.objects.using(db).filter(code__in=list(ROLES)).update(status="ACTIVE", matrix_version=MATRIX_VERSION)

    for code, name_fa, order in UNIT_TYPES:
        unit_type.objects.using(db).create(
            code=code, name_fa=name_fa, sort_order=order, decision_id="DEC-048", provenance=SEED
        )
    for ext, media, label, check in UPLOAD_TYPES:
        upload_type.objects.using(db).create(
            extension=ext, media_type=media, label_fa=label, content_check=check, decision_id="DEC-053"
        )
    for job_type, name_fa in JOB_TYPES:
        job_definition.objects.using(db).create(
            job_type=job_type, name_fa=name_fa, cancellable=False, protected=True
        )

    for key, (label, dtype, unit, module, dec, lo, hi, allowed, val) in PARAMETERS.items():
        d = definition.objects.using(db).create(
            key=key,
            label_fa=label,
            datatype=dtype,
            unit=unit,
            owner_module=module,
            classification="OWNER_POLICY",
            decision_id=dec,
            min_value=lo,
            max_value=hi,
            allowed_values=allowed,
            provenance=SEED,
        )
        value.objects.using(db).create(
            definition=d,
            value=val,
            status="PUBLISHED",
            effective_from=now,
            decision_id=dec,
            reason=EMPLOYER_ANSWERS.get(key, f"{dec} APPROVED 2026-11-04") + " (seeded by migration 0010)",
            provenance=SEED,
            published_at=now,
        )
    schema_meta.objects.using(db).filter(id=1).update(
        schema_contract=SCHEMA_CONTRACT, seeded_by_migration=SEEDED_BY
    )


def unseed(apps: Any, schema_editor: Any) -> None:
    db = schema_editor.connection.alias
    get = apps.get_model
    get("platform_core", "SchemaMeta").objects.using(db).filter(id=1, seeded_by_migration=SEEDED_BY).update(
        schema_contract=PREVIOUS_META[0], seeded_by_migration=PREVIOUS_META[1]
    )
    # parameter values: SUPERSEDED/REJECTED rows are immutable (trigger); seed rows are PUBLISHED, delete them
    get("platform_core", "ParameterValue").objects.using(db).filter(
        provenance=SEED, definition_id__in=list(PARAMETERS)
    ).delete()
    get("platform_core", "ParameterDefinition").objects.using(db).filter(
        provenance=SEED, key__in=list(PARAMETERS)
    ).delete()
    get("platform_core", "JobDefinition").objects.using(db).filter(
        job_type__in=[j for j, _ in JOB_TYPES]
    ).delete()
    get("platform_core", "UploadType").objects.using(db).filter(
        extension__in=[u[0] for u in UPLOAD_TYPES]
    ).delete()
    get("platform_core", "OrgUnitType").objects.using(db).filter(
        provenance=SEED, code__in=[u[0] for u in UNIT_TYPES]
    ).delete()
    role = get("platform_core", "Role")
    seeded = role.objects.using(db).filter(provenance=SEED, code__in=list(ROLES))
    # Owner-only bypass (REV-0105): grants of ACTIVE roles are frozen and a role can never go back to DRAFT.
    # The reverse migration runs as the schema owner, so it may disable the guard for this one statement inside
    # the migration transaction; the runtime role cannot (not owner, roles_check.sh).
    schema_editor.execute("ALTER TABLE platform_role_permission DISABLE TRIGGER trg_role_permission_guard")
    get("platform_core", "RolePermission").objects.using(db).filter(role__in=seeded).delete()
    schema_editor.execute("ALTER TABLE platform_role_permission ENABLE TRIGGER trg_role_permission_guard")
    seeded.delete()
    get("platform_core", "Permission").objects.using(db).filter(action__in=list(PERMISSIONS)).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0009_phase01_constraint_names"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
