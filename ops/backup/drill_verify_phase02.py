#!/usr/bin/env python3
"""Verify the PHASE_02 invariants of a (restored / rolled-forward) drill database (PHASE_02 / 02.7).

Read-only plain SELECTs over the connected database (libpq env, ``PGDATABASE``); refuses any database whose
name does not start with ``aleekhan_drill_`` / ``test_aleekhan_drill_``. Prints ONE JSON object (counts and
check results only - no value, no name, no number) and exits 1 if any check fails.

Checks (DEC-006 gapless counter, DEC-059 versions, the deferred commit-time guards of migration 0020):

* serial counter: the issued serial values are exactly ``start_value .. next_value - 1`` (no gap, no
  duplicate, nothing at or beyond ``next_value``) and all are >= ``legacy_max_exclusive``;
* every CONFIRMED / CANCELLED order line has a serial, and every serial belongs to exactly one line;
* every serial has its snapshot version 1, and snapshot versions are contiguous per serial;
* every order has one version row for each version 1 .. ``current_version`` (confirmed orders: >= 1);
* every APPLIED change request has the order version it created;
* ``platform_number_counter``: every issued year-format number (CU- customers, SO- orders, CR- change
  requests) has its (kind, Jalali year) counter row and ``last_value`` >= that number (a missing row fails);
* import batches: >= 1 APPLIED Planning batch with staging rows and legacy codes; the failed apply is still
  visible (a VALIDATED Planning batch with a ``platform.integration.batch.apply_failed`` audit row).

Usage: python ops/backup/drill_verify_phase02.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aleekhan.settings")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402

CHECKS: dict[str, str] = {
    "serials_gapless_from_start": """
        SELECT bool_and(ok) FROM (
          SELECT (SELECT count(*) FROM identity_serial s WHERE s.serial_counter_id = c.id)
                   = c.next_value - c.start_value
             AND (SELECT count(DISTINCT serial_value) FROM identity_serial s WHERE s.serial_counter_id = c.id)
                   = c.next_value - c.start_value
             AND coalesce((SELECT min(serial_value) FROM identity_serial s WHERE s.serial_counter_id = c.id),
                          c.start_value) = c.start_value
             AND coalesce((SELECT max(serial_value) FROM identity_serial s WHERE s.serial_counter_id = c.id),
                          c.next_value - 1) = c.next_value - 1
             AND c.start_value >= c.legacy_max_exclusive AS ok
          FROM identity_serial_counter c) x""",
    "confirmed_lines_have_a_serial": """
        SELECT NOT EXISTS (SELECT 1 FROM commercial_customer_order_line
                            WHERE status IN ('CONFIRMED', 'CANCELLED') AND serial_id IS NULL)""",
    "serial_belongs_to_one_line": """
        SELECT NOT EXISTS (SELECT s.id FROM identity_serial s
                             LEFT JOIN commercial_customer_order_line l ON l.serial_id = s.id
                            GROUP BY s.id HAVING count(l.id) <> 1)""",
    "serial_snapshots_contiguous_from_1": """
        SELECT NOT EXISTS (SELECT s.id FROM identity_serial s
                             LEFT JOIN identity_serial_snapshot n ON n.serial_id = s.id
                            GROUP BY s.id
                           HAVING count(n.id) = 0 OR min(n.version) <> 1 OR max(n.version) <> count(n.id))""",
    "order_versions_complete": """
        SELECT NOT EXISTS (SELECT o.id FROM commercial_customer_order o
                             LEFT JOIN commercial_customer_order_version v ON v.order_id = o.id
                            GROUP BY o.id, o.current_version
                           HAVING count(v.id) <> o.current_version
                               OR coalesce(max(v.version), 0) <> o.current_version)""",
    "applied_change_requests_have_their_version": """
        SELECT NOT EXISTS (SELECT 1 FROM commercial_order_change_request r
                            WHERE r.status = 'APPLIED' AND NOT EXISTS (
                                  SELECT 1 FROM commercial_customer_order_version v
                                   WHERE v.change_request_id = r.id))""",
    "number_counters_cover_issued_numbers": """
        SELECT NOT EXISTS (
          SELECT 1 FROM (
            SELECT 'CU' AS kind, customer_no AS no FROM identity_customer
            UNION ALL SELECT 'SO', order_no FROM commercial_customer_order
            UNION ALL SELECT 'CR', request_no FROM commercial_order_change_request) n
          LEFT JOIN platform_number_counter c
            ON c.kind = CASE n.kind WHEN 'CU' THEN 'customer' WHEN 'SO' THEN 'order' ELSE 'change_request' END
           AND c.jalali_year = split_part(n.no, '-', 2)::int
          WHERE n.no ~ '^(CU|SO|CR)-[0-9]{4}-[0-9]{6,}$'
            AND (c.kind IS NULL OR split_part(n.no, '-', 3)::bigint > c.last_value))""",
    "planning_batch_applied_with_staging_and_codes": """
        SELECT EXISTS (SELECT 1 FROM platform_import_batch b
                         JOIN platform_integration_source s ON s.id = b.source_id
                        WHERE s.code = 'planning_catalogue_xlsm' AND b.status = 'APPLIED'
                          AND EXISTS (SELECT 1 FROM platform_import_staging_row r
                                       WHERE r.batch_id = b.id)
                          AND EXISTS (SELECT 1 FROM identity_product_code p
                                       WHERE p.import_batch_id = b.id))""",
    "failed_apply_still_visible": """
        SELECT EXISTS (SELECT 1 FROM platform_import_batch b
                         JOIN platform_integration_source s ON s.id = b.source_id
                        WHERE s.code = 'planning_catalogue_xlsm' AND b.status = 'VALIDATED'
                          AND EXISTS (SELECT 1 FROM platform_audit_event a
                                       WHERE a.action = 'platform.integration.batch.apply_failed'
                                         AND a.resource_id = b.id::text))""",
}
COUNTS: dict[str, str] = {
    "serials": "SELECT count(*) FROM identity_serial",
    "serial_snapshots": "SELECT count(*) FROM identity_serial_snapshot",
    "serial_counter_issued": "SELECT coalesce(sum(next_value - start_value), 0) FROM identity_serial_counter",
    "orders": "SELECT count(*) FROM commercial_customer_order",
    "order_versions": "SELECT count(*) FROM commercial_customer_order_version",
    "change_requests_applied": (
        "SELECT count(*) FROM commercial_order_change_request WHERE status = 'APPLIED'"
    ),
    "number_counters": "SELECT count(*) FROM platform_number_counter",
    "import_batches": "SELECT count(*) FROM platform_import_batch",
    "staging_rows": "SELECT count(*) FROM platform_import_staging_row",
    "conflict_items": "SELECT count(*) FROM platform_conflict_item",
    "legacy_codes": "SELECT count(*) FROM identity_product_code WHERE provenance_kind = 'LEG'",
}


def main() -> int:
    name = str(connection.settings_dict.get("NAME") or "")
    if not name.startswith(("aleekhan_drill_", "test_aleekhan_drill_")):
        print("drill_verify_phase02: refused (database must be [test_]aleekhan_drill_*)", file=sys.stderr)
        return 2
    out: dict[str, Any] = {"counts": {}, "checks": {}}
    with connection.cursor() as cur:
        for key, sql in COUNTS.items():
            cur.execute(sql)
            out["counts"][key] = int(cur.fetchone()[0])
        for key, sql in CHECKS.items():
            cur.execute(sql)
            out["checks"][key] = bool(cur.fetchone()[0])
    out["counts_nonzero"] = all(v > 0 for v in out["counts"].values())
    out["status"] = "PASS" if all(out["checks"].values()) and out["counts_nonzero"] else "FAIL"
    print(json.dumps(out, sort_keys=True))
    return 0 if out["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
