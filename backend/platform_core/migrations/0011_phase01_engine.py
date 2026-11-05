"""PHASE_01 / 01.3 engine migration (reversible).

1. REV-0109 (P2 of the 01.2 review; employer decision 2026-11-05, DEC-048): person-to-position assignments are
   never back-dated either. Trigger ``trg_position_assignment_a_not_backdated``:
   * INSERT: ``valid_from >= now - 60 s`` (the same TECHNICAL clock tolerance as
     ``platform_effective_from_guard``);
     future starts stay allowed;
   * UPDATE of ``valid_to``: the new end is ``>= now - 60 s`` and an assignment that has already ended (old
     ``valid_to`` in the past) is never changed again (no retroactive end, no retroactive re-opening).
   Rule name ``ck_position_assignment_not_backdated`` (check_violation).
2. Session end reason ``CONCURRENT_LIMIT`` (DEC-051 / Q-0101: the oldest live session is ended automatically).
   Reverse: only possible while no session row uses the new value (the restored CHECK would refuse it).
3. Seed of the housekeeping job types run by the 01.3 engine (``platform_core.jobs.service.HOUSEKEEPING``):
   technical, idempotent batch jobs, not protected and safely cancellable at their checkpoints. Reverse
   deletes
   them only while no run references them (PROTECT FK).
"""

from typing import Any

from django.db import migrations, models

TRIGGER_SQL = r"""
CREATE FUNCTION platform_position_assignment_not_backdated() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;

CREATE TRIGGER trg_position_assignment_a_not_backdated BEFORE INSERT OR UPDATE ON
public.platform_position_assignment
    FOR EACH ROW EXECUTE FUNCTION platform_position_assignment_not_backdated();
"""

TRIGGER_REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS trg_position_assignment_a_not_backdated ON public.platform_position_assignment;
DROP FUNCTION IF EXISTS platform_position_assignment_not_backdated();
"""

END_REASONS = [
    "",
    "IDLE_TIMEOUT",
    "ABSOLUTE_TIMEOUT",
    "MFA_TIMEOUT",
    "LOGOUT",
    "SELF_REVOKE",
    "ADMIN_REVOKE",
    "USER_DISABLED",
    "PASSWORD_CHANGED",
    "MFA_RESET",
    "CONCURRENT_LIMIT",
]

# job_type -> name_fa (frozen data; must equal platform_core.jobs.service.HOUSEKEEPING_TYPES)
HOUSEKEEPING_JOBS = {
    "approval_expiry_sweep": "انقضای درخواست‌های تأیید",
    "role_assignment_expiry_sweep": "انقضای انتساب نقش‌ها",
    "session_expiry_sweep": "پایان جلسه‌های منقضی",
    "document_scan": "بررسی ضدبدافزار فایل‌های قرنطینه",
    "document_rejected_purge": "حذف بایت‌های فایل‌های ردشده پس از قرنطینه",
    "login_event_retention_purge": "حذف رخدادهای ورود پس از دوره نگهداری",
    "audit_integrity_check": "بررسی یکپارچگی زنجیره ممیزی",
}


def seed_jobs(apps: Any, schema_editor: Any) -> None:
    job_definition = apps.get_model("platform_core", "JobDefinition")
    for job_type, name_fa in HOUSEKEEPING_JOBS.items():
        job_definition.objects.using(schema_editor.connection.alias).create(
            job_type=job_type, name_fa=name_fa, cancellable=True, protected=False
        )


def unseed_jobs(apps: Any, schema_editor: Any) -> None:
    apps.get_model("platform_core", "JobDefinition").objects.using(schema_editor.connection.alias).filter(
        job_type__in=list(HOUSEKEEPING_JOBS)
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0010_seed_phase01_catalogue"),
    ]

    operations = [
        migrations.RunSQL(sql=TRIGGER_SQL, reverse_sql=TRIGGER_REVERSE_SQL),
        migrations.RemoveConstraint(model_name="session", name="ck_session_end_reason"),
        migrations.AlterField(
            model_name="session",
            name="end_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("IDLE_TIMEOUT", "Idle timeout"),
                    ("ABSOLUTE_TIMEOUT", "Absolute timeout"),
                    ("MFA_TIMEOUT", "MFA not completed in time"),
                    ("LOGOUT", "Logout"),
                    ("SELF_REVOKE", "Revoked by the user"),
                    ("ADMIN_REVOKE", "Revoked by an administrator"),
                    ("USER_DISABLED", "User disabled"),
                    ("PASSWORD_CHANGED", "Password changed or reset"),
                    ("MFA_RESET", "MFA reset"),
                    ("CONCURRENT_LIMIT", "Ended by the concurrent-session limit (oldest session)"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="session",
            constraint=models.CheckConstraint(
                condition=models.Q(("end_reason__in", END_REASONS)), name="ck_session_end_reason"
            ),
        ),
        migrations.RunPython(seed_jobs, unseed_jobs),
    ]
