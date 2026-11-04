#!/usr/bin/env python3
"""Seed SYNTHETIC, clearly labelled rows for the backup/restore drill (ops/backup/drill.sh).

Refuses to run unless the connected database name starts with ``aleekhan_drill_`` and ``ALEEKHAN_ENV`` is
``dev`` or ``test`` - it can never write into a real database. Every row goes through the platform write
path (unit of work: audit + outbox; import batch -> staging -> validate; conflict queue), so the drill also
exercises triggers and constraints on restore.

Usage: python ops/backup/drill_seed.py [N]   (N = number of audit/outbox pairs and staging rows, default 200)
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aleekhan.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection  # noqa: E402

from platform_core.engine.context import Actor, RequestContext  # noqa: E402
from platform_core.engine.uow import unit_of_work  # noqa: E402
from platform_core.integration import conflicts as cf  # noqa: E402
from platform_core.integration import imports as im  # noqa: E402
from platform_core.integration.models import IntegrationSource  # noqa: E402

LABEL = "synthetic_drill"


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    name = str(connection.settings_dict.get("NAME") or "")
    if not name.startswith("aleekhan_drill_") or settings.ALEEKHAN_ENV not in {"dev", "test"}:
        print(
            "drill_seed: refused (database must be aleekhan_drill_* and ALEEKHAN_ENV dev/test)",
            file=sys.stderr,
        )
        return 2
    ctx = RequestContext(Actor.system(), request_id=uuid.uuid4())
    for i in range(n):
        with unit_of_work(ctx) as uow:
            uow.audit(
                action="platform.ops.drill_seed", resource_type="platform.synthetic", resource_id=f"d{i}"
            )
            uow.emit(
                event_type="platform.ops.drill_seeded",
                aggregate_type="platform.synthetic",
                aggregate_id=f"d{i}",
                aggregate_version=1,
                payload={"label": LABEL, "i": i},
            )
    source = IntegrationSource.objects.create(
        code=f"{LABEL}_{uuid.uuid4().hex[:8]}",
        name_fa="منبع ساختگی تمرین بازیابی",
        kind="EXCEL_FILE",
        policy_decision_id="DEC-016",
        staleness_threshold=timedelta(hours=24),
    )
    batch = im.receive_file(
        ctx,
        source_code=source.code,
        content=f"SYNTHETIC drill file {uuid.uuid4()}".encode(),
        original_name="drill.xlsx",
    ).batch
    rows = [
        im.StagingInput(i + 1, {"label": LABEL, "row": i, "code": f"{i:014d}"}, "DRILL") for i in range(n)
    ]
    im.stage_rows(ctx, batch.id, rows)
    im.validate_batch(ctx, batch.id)
    cf.raise_conflict(
        ctx, source_code=source.code, kind="synthetic_drill", key="k1", details={"label": LABEL}
    )
    print(f"drill_seed: seeded n={n} source={source.code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
