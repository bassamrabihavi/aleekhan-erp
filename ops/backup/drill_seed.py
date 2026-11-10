#!/usr/bin/env python3
"""Seed SYNTHETIC, clearly labelled rows for the backup/restore drill (ops/backup/drill.sh).

Refuses to run unless the connected database name starts with ``aleekhan_drill_`` or
``test_aleekhan_drill_`` and ``ALEEKHAN_ENV`` is ``dev`` or ``test`` - it can never write
into a real database.
Every row of the PHASE_00 part goes through the platform write
path (unit of work: audit + outbox; import batch -> staging -> validate; conflict queue), so the drill also
exercises triggers and constraints on restore.

PHASE_01 / 01.7: also one labelled row set in the PHASE_01 tables (migrations 0007-0018): a synthetic user
with a credential (random password, never printed or stored anywhere else), org unit + position +
holder, an ``employee`` role assignment, a work task, an approval request, a document with a stored object
and a revision
(metadata only, no bytes), job runs of two housekeeping jobs (lifecycle + audit integrity run) and one outbox
event in the 0018 state DISCARDED - so the drill proves those tables, their triggers and the audit hash chain
survive dump and restore.

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
    allowed = name.startswith(("aleekhan_drill_", "test_aleekhan_drill_"))
    if not allowed or settings.ALEEKHAN_ENV not in {"dev", "test"}:
        print(
            "drill_seed: refused (database must be [test_]aleekhan_drill_* and ALEEKHAN_ENV dev/test)",
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
                # 01.6: uncatalogued types are refused; dev/test accept only the synthetic namespace
                event_type="platform.synthetic.drill_seeded",
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
    phase01 = seed_phase01()
    print(f"drill_seed: seeded n={n} source={source.code} phase01_rows={phase01}")
    return 0


def seed_phase01() -> int:
    """One labelled row set in the PHASE_01 tables (see the module docstring). Returns the rows written."""
    import hashlib
    import secrets

    from django.utils import timezone

    from platform_core.documents.models import Document, DocumentRevision, StoredObject
    from platform_core.identity.models import Credential, Role, RoleAssignment, User
    from platform_core.identity.passwords import hash_password
    from platform_core.jobs.service import run_job
    from platform_core.models import OutboxEvent
    from platform_core.org.models import OrgUnit, Position, PositionAssignment
    from platform_core.schema_common import SYNTHETIC_LABEL
    from platform_core.workflow.models import ApprovalRequest, WorkTask

    tag = uuid.uuid4().hex[:8]
    now = timezone.now()
    who = User.objects.create(
        username=f"syn.drill.{tag}",
        display_name=f"کاربر ساختگی تمرین ({SYNTHETIC_LABEL})",
        account_kind="PERSON",
        network_policy="ANY_WITH_MFA_OUTSIDE",
        provenance="SEED_SYNTHETIC",
    )
    Credential.objects.create(
        user=who,
        password_hash=hash_password(secrets.token_urlsafe(18) + "-Aa1!"),  # random, never printed
        set_at=now - timedelta(seconds=5),
        expires_at=now + timedelta(days=90),
    )
    unit = OrgUnit.objects.create(
        code=f"syn_drill_{tag}",
        name_fa=f"واحد ساختگی تمرین ({SYNTHETIC_LABEL})",
        unit_type_id="COMPANY",
        provenance="SEED_SYNTHETIC",
    )
    pos = Position.objects.create(
        unit=unit,
        code=f"syn_drill_pos_{tag}",
        title_fa=f"سمت ساختگی تمرین ({SYNTHETIC_LABEL})",
        provenance="SEED_SYNTHETIC",
    )
    PositionAssignment.objects.create(position=pos, user=who, kind="PRIMARY", reason=LABEL)
    RoleAssignment.objects.create(
        user=who,
        role=Role.objects.get(code="employee"),
        scope_kind="GLOBAL",
        status="ACTIVE",
        granted_by=who,  # self-grant of a BUSINESS role without business approval (synthetic drill row)
        granted_via="ADMIN",
        self_assignment=True,
        reason=LABEL,
    )
    WorkTask.objects.create(
        subject=f"کار ساختگی تمرین ({LABEL})", assignee_kind="USER", assignee_user=who, created_by=who
    )
    ApprovalRequest.objects.create(
        action_id="platform.document.approve",
        resource_type="document_revision",
        resource_id=str(uuid.uuid4()),
        resource_revision=1,
        requested_by=who,
        requested_at=now,
        expires_at=now + timedelta(days=30),
    )
    obj = StoredObject.objects.create(
        storage_key=secrets.token_urlsafe(32)[:43],
        volume="drill_volume",
        size_bytes=1024,
        sha256=hashlib.sha256(LABEL.encode()).hexdigest(),
        encryption_scheme="ENCRYPTED_VOLUME",
        key_ref="drill-key-1",
    )
    doc = Document.objects.create(
        document_type="syn_drawing", title_fa=f"سند ساختگی ({LABEL})", sensitivity="S1", created_by=who
    )
    DocumentRevision.objects.create(
        document=doc,
        revision_no=1,
        stored_object=obj,
        upload_type_id="pdf",
        sha256=obj.sha256,
        size_bytes=obj.size_bytes,
        original_name="drill.pdf",
        uploaded_by=who,
    )
    # DRILL_SKIP_JOB_RUNS=1 (rollback rehearsal scenario A): no housekeeping job runs - a run of a 0011 job
    # type blocks the reverse of 0011 by design (PROTECT FK, migration 0011 docstring item 3)
    skip_runs = os.environ.get("DRILL_SKIP_JOB_RUNS", "") == "1"
    runs = [] if skip_runs else [run_job("audit_integrity_check"), run_job("document_orphan_cleanup")]
    dead = OutboxEvent.objects.create(
        event_type="platform.synthetic.drill_seeded",
        aggregate_type="platform.synthetic",
        aggregate_id=f"drill-discard-{tag}",
        aggregate_version=1,
        actor_type="SYSTEM",
        payload={"label": f"{LABEL}_discarded"},
        delivery_status="DEAD_LETTER",
    )
    OutboxEvent.objects.filter(pk=dead.pk).update(delivery_status="DISCARDED", discarded_at=now)
    return 11 + len(runs)


if __name__ == "__main__":
    sys.exit(main())
