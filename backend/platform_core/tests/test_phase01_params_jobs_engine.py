"""Parameters (STATE_TRANSITIONS 4.9, Q-0103), job runs (4.7, Gate-1 safe cancel), retention (DEC-032) and the
console owner bootstrap / recovery (DEC-003 / DEC-054)."""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.core.management import CommandError, call_command

from platform_core.engine.context import Actor, RequestContext, db_now
from platform_core.engine.errors import (
    AccessDenied,
    JobProtected,
    MfaRequired,
    RuleNotApproved,
    StateTransitionNotAllowed,
    ValidationFailed,
)
from platform_core.identity.models import Credential, LoginAttempt, RoleAssignment, User
from platform_core.jobs import retention
from platform_core.jobs import service as jobs
from platform_core.jobs.models import JobRun
from platform_core.models import AuditEvent
from platform_core.params import service as params
from platform_core.params.models import ParameterDefinition, ParameterValue
from platform_core.params.values import effective, effective_int

from .engine_fixtures import SYN_PW_OWNER, SYN_PW_WEAK, caller, give_role, person, with_role

pytestmark = pytest.mark.django_db
SYS = RequestContext(Actor.system())


# ------------------------------------------------------------------------------------------ parameters
def test_effective_values_come_from_the_seed() -> None:
    assert effective_int("lockout_max_failures") == 5
    assert effective("session_limit_exceeded_action") == "END_OLDEST_SESSION"
    assert effective_int("document_upload_max_bytes") == 26_214_400


def test_owner_policy_published_by_owner_alone_with_step_up_and_reason() -> None:
    o, owner = with_role("owner_admin")
    pv = params.publish_owner_policy(owner, key="lockout_max_failures", value="6", reason="employer decision")
    assert pv.status == "PUBLISHED" and pv.proposed_by_id == pv.published_by_id == o.pk
    assert effective_int("lockout_max_failures") == 6
    assert (
        ParameterValue.objects.filter(definition_id="lockout_max_failures", status="SUPERSEDED").count() == 1
    )
    assert AuditEvent.objects.filter(
        action="platform.config.parameter.publish", resource_id=str(pv.pk)
    ).exists()
    with pytest.raises(ValidationFailed):
        params.publish_owner_policy(owner, key="lockout_max_failures", value="7", reason="")
    with pytest.raises(MfaRequired):
        params.publish_owner_policy(
            caller(o, mfa=False), key="lockout_max_failures", value="7", reason="change"
        )
    with pytest.raises(ValidationFailed):  # never back-dated
        params.publish_owner_policy(
            owner,
            key="lockout_max_failures",
            value="7",
            reason="late",
            effective_from=db_now() - timedelta(days=1),
        )
    _it, ops = with_role("it_ops")
    with pytest.raises(AccessDenied):
        params.propose(ops, key="lockout_max_failures", value="7", reason="ops idea")


def test_business_rule_parameters_are_blocked_by_their_decision() -> None:
    ParameterDefinition.objects.create(
        key="syn_business_threshold", label_fa="آستانه ساختگی", datatype="INTEGER", owner_module="quality",
        classification="BUSINESS_RULE", decision_id="DEC-016",
    )  # fmt: skip
    _o, owner = with_role("owner_admin")
    with pytest.raises(RuleNotApproved) as exc:
        params.propose(owner, key="syn_business_threshold", value="3", reason="proposal")
    assert exc.value.decision_id == "DEC-016"


def test_parameter_machine() -> None:
    m = params.PARAMETER_VALUE_MACHINE
    assert m.can("PENDING_APPROVAL", "PUBLISHED") and m.can("PUBLISHED", "SUPERSEDED")
    assert not m.can("PUBLISHED", "DRAFT") and not m.can("REJECTED", "PUBLISHED")


def test_technical_parameter_publish_needs_the_publish_permission() -> None:
    ParameterDefinition.objects.create(
        key="syn_tech_batch", label_fa="اندازه دسته ساختگی", datatype="INTEGER", owner_module="ops",
        classification="TECHNICAL",
    )  # fmt: skip
    _o, owner = with_role("owner_admin")
    pv = params.propose(owner, key="syn_tech_batch", value="100", reason="ops default")
    assert pv.status == "PENDING_APPROVAL"
    with pytest.raises(AccessDenied):  # owner_admin is TECHNICAL: publish is a business-approval permission
        params.publish(owner, pv.pk)
    approver = person()
    give_role(approver, "config_approver")
    assert params.publish(caller(approver), pv.pk).status == "PUBLISHED"
    assert effective_int("syn_tech_batch") == 100


# ------------------------------------------------------------------------------------------------ jobs
def test_job_machine_every_pair() -> None:
    edges = {
        ("QUEUED", "RUNNING"), ("QUEUED", "CANCELLED"), ("RUNNING", "SUCCEEDED"), ("RUNNING", "FAILED"),
        ("RUNNING", "CANCEL_REQUESTED"), ("CANCEL_REQUESTED", "CANCELLED"), ("CANCEL_REQUESTED", "SUCCEEDED"),
        ("CANCEL_REQUESTED", "FAILED"),
    }  # fmt: skip
    m = jobs.JOB_MACHINE
    for a in sorted(m.states):
        for b in sorted(m.states):
            assert m.can(a, b) is ((a, b) in edges), (a, b)


def test_protected_jobs_are_never_cancelled() -> None:
    _o, owner = with_role("owner_admin")
    run = jobs.enqueue(SYS, job_type="db_backup", task_key="syn-backup-1")
    with pytest.raises(JobProtected):
        jobs.request_cancel(owner, run.pk, reason="stop the backup")
    with pytest.raises(RuleNotApproved) as exc:
        jobs.force_kill(owner, run.pk, reason="kill")
    assert exc.value.decision_id == "DEC-024"


def test_safe_cancel_queued_running_checkpoint_and_too_late() -> None:
    _o, ops = with_role("it_ops")
    queued = jobs.enqueue(SYS, job_type="session_expiry_sweep", task_key="syn-q")
    assert jobs.enqueue(SYS, job_type="session_expiry_sweep", task_key="syn-q").pk == queued.pk  # idempotent
    with pytest.raises(ValidationFailed):
        jobs.request_cancel(ops, queued.pk, reason="")
    assert jobs.request_cancel(ops, queued.pk, reason="not needed").state == "CANCELLED"
    running = jobs.enqueue(SYS, job_type="session_expiry_sweep", task_key="syn-r")
    jobs.start(running.pk)
    assert jobs.checkpoint(running.pk, progress=10) is True
    assert jobs.request_cancel(ops, running.pk, reason="maintenance").state == "CANCEL_REQUESTED"
    assert jobs.checkpoint(running.pk) is False
    assert JobRun.objects.get(pk=running.pk).state == "CANCELLED"
    late = jobs.enqueue(SYS, job_type="session_expiry_sweep", task_key="syn-l")
    jobs.start(late.pk)
    jobs.request_cancel(ops, late.pk, reason="maintenance")
    done = jobs.finish(late.pk, ok=True)
    assert done.state == "SUCCEEDED" and done.cancel_too_late is True
    with pytest.raises(StateTransitionNotAllowed):
        jobs.request_cancel(ops, done.pk, reason="again")
    _e, emp = with_role("employee")
    with pytest.raises(AccessDenied):
        jobs.request_cancel(emp, late.pk, reason="not allowed")


def test_housekeeping_run_and_audit_integrity_job() -> None:
    run = jobs.run_job("audit_integrity_check")
    assert run.state == "SUCCEEDED"
    from platform_core.jobs.models import AuditIntegrityRun

    assert AuditIntegrityRun.objects.filter(status="OK").exists()


# ----------------------------------------------------------------------------------------- retention
def test_login_events_older_than_retention_are_purged_newer_are_kept() -> None:
    old = LoginAttempt.objects.create(
        username_attempted="syn.old",
        outcome="OK",
        network_zone="INTERNAL",
        occurred_at=db_now() - timedelta(days=24 * 31 + 5),
    )
    new = LoginAttempt.objects.create(username_attempted="syn.new", outcome="OK", network_zone="INTERNAL")
    assert retention.purge_login_events() == 1
    assert (
        not LoginAttempt.objects.filter(pk=old.pk).exists()
        and LoginAttempt.objects.filter(pk=new.pk).exists()
    )


def test_audit_events_are_never_purged() -> None:
    with pytest.raises(AccessDenied):
        retention.purge_audit_events()


# ------------------------------------------------------------------------------------------ bootstrap
def _bootstrap(*args: str, password: str = "Syn-Owner-Pass-1!") -> str:  # noqa: S107
    out = io.StringIO()
    import sys

    stdin, sys.stdin = sys.stdin, io.StringIO(password + "\n")
    try:
        call_command("bootstrap_owner", *args, "--password-stdin", stdout=out)
    finally:
        sys.stdin = stdin
    return out.getvalue()


def test_bootstrap_creates_the_first_owner_once_and_recovery_resets() -> None:
    out = _bootstrap("--username", "syn.owner", "--display-name", "مالک ساختگی", "--reason", "first start")
    assert "Syn-Owner-Pass-1!" not in out
    owner = User.objects.get(username="syn.owner")
    ra = RoleAssignment.objects.get(user=owner)
    assert (ra.role.code, ra.granted_via, ra.granted_by_id, ra.status) == (
        "owner_admin",
        "CONSOLE_BOOTSTRAP",
        None,
        "ACTIVE",
    )
    cred = Credential.objects.get(user=owner)
    assert cred.is_one_time and cred.must_change and owner.status == "CREATED"
    assert AuditEvent.objects.filter(action="platform.identity.owner.bootstrap", actor_type="SYSTEM").exists()
    with pytest.raises(CommandError, match="STATE_TRANSITION_NOT_ALLOWED"):
        _bootstrap("--username", "syn.owner2", "--display-name", "دوم", "--reason", "second")
    with pytest.raises(CommandError, match="PASSWORD_POLICY_VIOLATION"):
        _bootstrap(
            "--recover",
            "--username",
            "syn.owner",
            "--reason",
            "lost phone",
            password=SYN_PW_WEAK,
        )
    out = _bootstrap(
        "--recover",
        "--username",
        "syn.owner",
        "--reason",
        "lost phone",
        password=SYN_PW_OWNER,
    )
    assert "recovered" in out and "Syn-Owner-Pass-2!" not in out
    assert AuditEvent.objects.filter(action="platform.identity.owner.recover").exists()
    with pytest.raises(CommandError, match="NOT_FOUND"):
        _bootstrap("--recover", "--username", "syn.nobody", "--reason", "x y z")
