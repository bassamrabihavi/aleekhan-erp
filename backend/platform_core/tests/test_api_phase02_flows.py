"""PHASE_02 / 02.4 HTTP flows against PostgreSQL (real sessions, committed rows, no DB mock). Synthetic data
only (R-38): ``9x`` type segments, ``9xxx`` products, synthetic customers / representative names.

Covers every PHASE_02 operation's happy path with response-schema validation, the role matrix (DEC-057 v2.1)
on the decisive writes, fresh MFA, ETag / If-Match 412 on real records, idempotent replay (same response,
``Idempotent-Replayed``, one effect; other body -> 422), pagination, rate limit, request id, representative
name masking + read audit (DEC-058), the 2026-11-14 amendments (Jalali numbers, style collision, planning
reject) and ID-01..ID-04 through the HTTP layer, including concurrent confirms through API clients.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import pytest
from django.test import Client, override_settings

from platform_core.engine.context import db_now
from platform_core.identity.models import User
from platform_core.models import AuditEvent
from platform_core.product_identity.jalali import jalali_year_tehran
from platform_core.product_identity.models import ProductClass, Serial, SerialCounter, SerialSnapshot
from platform_core.product_identity.usecase import NUMBER_PATTERN

from . import openapi_contract as oc
from . import phase02_factories as f
from .engine_fixtures import INTERNAL_IP, give_role, person
from .phase01_api import API, body, code, etag_version, get, idem, if_match, patch, post, session_client
from .threads import run_concurrently

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.usefixtures("api_db", "clear_cache")]
SYN_REP = f"نماینده ساختگی {f.SYN}"
SHA = "0" * 63 + "2"


def holder(*roles: str) -> User:
    u = person()
    for r in roles:
        give_role(u, r)
    return u


def ok(r: Any, path: str, method: str, status: int = 200) -> dict[str, Any]:
    assert r.status_code == status, (method, path, r.status_code, r.content[:400])
    oc.validate_response(path, method, r)
    out: dict[str, Any] = body(r)
    return out


def refused(r: Any, path: str, method: str, status: int, top: str, reason: str | None = None) -> None:
    assert r.status_code == status and code(r) == top, (path, r.status_code, r.content[:400])
    if reason is not None:
        assert body(r)["errors"][0]["code"] == reason, body(r)
    oc.validate_response(path, method, r)


class Team:
    def __init__(self) -> None:
        self.co, self.cm, self.cm2 = (
            holder("commercial_officer"),
            holder("commercial_manager"),
            holder("commercial_manager"),
        )
        self.po, self.po2 = holder("planning_officer"), holder("planning_officer")
        self.pds, self.cra = holder("product_data_steward"), holder("code_rule_approver")
        self.viewer = holder("management_viewer")
        self.c = {k: session_client(v) for k, v in vars(self).items() if isinstance(v, User)}


def _chain() -> tuple[Any, Any]:
    _t, _c, _p, s, r = f.styled()
    return s, r


def _draft(t: Team, *, lines: int = 1, rep: str | None = SYN_REP) -> dict[str, Any]:
    cust = f.customer()
    o = ok(
        post(
            t.c["co"],
            "/commercial/customer-orders",
            {
                "customer_id": str(cust.pk),
                "order_type": "series_production",
                "order_date": "2030-01-10",
                "customer_representative_name": rep,
            },
            **idem(),
        ),
        "/commercial/customer-orders",
        "post",
        201,
    )
    s, _r = _chain()
    for _ in range(lines):
        o = ok(
            post(
                t.c["co"],
                f"/commercial/customer-orders/{o['order_id']}/lines",
                {"style_id": str(s.pk), "quantity": 5},
                **if_match(o["row_version"]),
            ),
            "/commercial/customer-orders/{order_id}/lines",
            "post",
            201,
        )
    return o


def _validated(t: Team, **kw: Any) -> dict[str, Any]:
    o = _draft(t, **kw)
    return ok(
        post(
            t.c["co"],
            f"/commercial/customer-orders/{o['order_id']}/validate",
            {},
            **if_match(o["row_version"]),
        ),
        "/commercial/customer-orders/{order_id}/validate",
        "post",
    )


def _confirmed(t: Team, **kw: Any) -> dict[str, Any]:
    o = _validated(t, **kw)
    return ok(
        post(
            t.c["po"],
            f"/commercial/customer-orders/{o['order_id']}/confirm",
            {},
            **if_match(o["row_version"]),
        ),
        "/commercial/customer-orders/{order_id}/confirm",
        "post",
    )


# ------------------------------------------------------------------------------------- identity masters
def test_customers_brands_numbers_search_duplicate_warning_and_412() -> None:
    t = Team()
    year = jalali_year_tehran(db_now())
    name = f"مشتري ساختگي يكتا {uuid.uuid4().hex[:6]} {f.SYN}"  # Arabic ي / ك: search normalises them
    c1 = ok(
        post(t.c["co"], "/identity/customers", {"display_name_fa": name}, **idem()),
        "/identity/customers",
        "post",
        201,
    )
    assert re.fullmatch(NUMBER_PATTERN, c1["customer_no"]) and c1["customer_no"].startswith(f"CU-{year}-")
    path = "/identity/customers"
    refused(
        post(t.c["co"], path, {"display_name_fa": name}, **idem()),
        path,
        "post",
        400,
        "VALIDATION_FAILED",
        "DUPLICATE_CUSTOMER_NAME",
    )
    c2 = ok(
        post(t.c["co"], path, {"display_name_fa": name, "acknowledge_possible_duplicate": True}, **idem()),
        path,
        "post",
        201,
    )
    assert int(c2["customer_no"].rsplit("-", 1)[1]) > int(c1["customer_no"].rsplit("-", 1)[1])
    found = ok(get(t.c["viewer"], path, {"q": name.replace("ي", "ی").replace("ك", "ک")[:20]}), path, "get")
    assert {x["customer_id"] for x in found["items"]} >= {c1["customer_id"], c2["customer_id"]}
    one = f"/identity/customers/{c1['customer_id']}"
    r = get(t.c["viewer"], one)
    got = ok(r, "/identity/customers/{customer_id}", "get")
    assert etag_version(r) == got["row_version"]
    pp = "/identity/customers/{customer_id}"
    upd = {"legal_name_fa": f"نام حقوقی ساختگی {f.SYN}", "reason": "synthetic update"}
    refused(
        patch(t.c["co"], one, upd, **if_match(got["row_version"] + 5)), pp, "patch", 412, "VERSION_CONFLICT"
    )
    upd_ok = ok(patch(t.c["co"], one, upd, **if_match(got["row_version"])), pp, "patch")
    assert upd_ok["legal_name_fa"] and upd_ok["row_version"] > got["row_version"]
    cleared = ok(
        patch(
            t.c["co"],
            one,
            {"legal_name_fa": None, "reason": "synthetic clear"},
            **if_match(upd_ok["row_version"]),
        ),
        pp,
        "patch",
    )
    assert cleared["legal_name_fa"] is None
    bp = "/identity/customers/{customer_id}/brands"
    b = ok(
        post(t.c["co"], f"{one}/brands", {"brand_name_fa": f"برند ساختگی {f.SYN}"}, **idem()), bp, "post", 201
    )
    assert ok(get(t.c["viewer"], f"{one}/brands"), bp, "get")["items"][0]["brand_id"] == b["brand_id"]
    b2 = ok(
        patch(
            t.c["co"],
            f"{one}/brands/{b['brand_id']}",
            {"status": "INACTIVE", "reason": "synthetic"},
            **if_match(b["row_version"]),
        ),
        "/identity/customers/{customer_id}/brands/{brand_id}",
        "patch",
    )
    assert b2["status"] == "INACTIVE"
    other = f.customer()
    refused(
        patch(
            t.c["co"],
            f"/identity/customers/{other.pk}/brands/{b['brand_id']}",
            {"status": "ACTIVE", "reason": "syn"},
            **if_match(b2["row_version"]),
        ),
        "/identity/customers/{customer_id}/brands/{brand_id}",
        "patch",
        404,
        "NOT_FOUND",
    )


def test_products_styles_revisions_collision_tracking_suggestions_and_classes() -> None:
    t = Team()
    ptype = f.product_type()
    cat = f.category(ptype, "07")
    classes = ok(
        get(t.c["viewer"], "/identity/product-classes", {"level_key": "product_type"}),
        "/identity/product-classes",
        "get",
    )
    assert str(ptype.pk) in {x["product_class_id"] for x in classes["items"]}
    pp = "/identity/products"
    prod = ok(
        post(
            t.c["pds"], pp, {"product_class_id": str(ptype.pk), "name_fa": f"محصول ساختگی {f.SYN}"}, **idem()
        ),
        pp,
        "post",
        201,
    )
    assert prod["product_no"] == "0001" and prod["uom"] == "PIECE"  # ID-01: four digits as text
    one = f"/identity/products/{prod['product_id']}"
    prod = ok(
        patch(t.c["pds"], one, {"status": "ACTIVE", "reason": "synthetic"}, **if_match(prod["row_version"])),
        "/identity/products/{product_id}",
        "patch",
    )
    assert ok(get(t.c["viewer"], one), "/identity/products/{product_id}", "get")["status"] == "ACTIVE"
    assert (
        ok(get(t.c["viewer"], pp, {"product_class_id": str(ptype.pk)}), pp, "get")["items"][0]["product_id"]
        == prod["product_id"]
    )
    sp = "/identity/products/{product_id}/styles"
    st = ok(
        post(
            t.c["pds"],
            f"{one}/styles",
            {
                "category_id": str(cat.pk),
                "name_fa": f"استایل ساختگی {f.SYN}",
                "initial_attributes": {"colour_fa": f"رنگ ساختگی {f.SYN}"},
            },
            **idem(),
        ),
        sp,
        "post",
        201,
    )
    assert st["style_no"] == "0001" and st["category_id"] == str(cat.pk) and st["current_revision_id"] is None
    # REV-0232 through the API: count + 1 taken (legacy gap) -> the first free number after it, never refused
    from platform_core.product_identity.models import Product

    f.style(Product.objects.get(pk=prod["product_id"]), cat, "0003")
    st2 = ok(
        post(
            t.c["pds"],
            f"{one}/styles",
            {"category_id": str(cat.pk), "name_fa": f"استایل دوم {f.SYN}"},
            **idem(),
        ),
        sp,
        "post",
        201,
    )
    assert st2["style_no"] == "0004"
    assert len(ok(get(t.c["viewer"], f"{one}/styles"), sp, "get")["items"]) == 3
    s1 = f"/identity/styles/{st['style_id']}"
    revs = ok(get(t.c["viewer"], f"{s1}/revisions"), "/identity/styles/{style_id}/revisions", "get")["items"]
    assert len(revs) == 1 and revs[0]["status"] == "DRAFT"
    act = f"{s1}/revisions/{revs[0]['style_revision_id']}/activate"
    ap = "/identity/styles/{style_id}/revisions/{style_revision_id}/activate"
    r1 = ok(post(t.c["pds"], act, {"reason": "synthetic"}, **if_match(revs[0]["row_version"])), ap, "post")
    assert r1["status"] == "ACTIVE"
    refused(
        post(
            t.c["pds"],
            f"/identity/styles/{st2['style_id']}/revisions/{revs[0]['style_revision_id']}/activate",
            {"reason": "synthetic"},
            **if_match(r1["row_version"]),
        ),
        ap,
        "post",
        404,
        "NOT_FOUND",
    )
    r2 = ok(
        post(
            t.c["pds"],
            f"{s1}/revisions",
            {"attributes": {"main_material_fa": f"چرم ساختگی {f.SYN}"}, "reason": "synthetic"},
            **idem(),
        ),
        "/identity/styles/{style_id}/revisions",
        "post",
        201,
    )
    assert r2["revision_no"] == 2
    got = ok(get(t.c["viewer"], s1), "/identity/styles/{style_id}", "get")
    assert got["current_revision_id"] == r1["style_revision_id"]
    got = ok(
        patch(t.c["pds"], s1, {"status": "ACTIVE", "reason": "synthetic"}, **if_match(got["row_version"])),
        "/identity/styles/{style_id}",
        "patch",
    )
    track = ok(get(t.c["viewer"], f"{s1}/tracking"), "/identity/styles/{style_id}/tracking", "get")
    assert (
        track["counts"] == {"serials_total": 0, "serials_active": 0, "orders_total": 0}
        and track["serials"] == []
    )
    sug = ok(
        get(
            t.c["viewer"],
            "/identity/style-suggestions",
            {"q": "استایل ساختگی", "product_id": prod["product_id"]},
        ),
        "/identity/style-suggestions",
        "get",
    )
    assert sug["items"][0]["reasons"][0] == "SAME_PRODUCT"
    refused(
        get(t.c["viewer"], "/identity/style-suggestions"),
        "/identity/style-suggestions",
        "get",
        400,
        "VALIDATION_FAILED",
    )


# ------------------------------------------------------------------------------- codes and code rules
def _golden(t_code: str, n: int = 20) -> list[dict[str, Any]]:
    return [
        {
            "inputs": {
                "type_code": t_code,
                "category_code": "07",
                "product_no": f"{9000 + i:04d}",
                "style_no": "0001",
            },
            "expected_code": "02" + t_code + "07" + f"{9000 + i:04d}" + "0001",
            "source_sheet": "SyntheticSheet",
            "source_cell_ref": f"S{i}",
        }
        for i in range(n)
    ]


def test_code_rule_lifecycle_preview_validate_issue_and_registry() -> None:
    t = Team()
    owner = holder("owner_admin")
    s, _rev = _chain()
    seg = s.product.product_type.segment_value
    rp = "/identity/code-rule-revisions"
    rule = ok(
        post(
            t.c["pds"],
            rp,
            {"product_type_codes": [seg], "source_workbook_sha256": SHA, "reason": "synthetic"},
            **idem(),
        ),
        rp,
        "post",
        201,
    )
    one = f"{rp}/{rule['rule_revision_id']}"
    added = ok(
        post(t.c["pds"], f"{one}/golden-cases", {"cases": _golden(seg)}, **idem()),
        "/identity/code-rule-revisions/{rule_revision_id}/golden-cases",
        "post",
        201,
    )
    assert added["added"] == 20 and seg not in json.dumps(added["revision"]["rule_spec"])
    rule = ok(get(t.c["po"], one), "/identity/code-rule-revisions/{rule_revision_id}", "get")
    assert rule == added["revision"]
    sub = ok(
        post(t.c["pds"], f"{one}/submit-review", {"reason": "synthetic"}, **if_match(rule["row_version"])),
        "/identity/code-rule-revisions/{rule_revision_id}/submit-review",
        "post",
    )
    assert sub["status"] == "IN_REVIEW" and sub["golden_case_count"] == 20
    apath = "/identity/code-rule-revisions/{rule_revision_id}/approve"
    maker_approver = session_client(t.pds)
    refused(
        post(
            maker_approver,
            f"{one}/approve",
            {"resource_revision": sub["revision_no"], "note": "x"},
            **if_match(sub["row_version"]),
        ),
        apath,
        "post",
        403,
        "ACCESS_DENIED",
    )
    stale_mfa = session_client(t.cra, mfa=False)
    refused(
        post(
            stale_mfa,
            f"{one}/approve",
            {"resource_revision": sub["revision_no"], "note": "x"},
            **if_match(sub["row_version"]),
        ),
        apath,
        "post",
        401,
        "MFA_REQUIRED",
    )
    appr = ok(
        post(
            t.c["cra"],
            f"{one}/approve",
            {"resource_revision": sub["revision_no"], "note": "synthetic"},
            **if_match(sub["row_version"]),
        ),
        apath,
        "post",
    )
    act = ok(
        post(
            session_client(owner), f"{one}/activate", {"reason": "synthetic"}, **if_match(appr["row_version"])
        ),
        "/identity/code-rule-revisions/{rule_revision_id}/activate",
        "post",
    )
    assert act["status"] == "ACTIVE"
    listed = ok(get(t.c["po"], rp, {"status": "ACTIVE"}), rp, "get")
    assert [x["rule_revision_id"] for x in listed["items"]] == [act["rule_revision_id"]]
    # reject another revision (different approver than maker)
    other = ok(
        post(
            t.c["pds"],
            rp,
            {"product_type_codes": [seg], "source_workbook_sha256": SHA, "reason": "synthetic"},
            **idem(),
        ),
        rp,
        "post",
        201,
    )
    o1 = f"{rp}/{other['rule_revision_id']}"
    other = ok(
        post(t.c["pds"], f"{o1}/golden-cases", {"cases": _golden(seg)}, **idem()),
        "/identity/code-rule-revisions/{rule_revision_id}/golden-cases",
        "post",
        201,
    )["revision"]
    other = ok(
        post(t.c["pds"], f"{o1}/submit-review", {"reason": "synthetic"}, **if_match(other["row_version"])),
        "/identity/code-rule-revisions/{rule_revision_id}/submit-review",
        "post",
    )
    rej = ok(
        post(t.c["cra"], f"{o1}/reject", {"reason": "synthetic rejection"}, **if_match(other["row_version"])),
        "/identity/code-rule-revisions/{rule_revision_id}/reject",
        "post",
    )
    assert rej["status"] == "REJECTED"
    # preview / validate (side-effect free, no Idempotency-Key) and issue (fresh MFA)
    pv = "/identity/product-codes/preview"
    prev = ok(post(t.c["co"], pv, {"style_id": str(s.pk)}), pv, "post")
    assert (
        prev["code"] == f.code_for(s)
        and prev["issued"] is False
        and prev["rule_revision_id"] == act["rule_revision_id"]
    )
    new = ok(
        post(
            t.c["co"],
            pv,
            {"product_class_id": str(s.product.product_type_id), "category_id": str(s.category_id)},
        ),
        pv,
        "post",
    )
    assert new["new_product"] is True and new["segments"][3] == {"level_key": "style_no", "value": "0001"}
    refused(
        post(t.c["co"], pv, {"style_id": str(s.pk), "category_id": str(s.category_id)}),
        pv,
        "post",
        400,
        "VALIDATION_FAILED",
    )
    cp = "/identity/product-codes"
    issued = ok(
        post(t.c["pds"], cp, {"style_id": str(s.pk), "rule_revision_id": act["rule_revision_id"]}, **idem()),
        cp,
        "post",
        201,
    )
    assert (issued["code"], issued["status"], issued["erp_status"]) == (
        prev["code"],
        "RESERVED",
        "ERP_PENDING",
    )
    assert isinstance(issued["code"], str) and len(issued["code"]) == 14  # ID-01: Code14 text
    refused(
        post(t.c["pds"], cp, {"style_id": str(s.pk)}, **idem()),
        cp,
        "post",
        409,
        "STATE_TRANSITION_NOT_ALLOWED",
        "CODE_ALREADY_ISSUED",
    )
    vp = "/identity/product-codes/validate"
    val = ok(post(t.c["co"], vp, {"code": issued["code"], "code_namespace": "product_code"}), vp, "post")
    assert (
        val["format_valid"]
        and val["segments_checked"]
        and val["registry_entry"]["product_code_id"] == issued["product_code_id"]
    )
    assert val["reasons"] == []
    bad = ok(
        post(t.c["co"], vp, {"code": " ۰۲" + issued["code"][3:], "code_namespace": "product_code"}),
        vp,
        "post",
    )
    assert {"SURROUNDING_WHITESPACE", "NON_ASCII_DIGIT"} <= set(bad["reasons"]) and not bad["format_valid"]
    legacy = ok(
        post(t.c["co"], vp, {"code": issued["code"][:10] + "0000", "code_namespace": "product_code"}),
        vp,
        "post",
    )
    assert legacy["reasons"] == ["LEGACY_ONLY_STYLE_0000", "NOT_IN_REGISTRY"]
    assert (
        ok(
            get(t.c["co"], f"{cp}/{issued['product_code_id']}"),
            "/identity/product-codes/{product_code_id}",
            "get",
        )["code"]
        == issued["code"]
    )
    assert ok(get(t.c["co"], cp, {"style_id": str(s.pk)}), cp, "get")["items"][0]["code"] == issued["code"]
    assert not AuditEvent.objects.filter(action__startswith="identity.product_code.validate").exists()


# ------------------------------------------------------------------------------------- orders and serials
def test_order_lifecycle_representative_masking_serials_and_versions() -> None:
    t = Team()
    year = jalali_year_tehran(db_now())
    o = _draft(t, lines=2)
    assert (
        o["order_no"].startswith(f"SO-{year}-") and o["customer_representative_name"] == "[REDACTED]"
    )  # write response
    one = f"/commercial/customer-orders/{o['order_id']}"
    op = "/commercial/customer-orders/{order_id}"
    # DEC-058: unmasked read audited, management_viewer masked and not audited
    before = AuditEvent.objects.filter(action="commercial.order.representative_read").count()
    assert ok(get(t.c["co"], one), op, "get")["customer_representative_name"] == SYN_REP
    assert ok(get(t.c["viewer"], one), op, "get")["customer_representative_name"] == "[REDACTED]"
    assert AuditEvent.objects.filter(action="commercial.order.representative_read").count() == before + 1
    lines = ok(get(t.c["co"], one), op, "get")["lines"]
    o = ok(
        patch(
            t.c["co"],
            one,
            {"program_ref": "SYN-PRG-1", "customer_representative_name": None},
            **if_match(o["row_version"]),
        ),
        op,
        "patch",
    )
    assert o["customer_representative_name"] is None
    lp = "/commercial/customer-orders/{order_id}/lines/{line_id}"
    o = ok(
        patch(t.c["co"], f"{one}/lines/{lines[0]['line_id']}", {"quantity": 7}, **if_match(o["row_version"])),
        lp,
        "patch",
    )
    o = ok(
        post(
            t.c["co"],
            f"{one}/lines/{lines[1]['line_id']}/remove",
            {"reason": "synthetic"},
            **if_match(o["row_version"]),
        ),
        "/commercial/customer-orders/{order_id}/lines/{line_id}/remove",
        "post",
    )
    assert [ln["status"] for ln in o["lines"]] == ["OPEN", "REMOVED"] and o["lines"][0]["quantity"] == 7
    vpath = "/commercial/customer-orders/{order_id}/validate"
    o = ok(post(t.c["co"], f"{one}/validate", {}, **if_match(o["row_version"])), vpath, "post")
    o = ok(
        post(t.c["co"], f"{one}/reopen", {"reason": "synthetic"}, **if_match(o["row_version"])),
        "/commercial/customer-orders/{order_id}/reopen",
        "post",
    )
    o = ok(post(t.c["co"], f"{one}/validate", {}, **if_match(o["row_version"])), vpath, "post")
    cpath = "/commercial/customer-orders/{order_id}/confirm"
    refused(
        post(t.c["co"], f"{one}/confirm", {}, **if_match(o["row_version"])),
        cpath,
        "post",
        403,
        "ACCESS_DENIED",
    )
    refused(
        post(session_client(t.po, mfa=False), f"{one}/confirm", {}, **if_match(o["row_version"])),
        cpath,
        "post",
        401,
        "MFA_REQUIRED",
    )
    first = SerialCounter.objects.get(namespace_key="factory_serial").next_value
    conf = ok(
        post(t.c["po"], f"{one}/confirm", {"note": "synthetic"}, **if_match(o["row_version"])), cpath, "post"
    )
    live = [ln for ln in conf["lines"] if ln["status"] == "CONFIRMED"]
    assert conf["status"] == "CONFIRMED" and conf["current_version"] == 1 and len(live) == 1  # ID-02 / ID-03
    assert live[0]["serial_number"] == str(first) and re.fullmatch(r"[1-9][0-9]*", live[0]["serial_number"])
    rel = ok(
        post(t.c["po"], f"{one}/release-to-plan", {}, **if_match(conf["row_version"])),
        "/commercial/customer-orders/{order_id}/release-to-plan",
        "post",
    )
    assert rel["status"] == "RELEASED_TO_PLAN"
    vers = ok(
        get(t.c["viewer"], f"{one}/versions"), "/commercial/customer-orders/{order_id}/versions", "get"
    )["items"]
    assert [v["version"] for v in vers] == [1]
    v1 = ok(
        get(t.c["viewer"], f"{one}/versions/1"),
        "/commercial/customer-orders/{order_id}/versions/{order_version}",
        "get",
    )
    assert "customer_representative_name" not in json.dumps(v1["image"])
    refused(
        get(t.c["viewer"], f"{one}/versions/9"),
        "/commercial/customer-orders/{order_id}/versions/{order_version}",
        "get",
        404,
        "NOT_FOUND",
    )
    listed = ok(
        get(t.c["viewer"], "/commercial/customer-orders", {"status": "RELEASED_TO_PLAN"}),
        "/commercial/customer-orders",
        "get",
    )
    assert o["order_id"] in {x["order_id"] for x in listed["items"]}
    assert "customer_representative_name" not in json.dumps(listed)
    sid = live[0]["serial_id"]
    sp = f"/identity/serials/{sid}"
    ser = ok(get(t.c["viewer"], sp), "/identity/serials/{serial_id}", "get")
    assert (ser["order_line_id"], ser["current_snapshot_version"]) == (live[0]["line_id"], 1)
    assert (
        ok(get(t.c["viewer"], "/identity/serials", {"order_id": o["order_id"]}), "/identity/serials", "get")[
            "items"
        ][0]["serial_id"]
        == sid
    )
    assert (
        ok(get(t.c["viewer"], "/identity/serials", {"q": str(first)}), "/identity/serials", "get")["items"][
            0
        ]["serial_id"]
        == sid
    )
    snaps = ok(get(t.c["viewer"], f"{sp}/snapshots"), "/identity/serials/{serial_id}/snapshots", "get")[
        "items"
    ]
    assert [s["version"] for s in snaps] == [1] and SYN_REP not in json.dumps(snaps)
    trk = ok(get(t.c["viewer"], f"{sp}/tracking"), "/identity/serials/{serial_id}/tracking", "get")
    assert {"ORDER_CONFIRMED", "SERIAL_ALLOCATED", "ORDER_RELEASED_TO_PLAN"} <= {
        e["kind"] for e in trk["events"]
    }
    style_track = ok(
        get(t.c["viewer"], f"/identity/styles/{live[0]['style_id']}/tracking"),
        "/identity/styles/{style_id}/tracking",
        "get",
    )
    assert style_track["counts"]["serials_total"] == 1 and style_track["serials"][0]["serial_id"] == sid
    # a stand-alone allocation does not exist (DEC-006 L-A)
    refused(
        post(
            t.c["po"],
            "/identity/serials",
            {"order_line_id": live[0]["line_id"], "order_line_row_version": 1},
            **idem(),
        ),
        "/identity/serials",
        "post",
        409,
        "STATE_TRANSITION_NOT_ALLOWED",
        "SERIAL_ALLOCATED_AT_CONFIRM",
    )
    # cancel an unconfirmed order
    d = _draft(t)
    can = ok(
        post(
            t.c["co"],
            f"/commercial/customer-orders/{d['order_id']}/cancel",
            {"reason": "synthetic"},
            **if_match(d["row_version"]),
        ),
        "/commercial/customer-orders/{order_id}/cancel",
        "post",
    )
    assert can["status"] == "CANCELLED"


def test_confirmer_is_never_the_creator() -> None:
    t = Team()
    both = holder("commercial_officer", "planning_officer")
    c = session_client(both)
    cust = f.customer()
    s, _r = _chain()
    o = ok(
        post(
            c,
            "/commercial/customer-orders",
            {"customer_id": str(cust.pk), "order_type": "sampling", "order_date": "2030-01-10"},
            **idem(),
        ),
        "/commercial/customer-orders",
        "post",
        201,
    )
    o = ok(
        post(
            c,
            f"/commercial/customer-orders/{o['order_id']}/lines",
            {"style_id": str(s.pk), "quantity": 1},
            **if_match(o["row_version"]),
        ),
        "/commercial/customer-orders/{order_id}/lines",
        "post",
        201,
    )
    o = ok(
        post(c, f"/commercial/customer-orders/{o['order_id']}/validate", {}, **if_match(o["row_version"])),
        "/commercial/customer-orders/{order_id}/validate",
        "post",
    )
    refused(
        post(c, f"/commercial/customer-orders/{o['order_id']}/confirm", {}, **if_match(o["row_version"])),
        "/commercial/customer-orders/{order_id}/confirm",
        "post",
        403,
        "SELF_APPROVAL_FORBIDDEN",
        "CONFIRMER_IS_CREATOR",
    )
    assert (
        ok(
            post(
                t.c["po"],
                f"/commercial/customer-orders/{o['order_id']}/confirm",
                {},
                **if_match(o["row_version"]),
            ),
            "/commercial/customer-orders/{order_id}/confirm",
            "post",
        )["status"]
        == "CONFIRMED"
    )


# ------------------------------------------------------------------------------------- change requests
def _cr(
    t: Team,
    o: dict[str, Any],
    kind: str,
    items: list[Any] | None = None,
    *,
    submit: bool = True,
    who: str = "co",
) -> dict[str, Any]:
    cur = ok(
        get(t.c["co"], f"/commercial/customer-orders/{o['order_id']}"),
        "/commercial/customer-orders/{order_id}",
        "get",
    )
    return ok(
        post(
            t.c[who],
            "/commercial/change-requests",
            {
                "order_id": o["order_id"],
                "order_row_version": cur["row_version"],
                "kind": kind,
                "items": items or [],
                "reason": "synthetic change",
                "submit": submit,
            },
            **idem(),
        ),
        "/commercial/change-requests",
        "post",
        201,
    )


def _act(
    t: Team, who: str, cr: dict[str, Any], action: str, data: dict[str, Any] | None = None, status: int = 200
) -> dict[str, Any]:
    path = "/commercial/change-requests/{change_request_id}/" + action
    r = post(
        t.c[who],
        f"/commercial/change-requests/{cr['change_request_id']}/{action}",
        data or {},
        **if_match(cr["row_version"]),
    )
    return ok(r, path, "post", status)


def test_change_requests_due_date_planning_approve_and_reject_add_line_and_withdraw() -> None:
    t = Team()
    o = _confirmed(t)
    cp = "/commercial/change-requests/{change_request_id}"
    due = [{"line_id": None, "requested_due_date": "2030-05-01"}]
    cr = _cr(t, o, "DUE_DATE_CHANGE", due)
    assert re.fullmatch(NUMBER_PATTERN, cr["request_no"]) and cr["planning_required"] is True
    imp = ok(
        get(t.c["viewer"], f"/commercial/change-requests/{cr['change_request_id']}/impact"),
        cp + "/impact",
        "get",
    )
    assert imp["serials_affected"] and imp["unavailable_sections"]
    refused(
        post(
            session_client(t.cm, mfa=False),
            f"/commercial/change-requests/{cr['change_request_id']}/decide",
            {"decision": "APPROVE"},
            **if_match(cr["row_version"]),
        ),
        cp + "/decide",
        "post",
        401,
        "MFA_REQUIRED",
    )
    refused(
        post(
            t.c["cm"],
            f"/commercial/change-requests/{cr['change_request_id']}/planning-decision",
            {"decision": "APPROVE"},
            **if_match(cr["row_version"]),
        ),
        cp + "/planning-decision",
        "post",
        403,
        "ACCESS_DENIED",
    )
    cr = _act(t, "cm", cr, "decide", {"decision": "APPROVE", "note": "synthetic"})
    refused(
        post(
            t.c["po"],
            f"/commercial/change-requests/{cr['change_request_id']}/apply",
            {},
            **if_match(cr["row_version"]),
        ),
        cp + "/apply",
        "post",
        409,
        "STATE_TRANSITION_NOT_ALLOWED",
        "PLANNING_APPROVAL_REQUIRED",
    )
    cr = _act(t, "po2", cr, "planning-decision", {"decision": "APPROVE"})
    assert cr["planning_approved_by"] == str(t.po2.pk)
    cr = _act(t, "po", cr, "apply")
    assert (cr["status"], cr["applied_version"]) == ("APPLIED", 2)
    order = ok(
        get(t.c["co"], f"/commercial/customer-orders/{o['order_id']}"),
        "/commercial/customer-orders/{order_id}",
        "get",
    )
    assert order["requested_due_date"] == "2030-05-01" and order["current_version"] == 2
    sid = order["lines"][0]["serial_id"]
    assert SerialSnapshot.objects.filter(serial_id=sid).count() == 2  # next snapshot, same serial
    # planning rejects (reason required): REJECTED, the due date stays (DEC-059 amendment 2026-11-14)
    cr2 = _cr(t, o, "DUE_DATE_CHANGE", [{"line_id": None, "requested_due_date": "2030-06-01"}])
    refused(
        post(
            t.c["po2"],
            f"/commercial/change-requests/{cr2['change_request_id']}/planning-decision",
            {"decision": "REJECT"},
            **if_match(cr2["row_version"]),
        ),
        cp + "/planning-decision",
        "post",
        400,
        "VALIDATION_FAILED",
        "REQUIRED",
    )
    cr2 = _act(t, "po2", cr2, "planning-decision", {"decision": "REJECT", "note": "synthetic: no capacity"})
    assert (cr2["status"], cr2["planning_rejected_by"]) == ("REJECTED", str(t.po2.pk))
    order = ok(
        get(t.c["co"], f"/commercial/customer-orders/{o['order_id']}"),
        "/commercial/customer-orders/{order_id}",
        "get",
    )
    assert order["requested_due_date"] == "2030-05-01"
    # ADD_LINE (ID-03): a new line with a new serial; a DRAFT request submitted and a request withdrawn
    s, _r = _chain()
    add = _cr(t, o, "ADD_LINE", [{"style_id": str(s.pk), "quantity": 3}], submit=False)
    assert add["status"] == "DRAFT"
    add = _act(t, "co", add, "submit")
    add = _act(t, "cm2", add, "decide", {"decision": "APPROVE"})
    add = _act(t, "po", add, "apply")
    order = ok(
        get(t.c["co"], f"/commercial/customer-orders/{o['order_id']}"),
        "/commercial/customer-orders/{order_id}",
        "get",
    )
    serials = [ln["serial_id"] for ln in order["lines"] if ln["status"] == "CONFIRMED"]
    assert len(serials) == len(set(serials)) == 2
    hold = _cr(t, o, "HOLD")
    hold = _act(t, "co", hold, "withdraw", {"reason": "synthetic"})
    assert hold["status"] == "WITHDRAWN"
    listed = ok(
        get(t.c["viewer"], "/commercial/change-requests", {"order_id": o["order_id"]}),
        "/commercial/change-requests",
        "get",
    )
    assert len(listed["items"]) == 4
    by_serial = ok(
        get(t.c["viewer"], "/commercial/change-requests", {"serial_id": sid, "kind": "DUE_DATE_CHANGE"}),
        "/commercial/change-requests",
        "get",
    )
    assert len(by_serial["items"]) == 2
    assert (
        ok(get(t.c["viewer"], f"/commercial/change-requests/{cr['change_request_id']}"), cp, "get")["status"]
        == "APPLIED"
    )
    refused(
        post(
            t.c["cm"],
            f"/commercial/change-requests/{cr2['change_request_id']}/decide",
            {"decision": "REJECT", "note": "syn"},
            **if_match(cr2["row_version"]),
        ),
        cp + "/decide",
        "post",
        409,
        "STATE_TRANSITION_NOT_ALLOWED",
    )


# ------------------------------------------------------------------------- external refs and history
def test_external_refs_and_historical_records() -> None:
    t = Team()
    cust = f.customer()
    rp = "/identity/external-refs"
    data = {
        "target_type": "customer",
        "target_id": str(cust.pk),
        "system": "RAHKARAN",
        "namespace": "contract_no",
        "value": "SYN-000123",
        "reason": "synthetic",
    }
    ref = ok(post(t.c["co"], rp, data, **idem()), rp, "post", 201)
    assert ref["value"] == "SYN-000123"  # raw text, never parsed
    refused(
        post(t.c["co"], rp, data, **idem()),
        rp,
        "post",
        409,
        "STATE_TRANSITION_NOT_ALLOWED",
        "EXTERNAL_REF_EXISTS",
    )
    refused(
        post(t.c["co"], rp, {**data, "target_id": str(uuid.uuid4())}, **idem()), rp, "post", 404, "NOT_FOUND"
    )
    refused(
        post(t.c["co"], rp, {**data, "namespace": "syn_unknown_type"}, **idem()),
        rp,
        "post",
        400,
        "VALIDATION_FAILED",
    )
    assert (
        ok(get(t.c["pds"], rp, {"target_id": str(cust.pk), "value": "SYN-000123"}), rp, "get")["items"][0][
            "external_ref_id"
        ]
        == ref["external_ref_id"]
    )
    end = ok(
        post(
            t.c["pds"],
            f"{rp}/{ref['external_ref_id']}/end",
            {"reason": "synthetic"},
            **if_match(ref["row_version"]),
        ),
        "/identity/external-refs/{external_ref_id}/end",
        "post",
    )
    assert end["valid_to"] is not None
    refused(
        post(
            t.c["pds"],
            f"{rp}/{ref['external_ref_id']}/end",
            {"reason": "synthetic"},
            **if_match(end["row_version"]),
        ),
        "/identity/external-refs/{external_ref_id}/end",
        "post",
        409,
        "STATE_TRANSITION_NOT_ALLOWED",
    )
    from platform_core.product_identity.models import HistoricalOrderRecord

    batch, row = f.staging()
    HistoricalOrderRecord.objects.create(
        provenance_kind="LEG",
        import_batch=batch,
        staging_row=row,
        code_flag="ABSENT",
        legacy_serial_text="S-SYN-1",
    )
    hp = "/identity/historical-order-records"
    hist = ok(get(t.c["po"], hp, {"import_batch_id": str(batch.pk)}), hp, "get")
    assert [h["legacy_serial_ref"] for h in hist["items"]] == ["S-SYN-1"]
    refused(get(t.c["co"], hp), hp, "get", 403, "ACCESS_DENIED")  # DEC-057: planning / steward only


# ----------------------------------------------------------------------------- role matrix (DEC-057 v2.1)
ROLE_DENIED: list[tuple[str, str, str, dict[str, Any]]] = [
    ("commercial_officer", "post", "/identity/products", {}),
    ("product_data_steward", "post", "/identity/customers", {}),
    ("planning_officer", "post", "/commercial/customer-orders", {}),
    ("commercial_officer", "post", "/identity/product-codes", {}),
    ("commercial_manager", "post", "/identity/code-rule-revisions", {}),
    ("product_data_steward", "post", "/identity/code-rule-revisions/{id}/approve", {}),
    ("commercial_officer", "post", "/commercial/customer-orders/{id}/confirm", {}),
    ("commercial_manager", "post", "/commercial/customer-orders/{id}/release-to-plan", {}),
    ("commercial_manager", "post", "/commercial/change-requests", {}),
    ("commercial_officer", "post", "/commercial/change-requests/{id}/decide", {}),
    ("planning_officer", "post", "/commercial/change-requests/{id}/decide", {}),
    ("commercial_manager", "post", "/commercial/change-requests/{id}/planning-decision", {}),
    ("commercial_manager", "post", "/commercial/change-requests/{id}/apply", {}),
    ("owner_admin", "post", "/commercial/customer-orders", {}),
    ("owner_admin", "post", "/commercial/change-requests/{id}/apply", {}),
    ("code_rule_approver", "get", "/commercial/customer-orders/{id}/versions", {}),
]


@pytest.mark.parametrize(
    ("role", "method", "path", "_x"), ROLE_DENIED, ids=[f"{r}:{p}" for r, _m, p, _x in ROLE_DENIED]
)
def test_a_role_without_the_permission_is_refused(role: str, method: str, path: str, _x: Any) -> None:
    c = session_client(holder(role))
    url = API + path.replace("{id}", str(uuid.uuid4()))
    if method == "get":
        r = c.get(url)
        if role == "code_rule_approver":  # holds commercial.order.read (DEC-057): out of record -> 404
            assert r.status_code == 404
            return
    else:
        r = c.post(url, "{}", content_type="application/json", **if_match(1))
    assert r.status_code == 403 and code(r) == "ACCESS_DENIED", (role, path, r.status_code)


def test_a_non_global_assignment_sees_no_phase02_record() -> None:
    """DEC-057 answer 3: PHASE_02 grants are GLOBAL; an ORG_UNIT assignment reaches no unit-less record."""
    from .phase01_factories import org_unit

    unit = org_unit()
    u = person()
    give_role(u, "management_viewer", scope_kind="ORG_UNIT", scope_unit=unit)
    cust = f.customer()
    c = session_client(u)
    assert get(c, f"/identity/customers/{cust.pk}").status_code == 404
    assert body(get(c, "/identity/customers"))["items"] == []


# ------------------------------------------------------------------------------------ cross-cutting
def test_idempotent_replay_same_response_one_effect_and_key_reuse_422() -> None:
    t = Team()
    key = idem()
    data = {"display_name_fa": f"مشتری تکرار {uuid.uuid4().hex[:6]} {f.SYN}"}
    r1 = post(t.c["co"], "/identity/customers", data, **key)
    r2 = post(t.c["co"], "/identity/customers", data, **key)
    assert r1.status_code == r2.status_code == 201 and body(r1) == body(r2)
    assert r2["Idempotent-Replayed"] == "true" and r1["ETag"] == r2["ETag"]
    from platform_core.product_identity.models import Customer

    assert Customer.objects.filter(display_name_fa=data["display_name_fa"]).count() == 1
    r3 = post(t.c["co"], "/identity/customers", {**data, "legal_name_fa": "x"}, **key)
    refused(r3, "/identity/customers", "post", 422, "IDEMPOTENCY_KEY_REUSED")
    # ID-04: a replayed confirm returns the stored response; no second serial
    o = _validated(t)
    hdr = if_match(o["row_version"])
    url = f"/commercial/customer-orders/{o['order_id']}/confirm"
    c1, c2 = post(t.c["po"], url, {}, **hdr), post(t.c["po"], url, {}, **hdr)
    assert (
        c1.status_code == c2.status_code == 200
        and body(c1) == body(c2)
        and c2["Idempotent-Replayed"] == "true"
    )
    assert Serial.objects.filter(pk__in=[ln["serial_id"] for ln in body(c1)["lines"]]).count() == 1
    # a refusal is replayed too (deterministic 4xx), keeping the original request id in the body
    stale = {
        **idem(),
        "HTTP_IF_MATCH": f'"{o["row_version"]}"',
    }  # the order moved on: 412, stored and replayed
    p1, p2 = post(t.c["po"], url, {}, **stale), post(t.c["po"], url, {}, **stale)
    assert p1.status_code == p2.status_code == 412 and body(p1)["request_id"] == body(p2)["request_id"]


def test_pagination_request_id_and_validation_envelope() -> None:
    t = Team()
    for i in range(3):
        post(
            t.c["co"],
            "/identity/customers",
            {"display_name_fa": f"مشتری صفحه {i} {uuid.uuid4().hex[:6]} {f.SYN}"},
            **idem(),
        )
    p1 = ok(get(t.c["viewer"], "/identity/customers", {"page_size": 2}), "/identity/customers", "get")
    assert len(p1["items"]) == 2 and p1["page"]["next_cursor"]
    p2 = ok(
        get(t.c["viewer"], "/identity/customers", {"page_size": 2, "cursor": p1["page"]["next_cursor"]}),
        "/identity/customers",
        "get",
    )
    assert p2["items"] and {x["customer_id"] for x in p1["items"]}.isdisjoint(
        {x["customer_id"] for x in p2["items"]}
    )
    refused(
        get(t.c["viewer"], "/identity/customers", {"page_size": 101}),
        "/identity/customers",
        "get",
        400,
        "VALIDATION_FAILED",
    )
    refused(
        get(t.c["viewer"], "/identity/customers", {"cursor": "tampered"}),
        "/identity/customers",
        "get",
        400,
        "VALIDATION_FAILED",
    )
    rid = str(uuid.uuid4())
    r = get(t.c["viewer"], "/identity/customers", HTTP_X_REQUEST_ID=rid)
    assert r["X-Request-ID"] == rid
    r = post(
        t.c["co"], "/identity/customers", {"display_name_fa": "", "unknown": 1}, **idem(HTTP_X_REQUEST_ID=rid)
    )
    refused(r, "/identity/customers", "post", 400, "VALIDATION_FAILED")
    assert body(r)["request_id"] == rid and {e["code"] for e in body(r)["errors"]} == {
        "TOO_SHORT",
        "UNKNOWN_FIELD",
    }
    assert all(set(e) <= {"field", "code"} for e in body(r)["errors"])  # submitted values are never echoed


@override_settings(
    ALEEKHAN_THROTTLE_RATES={
        "anon": "1000/min",
        "principal": "3/min",
        "health": "1000/min",
        "login_ip": "1000/min",
        "login_user": "1000/min",
    }
)
def test_rate_limit_per_principal_on_phase02_endpoints() -> None:
    t = Team()
    for _ in range(3):
        assert get(t.c["viewer"], "/identity/customers").status_code == 200
    r = get(t.c["viewer"], "/identity/customers")
    refused(r, "/identity/customers", "get", 429, "RATE_LIMITED")
    assert int(r["Retry-After"]) >= 1
    assert get(t.c["co"], "/identity/customers").status_code == 200  # another principal, its own bucket


def test_concurrent_confirms_through_the_api_one_wins_no_duplicate_serial_race() -> None:
    """ID-02 / ID-04 through HTTP: N planners confirm the same order with the same If-Match at once."""
    t = Team()
    o = _validated(t, lines=3)
    n = 6
    clients = [session_client(holder("planning_officer")) for _ in range(n)]
    first = SerialCounter.objects.get(namespace_key="factory_serial").next_value

    def confirm(i: int) -> int:
        r = clients[i].post(
            f"{API}/commercial/customer-orders/{o['order_id']}/confirm",
            "{}",
            content_type="application/json",
            **if_match(o["row_version"]),
        )
        return int(r.status_code)

    statuses = run_concurrently(confirm, n)
    assert sorted(statuses).count(200) == 1, statuses
    assert all(s in (200, 409, 412) for s in statuses), statuses
    numbers = list(Serial.objects.filter(status="ALLOCATED").values_list("serial_value", flat=True))
    mine = sorted(v for v in numbers if v >= first)
    assert mine == [first, first + 1, first + 2]  # three lines, three serials, no gap, no duplicate
    assert SerialCounter.objects.get(namespace_key="factory_serial").next_value == first + 3


def test_concurrent_style_creation_through_the_api_distinct_numbers_race() -> None:
    """REV-0232 + race: concurrent creations on a product with a legacy gap get distinct, free numbers."""
    ptype = f.product_type()
    cat = f.category(ptype, "07")
    prod = f.product(ptype, "9001")
    f.style(prod, cat, "0002")  # count + 1 = 0002 is taken
    n = 5
    clients = [session_client(holder("product_data_steward")) for _ in range(n)]

    def create(i: int) -> str:
        r = clients[i].post(
            f"{API}/identity/products/{prod.pk}/styles",
            json.dumps({"category_id": str(cat.pk), "name_fa": f"س {i} {f.SYN}"}),
            content_type="application/json",
            **idem(),
        )
        assert r.status_code == 201, r.content
        return str(body(r)["style_no"])

    numbers = run_concurrently(create, n)
    assert sorted(numbers) == ["0003", "0004", "0005", "0006", "0007"], numbers
    assert ProductClass.objects.filter(pk=ptype.pk).exists()


def test_anonymous_and_non_session_callers_are_refused() -> None:
    c = Client(REMOTE_ADDR=INTERNAL_IP)
    r = c.get(f"{API}/identity/customers")
    refused(r, "/identity/customers", "get", 401, "AUTHENTICATION_REQUIRED")
