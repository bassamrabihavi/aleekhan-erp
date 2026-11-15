"""Server console import of the Planning catalogue + legacy code registry (02.6, DEC-005 / DEC-058).

    manage.py import_planning_catalogue <path-outside-the-repo> --expected-sha256 <registered intake hash>
        [--category-columns BE=<type>,BF=<type>,...] [--codding-code-col <column>] [--sorce-header-rows 2]

* Refuses a path inside the repository and a file whose SHA-256 is not ``--expected-sha256`` (DEC-037: the
  registered baseline hash is given by the operator; it is not stored in the repo).
* An encrypted workbook needs ``ALEEKHAN_SRC_PASSWORD`` in the environment (never an argument, never
  printed). Macros are never loaded or run.
* Prints the batch id and **counts only** (no type, category, code or other value). Conflicts go to the
  conflict queue (``platform_conflict_item``, source ``planning_catalogue_xlsm``).
* ``Sorce`` has 2 header rows by default (row 1 Persian, with the type names over the category columns; row 2
  English); the product types are the first contiguous block of column E after them.
* Re-running with the same file is a no-op ("already applied"). Choose ``--codding-code-col`` before the first
  run: the staged columns are fixed per file (one batch per file hash).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from platform_core.engine.errors import AleekhanError


def command_error(exc: AleekhanError) -> CommandError:
    codes = ",".join(f"{e.field}:{e.code}" for e in exc.errors)
    return CommandError(f"{exc.code.value}{' ' + codes if codes else ''}")


class Command(BaseCommand):
    help = "Import product types, categories and legacy 14-digit codes from the Planning workbook (02.6)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("path")
        parser.add_argument("--expected-sha256", required=True)
        parser.add_argument("--category-columns", default="", help="e.g. BE=01,BF=02 (column=type code)")
        parser.add_argument("--codding-code-col", default="", help="column of the 14-digit code in Codding")
        parser.add_argument(
            "--sorce-header-rows",
            type=int,
            default=2,
            help="number of header rows of Sorce (default 2: Persian + English); row 1 names the types",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        from platform_core.product_identity import planning_import as pi

        try:
            layout = pi.Layout(
                category_column_types=pi.parse_category_columns(opts["category_columns"]),
                codding_code_col=(opts["codding_code_col"] or "").strip().upper() or None,
                header_rows=opts["sorce_header_rows"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        try:
            report = pi.import_planning_workbook(
                Path(opts["path"]),
                expected_sha256=opts["expected_sha256"],
                layout=layout,
                password=pi.password_from_env(),
            )
        except AleekhanError as exc:
            raise command_error(exc) from None
        self.stdout.write(
            json.dumps(
                {
                    "batch_id": str(report.batch_id),
                    "status": report.status,
                    "already_applied": report.already_applied,
                    "attempts": report.attempts,
                    "counts": dict(sorted(report.counts.items())),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
