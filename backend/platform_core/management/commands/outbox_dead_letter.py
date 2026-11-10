"""``manage.py outbox_dead_letter`` - dead-letter handling on the server console (01.7, REV-0129, REV-0133).

    manage.py outbox_dead_letter list [--json]
    manage.py outbox_dead_letter replay  --user <username> --event-id <uuid> --reason "<why>"
    manage.py outbox_dead_letter discard --user <username> --event-id <uuid> --reason "<why>"

(``--owner`` is kept as an alias of ``--user``.)
``list`` is read-only (event id, type, aggregate type, time, attempts, events held behind it - never payloads,
error texts or actor ids). ``replay`` sends the event back to PENDING; ``discard`` makes it DISCARDED for good
(it is never delivered; later events of its aggregate are released). Both are audited as the named user with
the reason. ``replay`` needs an ACTIVE ``owner_admin`` or ``it_ops`` holder; ``discard`` an ACTIVE
``owner_admin`` (employer decision 2026-11-10, REV-0133); anybody else is refused (exit code 1). See
docs/ops/JOB_MONITORING.md section "Dead letters".
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from platform_core.engine.errors import AleekhanError


class Command(BaseCommand):
    help = "List, replay (owner_admin/it_ops) or discard (owner_admin) DEAD_LETTER outbox events, audited."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("action", choices=["list", "replay", "discard"])
        parser.add_argument(
            "--user",
            "--owner",
            dest="owner",
            default="",
            help="username of the acting user (replay: owner_admin or it_ops; discard: owner_admin)",
        )
        parser.add_argument("--event-id", default="")
        parser.add_argument("--reason", default="")
        parser.add_argument("--json", action="store_true", help="list: one JSON array")

    def handle(self, *args: Any, **opts: Any) -> None:
        from platform_core.ops import dead_letters

        if opts["action"] == "list":
            rows = dead_letters.list_dead_letters()
            if opts["json"]:
                self.stdout.write(json.dumps([{**asdict(r), "event_id": str(r.event_id)} for r in rows]))
            else:
                for r in rows:
                    self.stdout.write(
                        f"{r.event_id} {r.event_type} {r.aggregate_type} {r.occurred_at} "
                        f"attempts={r.attempts} held_behind={r.held_behind}"
                    )
                self.stdout.write(f"dead_letters: {len(rows)}")
            return
        if not opts["owner"].strip():
            raise CommandError("--user is required")
        if len(opts["reason"].strip()) < 3:
            raise CommandError("--reason is required (at least 3 characters)")
        try:
            event_id = uuid.UUID(opts["event_id"])
        except ValueError:
            raise CommandError("--event-id must be a UUID") from None
        try:
            status = dead_letters.handle(
                action=opts["action"], username=opts["owner"], event_id=event_id, reason=opts["reason"]
            )
        except AleekhanError as exc:
            raise CommandError(exc.code.value) from None
        self.stdout.write(f"{opts['action']}: {event_id} -> {status}")
