"""PHASE_01 / 01.3 rework round 1 (reversible).

1. REV-0113: a parameter value that was SUPERSEDED before its ``effective_from`` never takes effect. New
   ``platform_param_value_at(key, at)`` selects PUBLISHED values, or SUPERSEDED values whose ``superseded_at`` is
   after their ``effective_from`` (they really were in force for a while); ``platform_param_value(key)`` is
   redefined as ``platform_param_value_at(key, statement_timestamp())`` (same signature, existing grants kept).
   History rows are not rewritten. Reverse restores the 0008 body and drops the new function.
2. REV-0114: login outcome ``MFA_ENROLMENT_REQUIRED`` (refused outside login of a user without MFA factor).
   Reverse: only possible while no login event uses the new value (the restored CHECK would refuse it).
"""

from django.db import migrations, models

FUNCTION_SQL = r"""
CREATE FUNCTION platform_param_value_at(p_key text, p_at timestamptz) RETURNS text
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, pg_temp AS $fn$
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
$fn$;

CREATE OR REPLACE FUNCTION platform_param_value(p_key text) RETURNS text
LANGUAGE sql STABLE SET search_path = pg_catalog, pg_temp AS $fn$
    SELECT public.platform_param_value_at(p_key, statement_timestamp());
$fn$;
"""

# 0008 body (plpgsql) restored on reverse
REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION platform_param_value(p_key text) RETURNS text
LANGUAGE plpgsql STABLE SET search_path = pg_catalog, pg_temp AS $fn$
DECLARE
    v text;
BEGIN
    SELECT pv.value INTO v
      FROM public.platform_parameter_value pv
     WHERE pv.parameter_key = p_key
       AND pv.status IN ('PUBLISHED', 'SUPERSEDED')
       AND pv.effective_from <= statement_timestamp()
     ORDER BY pv.effective_from DESC
     LIMIT 1;
    IF v IS NULL THEN
        RAISE EXCEPTION 'parameter_missing: parameter % has no effective value', p_key
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN v;
END;
$fn$;
DROP FUNCTION IF EXISTS platform_param_value_at(text, timestamptz);
"""

OUTCOMES = [
    "OK",
    "INVALID_CREDENTIALS",
    "LOCKED",
    "DISABLED",
    "ONE_TIME_EXPIRED",
    "NETWORK_POLICY_DENIED",
    "MFA_OK",
    "MFA_FAILED",
    "RECOVERY_CODE_USED",
    "MFA_ENROLMENT_REQUIRED",
]


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0011_phase01_engine"),
    ]

    operations = [
        migrations.RunSQL(sql=FUNCTION_SQL, reverse_sql=REVERSE_SQL),
        migrations.RemoveConstraint(model_name="loginattempt", name="ck_login_attempt_outcome"),
        migrations.AlterField(
            model_name="loginattempt",
            name="outcome",
            field=models.CharField(
                choices=[
                    ("OK", "Password accepted"),
                    ("INVALID_CREDENTIALS", "Wrong username or password"),
                    ("LOCKED", "Account locked"),
                    ("DISABLED", "Account disabled"),
                    ("ONE_TIME_EXPIRED", "Initial one-time password expired (DEC-051)"),
                    ("NETWORK_POLICY_DENIED", "Internal-only account from outside (DEC-042/052)"),
                    ("MFA_OK", "MFA code accepted"),
                    ("MFA_FAILED", "MFA code rejected"),
                    ("RECOVERY_CODE_USED", "Recovery code used (DEC-050)"),
                    ("MFA_ENROLMENT_REQUIRED", "Refused: MFA required but not enrolled"),
                ],
                max_length=24,
            ),
        ),
        migrations.AddConstraint(
            model_name="loginattempt",
            constraint=models.CheckConstraint(
                condition=models.Q(("outcome__in", OUTCOMES)), name="ck_login_attempt_outcome"
            ),
        ),
    ]
