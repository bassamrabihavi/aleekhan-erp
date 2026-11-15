"""``manage.py job_status`` - read-only housekeeping job monitoring (PHASE_01 / 01.7).

See docs/ops/JOB_MONITORING.md.

Prints one line per housekeeping job type: newest run state, last success / failure, ``overdue`` (no success
within the TECHNICAL DEFAULT window, also when it never ran) and ``failing`` (newest finished run FAILED),
plus a verdict ``ok|warn``. 02.7: also the operator-run import applies of the applied sources (``imports``;
reason ``IMPORT_APPLY_FAILED`` when a batch's apply failed and it is still not APPLIED). ``--json`` prints one
JSON object; ``--fail-on warn`` exits 1 on ``warn`` (cron / systemd timer / monitoring agent). Machine error
codes only; no actor ids, hostnames or exception texts.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from platform_core.ops.monitoring import (
    housekeeping_health,
    housekeeping_verdict,
    import_health,
    import_verdict,
)


class Command(BaseCommand):
    help = "Read-only housekeeping job monitoring (last run, overdue, failing, verdict)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--json", action="store_true", help="print one JSON object")
        parser.add_argument(
            "--fail-on", choices=["warn"], default=None, help="exit 1 when the verdict is warn"
        )
        parser.add_argument("--database", default="default")

    def handle(self, *args: Any, **options: Any) -> None:
        jobs = housekeeping_health(using=options["database"])
        verdict, reasons = housekeeping_verdict(jobs)
        imports = import_health(using=options["database"])  # 02.7: operator-run import applies are jobs too
        reasons = [*reasons, *import_verdict(imports)]
        verdict = "warn" if reasons else verdict
        if options["json"]:
            body = {
                "verdict": verdict,
                "reasons": reasons,
                "jobs": [j.as_dict() for j in jobs],
                "imports": [i.as_dict() for i in imports],
            }
            self.stdout.write(json.dumps(body, sort_keys=True))
        else:
            for j in jobs:
                d = j.as_dict()
                self.stdout.write(
                    f"{d['job_type']}: last_state={d['last_state']} "
                    f"last_succeeded_at={d['last_succeeded_at']} "
                    f"overdue={d['overdue']} failing={d['failing']}"
                    + (f" error_code={d['last_error_code']}" if d["last_error_code"] else "")
                )
            for i in imports:
                d = i.as_dict()
                self.stdout.write(
                    f"import {d['source_code']}: apply_failed={d['apply_failed']} "
                    f"awaiting_apply={d['awaiting_apply']} last_apply_failed_at={d['last_apply_failed_at']} "
                    f"last_applied_at={d['last_applied_at']}"
                )
            self.stdout.write(f"verdict: {verdict} {' '.join(reasons)}".rstrip())
        if options["fail_on"] == "warn" and verdict == "warn":
            raise CommandError(f"housekeeping verdict {verdict} ({','.join(reasons)})", returncode=1)
