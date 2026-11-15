"""Read-only DEC-006 check: are all legacy serials of the Planning workbook below the system range?

    manage.py legacy_serial_guard <path-outside-the-repo> --expected-sha256 <registered intake hash>
        [--threshold <n>]

Counts ``NOrder!B`` values only: plain integers, plain integers >= threshold (must be 0 for the first system
serial 63001 to be safe), duplicated plain values, and the other shapes by mask (``A9+``, ``9+-9``, ...).
Never prints a serial value, never writes anything (no batch, no row). The threshold defaults to the counter's
``legacy_max_exclusive`` (63000, DEC-006 / migration 0021). ``ALEEKHAN_SRC_PASSWORD`` decrypts in memory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from platform_core.engine.errors import AleekhanError

from .import_planning_catalogue import command_error


class Command(BaseCommand):
    help = "Count legacy NOrder!B serials at or above the system range (DEC-006), read only, counts only."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("path")
        parser.add_argument("--expected-sha256", required=True)
        parser.add_argument("--threshold", type=int, default=None)

    def handle(self, *args: Any, **opts: Any) -> None:
        from platform_core.product_identity import planning_import as pi
        from platform_core.product_identity.models import FACTORY_SERIAL_NAMESPACE, SerialCounter

        threshold = opts["threshold"]
        if threshold is None:
            counter = SerialCounter.objects.filter(namespace_key=FACTORY_SERIAL_NAMESPACE).first()
            if counter is None:
                raise CommandError("no serial counter: pass --threshold")
            threshold = counter.legacy_max_exclusive
        if threshold < 1:
            raise CommandError("--threshold must be positive")
        try:
            src = pi.read_source_file(Path(opts["path"]), expected_sha256=opts["expected_sha256"])
            wb = pi.open_workbook(src.data, password=pi.password_from_env())
            try:
                counts = pi.serial_guard_counts(wb, pi.Layout(), threshold=threshold)
            finally:
                wb.close()
        except AleekhanError as exc:
            raise command_error(exc) from None
        self.stdout.write(json.dumps(counts, ensure_ascii=False, indent=2))
