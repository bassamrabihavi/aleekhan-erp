"""``manage.py run_housekeeping <job_type>|--all`` - run housekeeping jobs once (PHASE_01 / 01.7).

For a systemd timer / cron on the app host until the Celery worker (ADR-001) is wired: each job runs under the
job-run lifecycle (``jobs.service.run_job``: QUEUED -> RUNNING -> SUCCEEDED / FAILED, checkpoint after each
batch, a requested safe cancel stops it), so it is visible on page 36 and in ``manage.py job_status``. The
exit code is 1 when a job ends FAILED. Prints job type and final state only.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = "Run one (or every) housekeeping job once under the job-run lifecycle."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("job_type", nargs="?", default="")
        parser.add_argument("--all", action="store_true", help="run every housekeeping job type in order")

    def handle(self, *args: Any, **opts: Any) -> None:
        from platform_core.jobs.service import HOUSEKEEPING_TYPES, run_job

        if opts["all"] == bool(opts["job_type"]):
            raise CommandError("give exactly one of <job_type> or --all")
        types = list(HOUSEKEEPING_TYPES) if opts["all"] else [opts["job_type"]]
        unknown = [t for t in types if t not in HOUSEKEEPING_TYPES]
        if unknown:
            raise CommandError(f"unknown housekeeping job type: {unknown[0][:64]}")
        failed = []
        for job_type in types:
            run = run_job(job_type)
            self.stdout.write(f"{job_type}: {run.state}")
            if run.state == "FAILED":
                failed.append(job_type)
        if failed:
            raise CommandError(f"failed: {','.join(failed)}", returncode=1)
