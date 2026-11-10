"""PHASE_01 / 01.6 Integration: event catalogue (producer contract + golden), provenance, consumer schema
versioning (N and N-1), poison events -> dead letter at once, per-aggregate ordering (also under concurrent
dispatchers), delivery freshness / blocked aggregates in the health snapshot and in GET /admin/health.

Consumers are SYNTHETIC test consumers (``platform.synthetic_*``); no business consumer exists in PHASE_01.
"""

from __future__ import annotations

import ast
import itertools
import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings as dj_settings
from django.db.migrations.loader import MigrationLoader
from openapi_schema_validator import OAS31Validator

from platform_core.engine import consumers as cs
from platform_core.engine import events as ev
from platform_core.engine import outbox as ob
from platform_core.engine.context import Actor, RequestContext
from platform_core.engine.errors import EngineContractError
from platform_core.engine.uow import unit_of_work
from platform_core.identity import roles, users
from platform_core.jobs import service as jobs
from platform_core.models import CompensationRecord, DeliveryStatus, InboxEvent, OutboxEvent
from platform_core.ops import monitoring
from platform_core.org import service as org
from platform_core.params import service as params

from . import openapi_contract as oc
from .engine_fixtures import PASSWORD, person, with_role
from .engine_fixtures import network as set_network
from .factories import outbox_event
from .phase01_api import get, session_client, with_roles
from .phase01_factories import SYN
from .threads import run_concurrently

S = DeliveryStatus
GOLDEN = Path(__file__).parent / "golden" / "event_catalogue.golden.json"
SOURCE_ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2030, 1, 1, tzinfo=UTC)
POLICY = ob.OutboxPolicy(
    max_attempts=4, base_delay=timedelta(seconds=10), factor=2, max_delay=timedelta(minutes=5)
)
SYS = RequestContext(Actor.system())


class Recorder:
    def __init__(self, fail_on: set[tuple[str, int]] | None = None) -> None:
        self.seen: list[ob.EventEnvelope] = []
        self.fail_on = set(fail_on or ())
        self.lock = threading.Lock()

    def __call__(self, env: ob.EventEnvelope, hctx: cs.HandlerContext) -> None:
        with self.lock:
            key = (env.aggregate_id, env.aggregate_version)
            if key in self.fail_on:
                self.fail_on.discard(key)  # fail once
                raise RuntimeError("SYNTHETIC transient failure")
            self.seen.append(env)


def _handler(name: str, fn: Any, types: frozenset[str]) -> cs.EventHandler:
    return cs.EventHandler(
        consumer=f"platform.{name}",
        event_types=types,
        handle=fn,
        compensation_doc="SYNTHETIC test consumer: no business effect to undo.",
    )


def _publisher(*handlers: cs.EventHandler, catalogue: ev.Catalogue = ev.CATALOGUE) -> cs.RegistryPublisher:
    reg = cs.HandlerRegistry()
    for h in handlers:
        reg.register(h)
    return cs.RegistryPublisher(reg, catalogue=catalogue)


# ----------------------------------------------------------------------------------------- catalogue golden
def test_catalogue_equals_the_reviewed_golden() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert golden["catalogue"] == ev.CATALOGUE.as_dict()
    assert golden["schema_migration_head"] == ev.SCHEMA_MIGRATION_HEAD
    assert golden["source_system"] == ev.SOURCE_SYSTEM


def test_every_payload_schema_is_valid_json_schema_and_s1() -> None:
    for t, spec in ev.CATALOGUE.as_dict().items():
        assert spec["sensitivity"] == "S1", t
        assert spec["producer"].startswith("platform_core."), t
        assert spec["accepted_versions"] == [spec["current_version"]], t  # PHASE_01: every type is still v1
        for schema in spec["versions"].values():
            OAS31Validator.check_schema(schema)  # JSON Schema 2020-12 (OpenAPI 3.1 dialect)
            assert schema["additionalProperties"] is False
            # identifiers / codes / counts only: no free-text field names
            for name in schema["properties"]:
                assert name not in {"name", "display_name", "username", "note", "reason", "title_fa"}, (
                    t,
                    name,
                )


def test_schema_migration_head_is_the_graph_leaf() -> None:
    loader = MigrationLoader(None, ignore_no_migrations=True)
    leaves = loader.graph.leaf_nodes("platform_core")
    assert [f"{a}.{n}" for a, n in leaves] == [ev.SCHEMA_MIGRATION_HEAD]


def _literal_emits() -> set[str]:
    out: set[str] = set()
    for path in SOURCE_ROOT.rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "emit":
                for kw in node.keywords:
                    if kw.arg == "event_type" and isinstance(kw.value, ast.Constant):
                        out.add(str(kw.value.value))
            # helpers called with literal (action, event_type) pairs: "platform.x.verb", "platform.x.verbed"
            if isinstance(node, ast.Call):
                consts = [
                    a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)
                ]
                for a, b in itertools.pairwise(consts):
                    if a.startswith("platform.") and b.startswith("platform.") and a != b and "." in b:
                        if b.rsplit(".", 1)[0] == a.rsplit(".", 1)[0]:
                            out.add(b)
    return out


def test_every_literal_event_type_in_the_code_is_catalogued() -> None:
    literal = _literal_emits()
    assert len(literal) >= 25, sorted(literal)  # the scan found the emit sites
    assert literal - set(ev.CATALOGUE.event_types) == set()


# ----------------------------------------------------------------------------------------- producer side
@pytest.mark.django_db
def test_emit_refuses_events_outside_the_catalogue_contract(settings: Any) -> None:
    good: dict[str, Any] = {"id": str(uuid.uuid4()), "status": "ACTIVE"}
    cases: list[tuple[str, str, int, dict[str, Any], str]] = [
        ("platform.identity.user.unknown_verb", "platform.user", 1, good, "EVENT_NOT_IN_CATALOGUE"),
        ("platform.identity.user.updated", "platform.role", 1, good, "EVENT_AGGREGATE_MISMATCH"),
        ("platform.identity.user.updated", "platform.user", 2, good, "EVENT_SCHEMA_VERSION"),
        ("platform.identity.user.updated", "platform.user", 1, {**good, "username": "x"}, "UNKNOWN_FIELD"),
        ("platform.identity.user.updated", "platform.user", 1, {"id": good["id"]}, "status:MISSING"),
        ("platform.identity.user.updated", "platform.user", 1, {**good, "id": "not-a-uuid"}, "id:TYPE"),
        ("platform.identity.user.updated", "platform.user", 1, {**good, "status": "lower"}, "status:TYPE"),
        (
            "platform.identity.user.mfa_reset",
            "platform.user",
            1,
            {"id": good["id"], "revoked_factors": True},
            "TYPE",
        ),
    ]
    for event_type, agg, version, payload, code in cases:
        with pytest.raises(EngineContractError, match=code), unit_of_work(SYS) as uow:
            uow.audit(action="platform.synthetic.update", resource_type="platform.synthetic")
            uow.emit(
                event_type=event_type,
                aggregate_type=agg,
                aggregate_id="1",
                aggregate_version=1,
                payload=payload,
                schema_version=version,
            )
    assert not OutboxEvent.objects.exists()  # every violation rolled the whole unit of work back
    # the synthetic namespace is accepted only in ALEEKHAN_ENV test / dev, never in staging / prod
    settings.ALEEKHAN_ENV = "staging"
    with pytest.raises(EngineContractError, match="EVENT_NOT_IN_CATALOGUE"), unit_of_work(SYS) as uow:
        uow.audit(action="platform.synthetic.update", resource_type="platform.synthetic")
        uow.emit(
            event_type="platform.synthetic.updated", aggregate_type="platform.synthetic", aggregate_id="1",
            aggregate_version=1,
        )  # fmt: skip


def _validate_all_rows() -> list[OutboxEvent]:
    rows = list(OutboxEvent.objects.order_by("id"))
    for row in rows:
        spec = ev.CATALOGUE.get(row.event_type)
        assert spec is not None, row.event_type
        schema = ev.json_schema(spec.versions[row.schema_version])
        OAS31Validator(schema).validate(row.payload)  # independent validator (dev dependency)
        assert row.aggregate_type == spec.aggregate_type
        assert (row.producer, row.build_commit, row.schema_migration) == (
            spec.producer,
            dj_settings.ALEEKHAN_BUILD_COMMIT,
            ev.SCHEMA_MIGRATION_HEAD,
        ), row.event_type
    return rows


@pytest.mark.django_db
def test_golden_flow_every_emitted_event_matches_the_catalogue_and_carries_provenance(
    settings: Any, tmp_path: Any
) -> None:
    """Real use cases of identity, roles, org, workflow, params and jobs; then every outbox row is checked."""
    settings.ALEEKHAN_DOCUMENT_STORAGE_ROOT = str(tmp_path)
    from platform_core.documents import scanner
    from platform_core.documents import service as docs

    _o, owner = with_role("owner_admin")
    u = users.create_user(
        owner,
        username=f"syn.ev.{uuid.uuid4().hex[:6]}",
        display_name="کاربر ساختگی",
        account_kind="PERSON",
        initial_password=PASSWORD,
        reason="synthetic",
    )
    ra = roles.grant_role(owner, user_id=u.pk, role_code="document_approver", reason="synthetic grant")
    assert ra.approval_request_id is not None  # assignment.changed + approval.raised
    root = org.create_unit(
        owner, code=f"syn_ev_{uuid.uuid4().hex[:6]}", name_fa=f"ریشه {SYN}", unit_type="COMPANY",
        parent_id=None, reason="synthetic", provenance="SEED_SYNTHETIC",
    )  # fmt: skip
    assert root.pk
    params.define_parameter(
        owner, key=f"syn_ev_{uuid.uuid4().hex[:6]}", label_fa="پارامتر ساختگی", datatype="INTEGER",
        owner_module="ops", classification="TECHNICAL", reason="synthetic",
    )  # fmt: skip
    jobs.enqueue(SYS, job_type="session_expiry_sweep", task_key=f"syn-ev-{uuid.uuid4().hex[:6]}")
    _c, ctl = with_role("document_controller")
    doc = docs.create_document(ctl, document_type="syn_drawing", title_fa="نقشه ساختگی", sensitivity="S1")
    rev = docs.upload_revision(ctl, doc.pk, filename="a.pdf", data=b"%PDF-1.7\n%synthetic\n%%EOF\n")
    docs.scan_revision(rev.pk, scanner.FakeScannerForTests())
    docs.submit_revision(ctl, rev.pk)
    rows = _validate_all_rows()
    types = {r.event_type for r in rows}
    assert {
        "platform.identity.user.created",
        "platform.identity.assignment.changed",
        "platform.workflow.approval.raised",
        "platform.org.unit.created",
        "platform.config.parameter.defined",
        "platform.ops.job.changed",
        "platform.document.created",
        "platform.document.revision.changed",
    } <= types


# ----------------------------------------------------------------------------------------- consumer side
V2_TYPE = "platform.synthetic.versioned"
SYN_CATALOGUE = ev.Catalogue(
    (
        ev.EventSpec(
            V2_TYPE,
            "platform_core.synthetic",
            "platform.synthetic",
            "synthetic v2 event (test only)",
            {1: {"id": ev.F("uuid")}, 2: {"id": ev.F("uuid"), "status": ev.F("code")}},
            upcasters={1: lambda p: {**p, "status": "UNKNOWN"}},
        ),
    )
)


def _row(version: int, payload: dict[str, Any], agg: str = "syn-v") -> OutboxEvent:
    return outbox_event(
        event_type=V2_TYPE, schema_version=version, payload=payload, aggregate_id=agg, next_attempt_at=T0
    )


def test_spec_versions_and_upcasters_are_validated() -> None:
    spec = SYN_CATALOGUE.get(V2_TYPE)
    assert spec is not None and spec.current_version == 2 and spec.accepted_versions == {1, 2}
    with pytest.raises(ValueError):
        ev.EventSpec("platform.x.y", "p", "a", "d", {1: {}, 3: {}})
    with pytest.raises(ValueError):
        ev.EventSpec("platform.x.y", "p", "a", "d", {1: {}}, upcasters={1: lambda p: dict(p)})
    with pytest.raises(ValueError):
        ev.F("free_text")


@pytest.mark.django_db
def test_consumer_accepts_n_and_upcasts_n_minus_1() -> None:
    rec = Recorder()
    pub = _publisher(_handler("synthetic_v", rec, frozenset({V2_TYPE})), catalogue=SYN_CATALOGUE)
    a = str(uuid.uuid4())
    b = str(uuid.uuid4())
    _row(2, {"id": a, "status": "ACTIVE"}, agg="syn-v2")
    _row(1, {"id": b}, agg="syn-v1")
    stats = ob.dispatch_once(pub, POLICY, now=T0)
    assert stats.delivered == 2
    got = {e.payload["id"]: (e.schema_version, dict(e.payload)) for e in rec.seen}
    assert got[a] == (2, {"id": a, "status": "ACTIVE"})
    assert got[b] == (2, {"id": b, "status": "UNKNOWN"})  # handlers only ever see the current version


@pytest.mark.django_db
def test_incompatible_payload_is_dead_lettered_at_once_with_compensation() -> None:
    rec = Recorder()
    pub = _publisher(_handler("synthetic_v", rec, frozenset({V2_TYPE})), catalogue=SYN_CATALOGUE)
    bad = _row(2, {"id": "nope"}, agg="syn-bad")
    stats = ob.dispatch_once(pub, POLICY, now=T0, on_dead_letter=pub.on_dead_letter)
    bad.refresh_from_db()
    assert (stats.dead_lettered, bad.delivery_status, bad.attempts) == (1, S.DEAD_LETTER, 1)
    assert bad.last_error == "SCHEMA_INVALID:v2"  # safe code, no payload value
    assert rec.seen == [] and not InboxEvent.objects.exists()
    comp = CompensationRecord.objects.get(event_id=bad.event_id)
    assert (comp.consumer, comp.outcome) == ("platform.synthetic_v", "MANUAL_REQUIRED")


@pytest.mark.django_db
def test_unsupported_old_version_is_permanent_newer_version_waits() -> None:
    three = ev.Catalogue(
        (
            ev.EventSpec(
                V2_TYPE, "platform_core.synthetic", "platform.synthetic", "v3 (test only)",
                {1: {"id": ev.F("uuid")}, 2: {"id": ev.F("uuid")}, 3: {"id": ev.F("uuid")}},
                upcasters={2: lambda p: dict(p)},
            ),
        )
    )  # fmt: skip
    pub = _publisher(_handler("synthetic_v", Recorder(), frozenset({V2_TYPE})), catalogue=three)
    old = _row(1, {"id": str(uuid.uuid4())}, agg="syn-old")
    ahead = _row(4, {"id": str(uuid.uuid4())}, agg="syn-ahead")
    ob.dispatch_once(pub, POLICY, now=T0)
    old.refresh_from_db()
    ahead.refresh_from_db()
    assert (old.delivery_status, old.last_error) == (S.DEAD_LETTER, "SCHEMA_VERSION_UNSUPPORTED:v1")
    assert (ahead.delivery_status, ahead.last_error) == (S.FAILED, "SCHEMA_VERSION_AHEAD:v4>v3")
    assert ahead.next_attempt_at == T0 + POLICY.delay_after(1, ahead.event_id)  # retried with backoff


@pytest.mark.django_db
def test_handler_sees_the_provenance_of_the_producing_code() -> None:
    _o, owner = with_role("owner_admin")
    org.create_unit(
        owner, code=f"syn_pv_{uuid.uuid4().hex[:6]}", name_fa=f"ریشه {SYN}", unit_type="COMPANY",
        parent_id=None, reason="synthetic", provenance="SEED_SYNTHETIC",
    )  # fmt: skip
    rec = Recorder()
    pub = _publisher(_handler("synthetic_org", rec, frozenset({"platform.org.unit.created"})))
    while ob.dispatch_once(pub, POLICY).claimed:
        pass
    assert len(rec.seen) == 1
    assert dict(rec.seen[0].provenance) == {
        "producer": "platform_core.org",
        "build_commit": dj_settings.ALEEKHAN_BUILD_COMMIT,
        "schema_migration": ev.SCHEMA_MIGRATION_HEAD,
    }


# ----------------------------------------------------------------------------------------- ordering
EVT = "platform.synthetic.created"


@pytest.mark.django_db
def test_a_failing_event_holds_back_later_events_of_its_aggregate_only() -> None:
    first = outbox_event(aggregate_id="agg-a", aggregate_version=1, next_attempt_at=T0)
    second = outbox_event(aggregate_id="agg-a", aggregate_version=2, next_attempt_at=T0)
    other = outbox_event(aggregate_id="agg-b", aggregate_version=1, next_attempt_at=T0)
    rec = Recorder(fail_on={("agg-a", 1)})
    pub = _publisher(_handler("synthetic_o", rec, frozenset({EVT})))
    stats = ob.dispatch_once(pub, POLICY, now=T0)
    assert stats.claimed == 2  # agg-a v1 (fails) + agg-b v1; agg-a v2 waits behind v1
    for r in (first, second, other):
        r.refresh_from_db()
    assert (first.delivery_status, second.delivery_status, other.delivery_status) == (
        S.FAILED,
        S.PENDING,
        S.ACKED,
    )
    later = T0 + timedelta(hours=1)
    assert ob.dispatch_once(pub, POLICY, now=later).claimed == 1  # v1 retried; v2 still behind it
    assert ob.dispatch_once(pub, POLICY, now=later).claimed == 1  # now v2
    assert [(e.aggregate_id, e.aggregate_version) for e in rec.seen] == [
        ("agg-b", 1),
        ("agg-a", 1),
        ("agg-a", 2),
    ]


@pytest.mark.django_db
def test_dead_letter_head_blocks_its_aggregate_until_replayed_and_health_shows_it() -> None:
    head = outbox_event(aggregate_id="agg-d", aggregate_version=1, next_attempt_at=T0)
    tail = outbox_event(aggregate_id="agg-d", aggregate_version=2, next_attempt_at=T0)
    rec = Recorder(fail_on={("agg-d", 1)})
    pub = _publisher(_handler("synthetic_d", rec, frozenset({EVT})))
    one = ob.OutboxPolicy(max_attempts=1, base_delay=timedelta(seconds=1))
    ob.dispatch_once(pub, one, now=T0)
    head.refresh_from_db()
    assert head.delivery_status == S.DEAD_LETTER
    assert ob.dispatch_once(pub, one, now=T0 + timedelta(hours=1)).claimed == 0  # tail is held
    h = monitoring.integration_health(now=T0)
    assert (h.blocked_aggregates, h.held_events) == (1, 1)
    snap = monitoring.outbox_snapshot(now=T0)
    assert "ORDERING_BLOCKED" in snap.reasons and snap.verdict == "critical"
    assert snap.as_dict()["integration"]["held_events"] == 1
    user = person()
    ob.replay_dead_letter(RequestContext(Actor.user(user.pk)), head.event_id, reason="synthetic replay")
    while ob.dispatch_once(pub, one, now=T0 + timedelta(hours=2)).claimed:
        pass
    tail.refresh_from_db()
    assert tail.delivery_status == S.ACKED
    assert [e.aggregate_version for e in rec.seen] == [1, 2]
    assert monitoring.integration_health(now=T0).blocked_aggregates == 0


@pytest.mark.django_db
def test_ordering_can_be_switched_off_by_policy() -> None:
    for v in (1, 2, 3):
        outbox_event(aggregate_id="agg-x", aggregate_version=v, next_attempt_at=T0)
    unordered = ob.OutboxPolicy(per_aggregate_order=False)
    assert len(ob.claim_batch(unordered, now=T0)) == 3
    OutboxEvent.objects.update(delivery_status=S.PENDING, dispatched_at=None)
    assert len(ob.claim_batch(ob.OutboxPolicy(), now=T0)) == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("audit_cleanup")
def test_concurrent_dispatchers_keep_per_aggregate_order_with_retries() -> None:
    aggregates = [f"agg-r{i}" for i in range(6)]
    for v in range(1, 7):
        for a in aggregates:
            outbox_event(aggregate_id=a, aggregate_version=v, next_attempt_at=T0)
    rec = Recorder(fail_on={(a, 3) for a in aggregates})  # every aggregate fails once in the middle
    pub = _publisher(_handler("synthetic_r", rec, frozenset({EVT})))
    policy = ob.OutboxPolicy(max_attempts=5, base_delay=timedelta(seconds=1), batch_size=4)
    clock = itertools.count(1)
    clock_lock = threading.Lock()

    def dispatcher(_: int) -> int:
        for _round in range(400):
            with clock_lock:
                now = T0 + timedelta(minutes=next(clock))
            ob.dispatch_once(pub, policy, now=now)
            if not OutboxEvent.objects.exclude(delivery_status=S.ACKED).exists():
                return 0
        return 1

    results = run_concurrently(dispatcher, 4)
    assert results == [0, 0, 0, 0], results
    assert OutboxEvent.objects.filter(delivery_status=S.ACKED).count() == 36
    for a in aggregates:
        assert [e.aggregate_version for e in rec.seen if e.aggregate_id == a] == [1, 2, 3, 4, 5, 6], a
    assert InboxEvent.objects.count() == 36


# ----------------------------------------------------------------------------------------- freshness
@pytest.mark.django_db
def test_lag_and_stale_flag() -> None:
    assert monitoring.integration_health().lag_seconds is None
    row = outbox_event(aggregate_id="agg-s")
    row.refresh_from_db()
    later = row.created_at + timedelta(minutes=20)
    h = monitoring.integration_health(now=later)
    assert h.lag_seconds == 1200 and h.stale is True
    assert h.stale_after_seconds == 900  # TECHNICAL DEFAULT
    assert monitoring.integration_health(now=row.created_at + timedelta(minutes=15)).stale is False
    assert "DELIVERY_STALE" in monitoring.outbox_snapshot(now=later).reasons
    OutboxEvent.objects.filter(pk=row.pk).update(delivery_status=S.DISPATCHED, dispatched_at=row.created_at)
    OutboxEvent.objects.filter(pk=row.pk).update(delivery_status=S.ACKED, acked_at=row.created_at)
    h = monitoring.integration_health()
    assert (h.lag_seconds, h.stale) == (None, False) and h.last_acked_at is not None


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("api_db", "clear_cache")
def test_health_endpoint_exposes_integration_freshness(settings: Any) -> None:
    set_network(settings)
    outbox_event(aggregate_id="agg-h", delivery_status=S.DEAD_LETTER)
    outbox_event(aggregate_id="agg-h")
    c = session_client(with_roles("owner_admin"))
    r = get(c, "/admin/health")
    assert r.status_code == 200, r.content
    oc.validate_response("/admin/health", "get", r)
    integ = json.loads(r.content)["integration"]
    assert integ["blocked_aggregates"] == 1 and integ["held_events"] == 1
    assert set(integ) == {
        "lag_seconds",
        "stale",
        "stale_after_seconds",
        "blocked_aggregates",
        "held_events",
        "open_conflicts",
        "compensation_open",
        "last_acked_at",
    }
    # management_viewer holds health.read too; it_ops / auditor rules unchanged (deny without the grant)
    r = get(session_client(with_roles("employee")), "/admin/health")
    assert r.status_code == 403
