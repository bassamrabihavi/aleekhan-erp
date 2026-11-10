"""``manage.py outbox_status`` - read-only outbox/job monitoring snapshot (00.7, docs/ops/JOB_MONITORING.md).

Prints counts per delivery state, due backlog, oldest pending age, stale DISPATCHED (lease expired), dead
letters, last dispatch/ack and open integration conflicts, plus a verdict ``ok|warn|critical``; since 01.6
also delivery lag / stale flag, aggregates blocked by a dead letter, held events and open compensation
records.

``--json`` prints one JSON object (for scrapers). ``--fail-on warn|critical`` makes the exit code 1 when the
verdict is at least that level (for cron / systemd timers / a monitoring agent). No payloads, error texts,
actor ids or hostnames are printed.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from platform_core.ops.monitoring import VERDICTS, outbox_snapshot


class Command(BaseCommand):
    help = "Read-only outbox/job monitoring snapshot (counts, backlog age, dead letters, verdict)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--json", action="store_true", help="print one JSON object")
        parser.add_argument(
            "--fail-on",
            choices=["warn", "critical"],
            default=None,
            help="exit with code 1 when the verdict is at least this level",
        )
        parser.add_argument("--database", default="default")

    def handle(self, *args: Any, **options: Any) -> None:
        snap = outbox_snapshot(using=options["database"])
        if options["json"]:
            self.stdout.write(json.dumps(snap.as_dict(), sort_keys=True))
        else:
            d = snap.as_dict()
            self.stdout.write(f"checked_at: {d['checked_at']}")
            self.stdout.write("counts: " + ", ".join(f"{k}={v}" for k, v in sorted(d["counts"].items())))
            for key in (
                "due_now",
                "oldest_due_age_seconds",
                "oldest_pending_age_seconds",
                "stale_dispatched",
                "dead_letters",
                "oldest_dead_letter_at",
                "last_dispatched_at",
                "last_acked_at",
                "open_conflicts",
                "lease_seconds",
            ):
                self.stdout.write(f"{key}: {d[key]}")
            integ = d.get("integration") or {}
            for key in ("lag_seconds", "stale", "blocked_aggregates", "held_events", "compensation_open"):
                self.stdout.write(f"integration.{key}: {integ.get(key)}")
            self.stdout.write(f"verdict: {d['verdict']} {' '.join(d['reasons'])}".rstrip())
        fail_on = options["fail_on"]
        if fail_on is not None and VERDICTS.index(snap.verdict) >= VERDICTS.index(fail_on):
            raise CommandError(f"outbox verdict {snap.verdict} ({','.join(snap.reasons)})", returncode=1)
