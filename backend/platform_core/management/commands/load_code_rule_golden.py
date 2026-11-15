"""Server console loader of DEC-005 golden cases into a NEW DRAFT code rule revision (PHASE_02 / 02.6).

    manage.py load_code_rule_golden <golden.json outside the repo> --maker <user uuid>
        --source-sha256 <registered workbook hash> [--types 01,02,...]

* The file is the golden-harness format (a JSON list of flat text objects, see
  ``tests/test_phase02_golden_harness.py``) **plus** ``source_sheet`` and ``source_cell_ref`` per case, and
  **without** the harness-only fields ``legacy_disputed`` / ``belt_width_source`` (refused, REV-0240).
* Refuses a path inside the repository (real cases never enter Git, DEC-028 / DEC-046, R-38).
* The 02.3 engine creates the revision and its cases as the maker (permission ``identity.code_rule.manage``;
  the maker can never approve it). Scope = ``--types`` or the families in the file. All or nothing.
* 02.7 (REV-0262): ``--maker`` must be an ACTIVE user holding ``identity.code_rule.manage``, and the operator
  passes HIS OWN user id (docs/integration/README.md, "Console operator rules"). The audit trail records the
  console origin (``identity.code_rule.console_load``: command, source batch, case count).
* 02.7 (REV-0266): ``--source-sha256`` must be the hash of an APPLIED ``planning_catalogue_xlsm`` batch
  (``SOURCE_BATCH_NOT_APPLIED`` otherwise).
* Prints the revision id and counts only (``golden_summary``), never a case value. The approver reviews it in
  the UI (code rules page); submit / approve stay in-app.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from platform_core.engine.errors import AleekhanError

from .import_planning_catalogue import command_error


class Command(BaseCommand):
    help = "Load golden cases (JSON outside the repo) into a new DRAFT code rule revision (DEC-005)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("path")
        parser.add_argument(
            "--maker",
            required=True,
            help="YOUR OWN user id (uuid): an active holder of identity.code_rule.manage",
        )
        parser.add_argument("--source-sha256", required=True, help="hash of an APPLIED Planning import batch")
        parser.add_argument("--types", default="", help="product type codes of the scope, e.g. 01,02")

    def handle(self, *args: Any, **opts: Any) -> None:
        from platform_core.product_identity.planning_import import load_golden_cases

        try:
            maker = uuid.UUID(opts["maker"])
        except ValueError:
            raise CommandError("--maker must be a user id (uuid)") from None
        types = [t.strip() for t in opts["types"].split(",") if t.strip()] or None
        try:
            summary = load_golden_cases(
                Path(opts["path"]), maker_id=maker, source_sha256=opts["source_sha256"], product_types=types
            )
        except AleekhanError as exc:
            raise command_error(exc) from None
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
