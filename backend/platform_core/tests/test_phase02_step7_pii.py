"""PHASE_02 / 02.7: the customer representative NAME (DEC-058, PII) lives in exactly one place.

A full order lifecycle runs over HTTP with real sessions (create with a name, change it, add a line,
validate, confirm with serials and snapshots, read by an allowed role (audited) and by the management viewer
(masked), list, idempotent replay) plus a change request through the engine (new order version + serial
snapshot). Then every row of every application table (``platform_*``, ``identity_*``, ``commercial_*``, via
``row_to_json``) and every log record is searched: the two synthetic names appear ONLY in
``commercial_customer_order.customer_representative_name`` - never in audit values, outbox payloads,
idempotency records (request hash + stored responses), order version images, serial snapshots, staging rows
or logs. The names are random synthetic Persian letters (no real person, R-38).
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

import pytest
from django.db import connection

from platform_core.commercial import changes
from platform_core.commercial.models import CustomerOrder, CustomerOrderLine
from platform_core.models import AuditEvent, IdempotencyRecord, OutboxEvent
from platform_core.product_identity.models import SerialSnapshot

from . import openapi_contract as oc
from . import phase02_factories as f
from .phase01_api import body, get, idem, if_match, patch, post, session_client
from .phase02_engine import holder

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("api_db", "clear_cache")]
_LETTERS = "ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی"
ORDERS = "/commercial/customer-orders"
APP_TABLES = r"^(platform|identity|commercial)_"


def _word() -> str:
    return "".join(secrets.choice(_LETTERS) for _ in range(7))


def _synthetic_name() -> str:
    return f"نماینده ساختگی {_word()} {_word()}"


def _ok(r: Any, path: str, method: str, status: int = 200) -> dict[str, Any]:
    assert r.status_code == status, (method, path, r.status_code, r.content[:300])
    oc.validate_response(path, method, r)
    out: dict[str, Any] = body(r)
    return out


def _all_rows() -> str:
    """Every row of every application table as JSON text; the one legitimate column is removed."""
    chunks = []
    with connection.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
            "AND table_type = 'BASE TABLE' AND table_name ~ %s ORDER BY table_name",
            [APP_TABLES],
        )
        tables = [t for (t,) in cur.fetchall()]
        for t in tables:
            strip = " - 'customer_representative_name'" if t == "commercial_customer_order" else ""
            # table names come from information_schema (not user input); quoted as identifiers
            sql = (
                "SELECT coalesce(string_agg((row_to_json(x)::jsonb" + strip + ")::text, chr(10)), '') "
                f'FROM public."{t}" x'
            )
            cur.execute(sql)
            chunks.append(cur.fetchone()[0])
    assert len(tables) >= 60, len(tables)
    return "\n".join(chunks)


def test_representative_name_never_leaves_its_column(caplog: Any) -> None:
    caplog.set_level(logging.DEBUG)
    name1, name2 = _synthetic_name(), _synthetic_name()
    co, po, cm, po2 = (
        holder("commercial_officer"),
        holder("planning_officer"),
        holder("commercial_manager"),
        holder("planning_officer"),
    )
    viewer, owner = holder("management_viewer"), holder("owner_admin")
    c_co, c_po = session_client(co.user), session_client(po.user)
    cust = f.customer()
    key = idem()
    create = {
        "customer_id": str(cust.pk),
        "order_type": "series_production",
        "order_date": "2030-01-10",
        "customer_representative_name": name1,
    }
    o = _ok(post(c_co, ORDERS, create, **key), ORDERS, "post", 201)
    assert o["customer_representative_name"] == "[REDACTED]"  # never echoed by a write
    replay = post(c_co, ORDERS, create, **key)  # idempotent replay: stored response, same redaction
    assert replay.status_code == 201 and replay["Idempotent-Replayed"] == "true"
    one = f"{ORDERS}/{o['order_id']}"
    o = _ok(
        patch(
            c_co,
            one,
            {"customer_representative_name": name2},
            **if_match(o["row_version"]),
        ),
        ORDERS + "/{order_id}",
        "patch",
    )
    style, _rev = f.styled()[3:]
    o = _ok(
        post(c_co, f"{one}/lines", {"style_id": str(style.pk), "quantity": 5}, **if_match(o["row_version"])),
        ORDERS + "/{order_id}/lines",
        "post",
        201,
    )
    o = _ok(
        post(c_co, f"{one}/validate", {}, **if_match(o["row_version"])),
        ORDERS + "/{order_id}/validate",
        "post",
    )
    o = _ok(
        post(c_po, f"{one}/confirm", {}, **if_match(o["row_version"])), ORDERS + "/{order_id}/confirm", "post"
    )
    assert o["status"] == "CONFIRMED"
    # reads: allowed role sees the name (audited, without the value), the viewer sees it masked
    assert _ok(get(c_co, one), ORDERS + "/{order_id}", "get")["customer_representative_name"] == name2
    assert (
        _ok(get(session_client(owner.user), one), ORDERS + "/{order_id}", "get")[
            "customer_representative_name"
        ]
        == name2
    )
    masked = _ok(get(session_client(viewer.user), one), ORDERS + "/{order_id}", "get")
    assert masked["customer_representative_name"] == "[REDACTED]"
    _ok(get(c_co, ORDERS), ORDERS, "get")
    # a change request: a new order version and a new serial snapshot
    order = CustomerOrder.objects.get(pk=o["order_id"])
    line = CustomerOrderLine.objects.get(order=order, status="CONFIRMED")
    cr = changes.create_change_request(
        co.caller,
        order.pk,
        kind="QTY_CHANGE",
        items=[{"line_id": str(line.pk), "quantity": 9}],
        reason="synthetic change",
        expected_version=order.row_version,
        submit=True,
    )
    cr = changes.decide_change_request(cm.caller, cr.pk, approve=True, expected_version=cr.row_version)
    changes.apply_change_request(po2.caller, cr.pk, expected_version=cr.row_version)

    # the evidence tables are populated, so the scan below is meaningful
    assert AuditEvent.objects.filter(action="commercial.order.representative_read").count() >= 2
    assert OutboxEvent.objects.filter(event_type__startswith="commercial.order.").count() >= 4
    assert IdempotencyRecord.objects.filter(endpoint__contains="customer-orders").count() >= 5
    assert SerialSnapshot.objects.count() >= 2
    assert CustomerOrder.objects.get(pk=order.pk).customer_representative_name == name2  # its one column

    rows = _all_rows()
    logs = "\n".join(f"{rec.getMessage()} {rec.__dict__}" for rec in caplog.records)
    assert len(rows) > 2000 and caplog.records
    for where, text in (("database rows outside the order column", rows), ("log records", logs)):
        for n in (name1, name2):
            assert n not in text, f"the representative name was found in {where}"  # value never printed
            for part in n.split()[2:]:  # the random words alone (e.g. a truncated or re-joined copy)
                assert part not in text, f"part of the representative name was found in {where}"
