"""PHASE_02 / 02.7 performance evidence (marker ``perf``; run with ``pytest -m perf``). SYNTHETIC data only.

Same conventions as ``test_perf_phase01``: real PostgreSQL test database, in-process (Django test client or
engine calls; no proxy, no gunicorn), numbers are evidence of the machine that ran them
(``ALEEKHAN_MACHINE``), every budget is a TECHNICAL DEFAULT gross-regression guard (not an SLA; real targets
belong to the pilot environment). ``ALEEKHAN_PERF_OUT=<file>`` writes the numbers as JSON.

1. Order confirm with N lines (one transaction: N serials from the gapless counter, N snapshots, version
   image, audit + outbox).
2. Serial allocation throughput under concurrency: W planners confirm orders at the same time (separate DB
   connections); serials/s, and the numbers stay unique and gapless.
3. Planning import of a synthetic workbook of baseline-like size (Sorce 6 types / 111 categories, NOrder
   3917 rows: 2841 distinct valid codes, 634 disputed rows over 224 distinct values) - aggregates follow
   docs/discovery/PLANNING_EXTRACTION_SUMMARY.md and the 02.6 real-run counts, the values are synthetic.
4. List endpoints with pagination on that volume: product codes (~2.8k), 1000 customer orders, the conflict
   queue, the code-rule list (REV-0244: revisions with 2000 golden cases each - the list reads the stored
   summary; the old live computation is measured next to it).
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from django.test import override_settings

from platform_core.api.phase02 import serializers as S
from platform_core.commercial import orders
from platform_core.commercial.models import CustomerOrder
from platform_core.devtools import phase02_engine as e
from platform_core.devtools import phase02_factories as f
from platform_core.devtools.engine_fixtures import ensure_catalogue
from platform_core.devtools.engine_fixtures import network as set_network
from platform_core.integration.models import ConflictItem
from platform_core.product_identity import codes
from platform_core.product_identity import planning_import as pi
from platform_core.product_identity.models import CodeRuleRevision, ProductCode, Serial, SerialCounter

from .phase01_api import get, session_client, with_roles
from .test_perf_phase01 import RATES, _latency, _record
from .threads import run_concurrently

pytestmark = [pytest.mark.perf]
SYN = "ساختگی"

CONFIRM_LINES = 100
WORKERS = 8
ORDERS_PER_WORKER = 5
LINES_PER_ORDER = 5
LIST_ORDERS = 1000
LIST_ITERATIONS = 15
GOLDEN_REVISIONS = 4
GOLDEN_PER_REVISION = 2000
# TECHNICAL DEFAULT budgets (gross-regression guards, not SLAs); same 5 s list budget as PHASE_01 inboxes
CONFIRM_BUDGET_MS = 30000.0
SERIALS_MIN_PER_S = 5.0
IMPORT_BUDGET_S = 300.0
LIST_P95_BUDGET_MS = 5000.0
CODE_RULE_LIST_P95_BUDGET_MS = 1500.0


def _serial_values() -> list[int]:
    return sorted(Serial.objects.values_list("serial_value", flat=True))


# --------------------------------------------------------------------------------- 1. confirm N lines
@pytest.mark.django_db
def test_perf_order_confirm_with_many_lines() -> None:
    p = e.people()
    o = e.validated_order(p.co, lines=CONFIRM_LINES)
    first = SerialCounter.objects.get(namespace_key="factory_serial").next_value
    t0 = time.perf_counter()
    done = orders.confirm_order(p.po.caller, o.pk, expected_version=o.row_version)
    ms = (time.perf_counter() - t0) * 1000
    assert done.status == "CONFIRMED"
    assert _serial_values() == list(range(first, first + CONFIRM_LINES))
    _record(
        "order_confirm_lines",
        {"lines": CONFIRM_LINES, "confirm_ms": round(ms, 1), "budget_ms": CONFIRM_BUDGET_MS},
    )
    assert ms < CONFIRM_BUDGET_MS


# --------------------------------------------------------------------- 2. serial throughput, W writers
@pytest.fixture
def phase02_tx(audit_cleanup: None) -> None:
    ensure_catalogue()


@pytest.mark.django_db(transaction=True)
@pytest.mark.usefixtures("phase02_tx")
def test_perf_serial_allocation_throughput_under_concurrency() -> None:
    p = e.people()
    made = [
        [e.validated_order(p.co, lines=LINES_PER_ORDER) for _ in range(ORDERS_PER_WORKER)]
        for _ in range(WORKERS)
    ]
    planners = [e.holder("planning_officer") for _ in range(WORKERS)]
    first = SerialCounter.objects.get(namespace_key="factory_serial").next_value

    def work(i: int) -> int:
        for o in made[i]:
            orders.confirm_order(planners[i].caller, o.pk, expected_version=o.row_version)
        return len(made[i])

    t0 = time.perf_counter()
    results = run_concurrently(work, WORKERS, timeout=600)
    seconds = time.perf_counter() - t0
    assert all(r == ORDERS_PER_WORKER for r in results), results
    total = WORKERS * ORDERS_PER_WORKER * LINES_PER_ORDER
    values = _serial_values()
    assert values == list(range(first, first + total))  # unique, gapless (DEC-006 G-B)
    rate = total / seconds
    _record(
        "serial_allocation_concurrency",
        {
            "workers": WORKERS,
            "orders": WORKERS * ORDERS_PER_WORKER,
            "serials": total,
            "seconds": round(seconds, 2),
            "serials_per_s": round(rate, 1),
            "orders_per_s": round(WORKERS * ORDERS_PER_WORKER / seconds, 2),
            "gapless": True,
            "min_serials_per_s": SERIALS_MIN_PER_S,
        },
    )
    assert rate > SERIALS_MIN_PER_S


# ------------------------------------------------------------ 3. + 4. import volume, then the lists
TYPE_NAMES = ("کفش", "کیف", "کمربند", "جیبی", "اکسسوری", "ست")  # the DEC-058 generic unit words
TYPE_SEGS = ("91", "92", "93", "94", "95", "96")
CATEGORY_COLS = ("BE", "BF", "BG", "BH", "BI")  # categories for the first five types
CATEGORY_ROWS = 23  # 5 x 23 = 115 slots; 111 filled
DISTINCT_CODES = 2841
VALID_ROWS = 3283
DISPUTED_VALUES = 224
DISPUTED_ROWS = 634


def _category_code(row: int) -> str:
    return TYPE_SEGS[row - 3] if row < 9 else f"{61 + row - 9:02d}"  # rows 3..25: 91..96, then 61..77


def _baseline_like_workbook(path: Path) -> tuple[Path, int]:
    sorce: dict[str, Any] = {"E2": "Product type", "O2": "Code"}
    for i, col in enumerate(CATEGORY_COLS):
        sorce[f"{col}1"] = TYPE_NAMES[i]
    for i, name in enumerate(TYPE_NAMES):
        sorce[f"E{3 + i}"] = name
    categories = 0
    cats_of: dict[str, list[str]] = {}
    for row in range(3, 3 + CATEGORY_ROWS):
        sorce[f"O{row}"] = _category_code(row)
        for i, col in enumerate(CATEGORY_COLS):
            if categories >= 111:
                break
            sorce[f"{col}{row}"] = f"دسته {SYN} {i}-{row}"
            cats_of.setdefault(TYPE_SEGS[i], []).append(_category_code(row))
            categories += 1
    norder: dict[str, Any] = {"A1": "نوع", "FZ1": "کد"}
    codes_: list[tuple[str, str, str]] = []
    k = 0
    while len(codes_) < DISTINCT_CODES:
        t = TYPE_SEGS[k % 5]
        cat = cats_of[t][k % len(cats_of[t])]
        prod = f"{9000 + (k // 40) % 1000:04d}"
        style = f"{1 + k % 40:04d}"
        codes_.append((f"02{t}{cat}{prod}{style}", prod, style))
        k += 1
    rows: list[tuple[str, str, str] | str] = list(codes_)
    rows += [codes_[i % DISTINCT_CODES] for i in range(VALID_ROWS - DISTINCT_CODES)]  # repeated orders
    rows += [f"SYN-{i % DISPUTED_VALUES:03d}" for i in range(DISPUTED_ROWS)]  # disputed, 224 values
    for n, item in enumerate(rows, start=2):
        if isinstance(item, tuple):
            code, prod, style = item
            norder[f"C{n}"], norder[f"D{n}"], norder[f"FZ{n}"] = prod, style, code
        else:
            norder[f"FZ{n}"] = item
        norder[f"A{n}"] = TYPE_NAMES[0]
    from platform_core.devtools.planning_workbook import write_workbook

    write_workbook(path, {"Sorce": sorce, "NOrder": norder, "Codding": {"K1": "کد"}})
    return path, len(rows)


@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache")
@override_settings(ALEEKHAN_THROTTLE_RATES=RATES)
def test_perf_planning_import_and_paginated_lists(settings: Any, tmp_path: Path) -> None:
    set_network(settings)
    path, norder_rows = _baseline_like_workbook(tmp_path / "baseline-like-synthetic.xlsm")
    from platform_core.devtools.planning_workbook import sha

    t0 = time.perf_counter()
    report = pi.import_planning_workbook(
        path, expected_sha256=sha(path), layout=pi.Layout(codding_code_col="K")
    )
    import_s = time.perf_counter() - t0
    assert report.status == "APPLIED"
    registered = ProductCode.objects.count()
    disputed = ConflictItem.objects.filter(kind="legacy_code_disputed").count()
    assert registered == DISTINCT_CODES and disputed == DISPUTED_VALUES
    assert report.counts["legacy_rows_disputed"] == DISPUTED_ROWS  # REV-0261: every row is on an item
    _record(
        "planning_import_baseline_like",
        {
            "file_bytes": path.stat().st_size,
            "norder_rows": norder_rows,
            "categories_slots": 111,
            "codes_registered": registered,
            "disputed_items": disputed,
            "disputed_rows": report.counts["legacy_rows_disputed"],
            "import_seconds": round(import_s, 2),
            "budget_s": IMPORT_BUDGET_S,
        },
    )
    assert import_s < IMPORT_BUDGET_S

    # 1000 DRAFT orders over 50 synthetic customers (bulk: list cost, not create cost, is measured here)
    maker = with_roles("commercial_officer")
    customers = [f.customer() for _ in range(50)]
    CustomerOrder.objects.bulk_create(
        [
            CustomerOrder(
                order_no=f"SO-1300-{i:06d}",
                customer=customers[i % 50],
                order_type_id="series_production",
                order_date=date(2030, 1, 10),
                created_by=maker,
            )
            for i in range(LIST_ORDERS)
        ],
        batch_size=500,
    )
    reader = session_client(with_roles("owner_admin"))
    results: dict[str, Any] = {}
    volume = {
        "product_codes": registered,
        "customer_orders": LIST_ORDERS,
        "conflicts": ConflictItem.objects.count(),
        "customers": len(customers),
    }
    urls = {
        "product_codes": "/identity/product-codes",
        "customer_orders": "/commercial/customer-orders",
        "conflicts": "/integration/conflicts",
        "customers": "/identity/customers",
    }
    for name, url in urls.items():
        expected_first = min(100, volume[name])

        def page(u: str = url, n_first: int = expected_first) -> None:
            r = get(reader, u, {"page_size": 100})
            assert r.status_code == 200, (u, r.status_code, r.content[:200])
            assert len(json.loads(r.content)["items"]) == n_first

        def walk(u: str = url) -> int:  # follow the cursor up to 5 pages deep
            cursor, n = None, 0
            for _ in range(5):
                params: dict[str, Any] = {"page_size": 100, **({"cursor": cursor} if cursor else {})}
                data = json.loads(get(reader, u, params).content)
                n += len(data["items"])
                cursor = data["page"]["next_cursor"]
                if not cursor:
                    break
            return n

        results[name] = _latency(page, LIST_ITERATIONS)
        t0 = time.perf_counter()
        assert walk() == min(500, volume[name]), name
        results[name]["five_pages_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        assert results[name]["p95_ms"] < LIST_P95_BUDGET_MS, (name, results[name])
    _record(
        "paginated_lists",
        {
            "page_size": 100,
            "volume": volume,
            "results": results,
            "budget_p95_ms": LIST_P95_BUDGET_MS,
        },
    )


@pytest.mark.django_db
@pytest.mark.usefixtures("clear_cache")
@override_settings(ALEEKHAN_THROTTLE_RATES=RATES)
def test_perf_code_rule_list_reads_the_stored_golden_summary(settings: Any) -> None:
    """REV-0244: the list used to rebuild the code of every stored golden case for every row."""
    set_network(settings)
    from .test_phase02_planning_import import golden_cases

    maker = e.holder("product_data_steward")
    for _ in range(GOLDEN_REVISIONS):
        r = codes.create_rule_revision(
            maker.caller, product_type_codes=["91"], source_workbook_sha256="d" * 64
        )
        rows = [
            {
                "inputs": {k: c[k] for k in ("type_code", "category_code", "product_no", "style_no")},
                "expected_code": c["expected_code"],
                "source_sheet": c["source_sheet"],
                "source_cell_ref": c["source_cell_ref"],
            }
            for c in golden_cases(GOLDEN_PER_REVISION)
        ]
        codes.add_golden_cases(maker.caller, r.pk, cases=rows)
    revisions = list(CodeRuleRevision.objects.order_by("-revision_no"))
    assert all(isinstance(x.golden_summary, dict) for x in revisions)
    assert all((x.golden_summary or {}).get("total") == GOLDEN_PER_REVISION for x in revisions)

    def live() -> None:  # what the 02.4 list did per page
        for x in revisions:
            S.code_rule(x, live_summary=True)

    reader = session_client(with_roles("product_data_steward"))

    def listed() -> None:
        resp = get(reader, "/identity/code-rule-revisions", {"page_size": 25})
        assert resp.status_code == 200
        assert len(json.loads(resp.content)["items"]) == GOLDEN_REVISIONS

    one = f"/identity/code-rule-revisions/{revisions[0].pk}"
    stored_list = _latency(listed, LIST_ITERATIONS)
    live_cost = _latency(live, 3)
    single = _latency(lambda: get(reader, one), 3)
    _record(
        "code_rule_list_golden_summary",
        {
            "revisions": GOLDEN_REVISIONS,
            "golden_cases_per_revision": GOLDEN_PER_REVISION,
            "list_stored_summary": stored_list,
            "old_live_summary_for_the_same_page": live_cost,
            "single_get_live": single,
            "budget_list_p95_ms": CODE_RULE_LIST_P95_BUDGET_MS,
        },
    )
    assert stored_list["p95_ms"] < CODE_RULE_LIST_P95_BUDGET_MS
    assert stored_list["p50_ms"] < live_cost["p50_ms"]  # the store is cheaper than the old per-row rebuild
