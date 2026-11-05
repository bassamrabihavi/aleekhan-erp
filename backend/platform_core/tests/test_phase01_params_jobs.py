"""PHASE_01 / 01.2: typed parameters (DEC provenance), jobs (safe cancel), integrity runs, field drafts."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.db.models.functions import Now
from django.utils import timezone

from platform_core.jobs.models import AuditIntegrityRun, JobDefinition, JobRun
from platform_core.params.models import DynamicFieldDefinition, ParameterDefinition, ParameterValue

from .phase01_factories import db_refuses, user

pytestmark = pytest.mark.django_db


def _definition(
    key: str, datatype: str = "INTEGER", classification: str = "TECHNICAL", **over: object
) -> ParameterDefinition:
    data: dict[str, object] = {
        "key": key,
        "label_fa": "پارامتر ساختگی",
        "datatype": datatype,
        "owner_module": "platform",
        "classification": classification,
    }
    data.update(over)
    return ParameterDefinition.objects.create(**data)


def _value(d: ParameterDefinition, value: str, **over: object) -> ParameterValue:
    data: dict[str, object] = {
        "definition": d,
        "value": value,
        "effective_from": timezone.now(),
        "proposed_by": user(),
    }
    data.update(over)
    return ParameterValue.objects.create(**data)


def test_policy_and_business_definitions_need_a_decision() -> None:
    with db_refuses("ck_parameter_definition_decision_required"):
        _definition("syn_policy", classification="OWNER_POLICY")
    with db_refuses("ck_parameter_definition_decision_required"):
        _definition("syn_rule", classification="BUSINESS_RULE")
    with db_refuses("ck_parameter_definition_key_fmt"):
        _definition("Syn.Key")


@pytest.mark.parametrize(
    ("datatype", "bad", "good"),
    [
        ("INTEGER", "1.5", "15"),
        ("DECIMAL", "1e3", "12.5000"),
        ("BOOLEAN", "yes", "false"),
        ("DATE", "2026-02-30", "2026-11-04"),
    ],
)
def test_values_are_typed_canonical_strings(datatype: str, bad: str, good: str) -> None:
    d = _definition(f"syn_{datatype.lower()}", datatype=datatype)
    with db_refuses("ck_parameter_value_type"):
        _value(d, bad)
    _value(d, good)


def test_bounds_and_enum_values() -> None:
    d = _definition("syn_bounded", min_value=1, max_value=10)
    with db_refuses("ck_parameter_value_bounds"):
        _value(d, "11")
    e = _definition("syn_enum", datatype="ENUM", allowed_values=["A", "B"])
    with db_refuses("ck_parameter_value_type"):
        _value(e, "C")
    with db_refuses("ck_parameter_definition_enum_values"):
        _definition("syn_enum2", datatype="ENUM")


def test_published_values_are_immutable_and_only_superseded() -> None:
    d = _definition("syn_pub")
    v = _value(d, "5")
    ParameterValue.objects.filter(pk=v.pk).update(status="PENDING_APPROVAL")
    with db_refuses("immutable_column"):
        ParameterValue.objects.filter(pk=v.pk).update(value="6")
    ParameterValue.objects.filter(pk=v.pk).update(status="PUBLISHED", published_by=user(), published_at=Now())
    with db_refuses("immutable_column"):
        ParameterValue.objects.filter(pk=v.pk).update(status="DRAFT")
    ParameterValue.objects.filter(pk=v.pk).update(status="SUPERSEDED", superseded_at=Now())
    with db_refuses("terminal_immutable"):
        ParameterValue.objects.filter(pk=v.pk).update(status="PUBLISHED")


def test_business_rule_publish_is_maker_checker() -> None:
    """DEC-032: a BUSINESS_RULE value is never published by the person who proposed it."""
    d = _definition("syn_br", classification="BUSINESS_RULE", decision_id="DEC-016")
    maker = user()
    v = _value(d, "3", proposed_by=maker, decision_id="DEC-016", status="PENDING_APPROVAL")
    with db_refuses("ck_parameter_value_maker_checker"):
        ParameterValue.objects.filter(pk=v.pk).update(
            status="PUBLISHED", published_by=maker, published_at=Now()
        )
    ParameterValue.objects.filter(pk=v.pk).update(status="PUBLISHED", published_by=user(), published_at=Now())


def test_effective_value_function_follows_effective_from() -> None:
    d = _definition("syn_eff")
    past = timezone.now() - timedelta(days=2)
    _value(d, "1", status="PUBLISHED", published_by=user(), published_at=past, effective_from=past)
    _value(
        d,
        "2",
        status="PUBLISHED",
        published_by=user(),
        published_at=past,
        effective_from=past + timedelta(days=1),
    )
    _value(
        d,
        "3",
        status="PUBLISHED",
        published_by=user(),
        published_at=past,
        effective_from=timezone.now() + timedelta(days=1),
    )
    with connection.cursor() as cur:
        cur.execute("SELECT platform_param_int('syn_eff')")
        assert cur.fetchone()[0] == 2
    with db_refuses("uq_parameter_value_effective"):
        _value(d, "4", status="PUBLISHED", published_by=user(), published_at=past, effective_from=past)
    with db_refuses("parameter_missing"), connection.cursor() as cur:
        cur.execute("SELECT platform_param_int('syn_unknown_key')")


def test_definition_type_and_classification_immutable() -> None:
    d = _definition("syn_imm")
    ParameterDefinition.objects.filter(pk=d.pk).update(label_fa="برچسب تازه")
    with db_refuses("immutable_column"):
        ParameterDefinition.objects.filter(pk=d.pk).update(datatype="STRING")
    with db_refuses("immutable_column"):
        ParameterDefinition.objects.filter(key="session_max_concurrent").update(classification="TECHNICAL")


def test_dynamic_fields_are_drafts_with_immutable_key() -> None:
    f = DynamicFieldDefinition.objects.create(
        field_key="syn_field",
        entity_scope="synthetic",
        label_fa="فیلد ساختگی",
        datatype="STRING",
        security_class="S1",
    )
    with db_refuses("ck_dynamic_field_draft_only"):
        DynamicFieldDefinition.objects.filter(pk=f.pk).update(status="ACTIVE")
    with db_refuses("immutable_column"):
        DynamicFieldDefinition.objects.filter(pk=f.pk).update(field_key="syn_other")
    DynamicFieldDefinition.objects.filter(pk=f.pk).update(label_fa="برچسب تازه")


# ---------------------------------------------------------------------------------------------- jobs
def _run(job_type: str, **over: object) -> JobRun:
    data: dict[str, object] = {"job_type_id": job_type, "task_key": f"syn-{uuid.uuid4()}"}
    data.update(over)
    return JobRun.objects.create(**data)


def test_protected_job_types_are_seeded_and_never_cancellable() -> None:
    """Gate-1 'Job kill under permission and reason': protected types (migrate/backup/restore) refuse it."""
    assert set(JobDefinition.objects.filter(protected=True).values_list("job_type", flat=True)) == {
        "db_migrate",
        "db_backup",
        "db_restore",
    }
    with db_refuses("ck_job_definition_protected_not_cancellable"):
        JobDefinition.objects.create(job_type="syn_bad", name_fa="x", cancellable=True, protected=True)
    run = _run("db_backup", state="RUNNING", started_at=Now())
    with db_refuses("ck_job_run_not_cancellable"):
        JobRun.objects.filter(pk=run.pk).update(
            state="CANCEL_REQUESTED",
            cancel_requested_by=user(),
            cancel_requested_at=Now(),
            cancel_reason="test",
        )
    with db_refuses("immutable_column"):
        JobDefinition.objects.filter(job_type="db_backup").update(protected=False)


def test_safe_cancel_needs_who_when_and_reason() -> None:
    JobDefinition.objects.create(
        job_type="syn_report", name_fa="گزارش ساختگی", cancellable=True, protected=False
    )
    run = _run("syn_report", state="RUNNING", started_at=Now())
    with db_refuses("ck_job_run_cancel_reason"):
        JobRun.objects.filter(pk=run.pk).update(
            state="CANCEL_REQUESTED",
            cancel_requested_by=user(),
            cancel_requested_at=Now(),
            cancel_reason="no",
        )
    JobRun.objects.filter(pk=run.pk).update(
        state="CANCEL_REQUESTED",
        cancel_requested_by=user(),
        cancel_requested_at=Now(),
        cancel_reason="synthetic",
    )
    JobRun.objects.filter(pk=run.pk).update(state="CANCELLED", finished_at=Now())
    with db_refuses("terminal_immutable"):
        JobRun.objects.filter(pk=run.pk).update(state="RUNNING", finished_at=None)
    with db_refuses("uq_job_run_task_key"):
        _run("syn_report", task_key=run.task_key)
    with db_refuses("ck_job_run_failed_has_code"):
        _run("syn_report", state="FAILED", started_at=Now(), finished_at=Now())


def test_audit_integrity_runs_are_append_only() -> None:
    now = timezone.now()
    with db_refuses("ck_audit_integrity_run_broken_ref"):
        AuditIntegrityRun.objects.create(started_at=now, finished_at=now, status="BROKEN", events_checked=3)
    r = AuditIntegrityRun.objects.create(started_at=now, finished_at=now, status="OK", events_checked=0)
    with db_refuses("append-only"):
        AuditIntegrityRun.objects.filter(pk=r.pk).update(status="BROKEN")
