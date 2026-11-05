"""Console bootstrap of the first owner / console recovery of the owner (DEC-003, DEC-054 C).

Run on the server console (physical access or SSH) only:

    manage.py bootstrap_owner --username <name> --display-name "<name>" --reason "<why>"
    manage.py bootstrap_owner --recover --username <owner> --reason "<why>"

The one-time password is read interactively (twice, never echoed) or from standard input with
``--password-stdin`` (one line); it is never accepted as an argument, never printed and never logged. The new
owner holds only ``owner_admin`` (DEC-049 item 4) and must change the password and enrol MFA at the first
login.
Bootstrap refuses when an owner already exists; ``--recover`` resets the owner's password (one-time) and MFA,
revokes all sessions and lifts a lock. Both are audited as SYSTEM with the given reason. There is no API for
either, and no break-glass account is created here (DEC-054 A: before production).
"""

from __future__ import annotations

import getpass
import sys
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from platform_core.engine.errors import AleekhanError


class Command(BaseCommand):
    help = "Create the first owner account (or recover the owner) from the server console (DEC-003/DEC-054)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--username", required=True)
        parser.add_argument("--display-name", default="")
        parser.add_argument("--reason", required=True)
        parser.add_argument(
            "--recover", action="store_true", help="console recovery of the owner (DEC-054 C)"
        )
        parser.add_argument(
            "--password-stdin", action="store_true", help="read the one-time password from stdin"
        )

    def _password(self, from_stdin: bool) -> str:
        if from_stdin:
            value = sys.stdin.readline().rstrip("\r\n")
        else:
            value = getpass.getpass("One-time password: ")
            if getpass.getpass("Repeat: ") != value:
                raise CommandError("the passwords do not match")
        if not value:
            raise CommandError("a password is required")
        return value

    def handle(self, *args: Any, **opts: Any) -> None:
        from platform_core.identity.users import bootstrap_owner, recover_owner

        password = self._password(bool(opts["password_stdin"]))
        try:
            if opts["recover"]:
                user = recover_owner(username=opts["username"], password=password, reason=opts["reason"])
                self.stdout.write(
                    f"owner recovered: {user.username} (one-time password set, MFA reset, sessions revoked)"
                )
            else:
                if not opts["display_name"].strip():
                    raise CommandError("--display-name is required")
                user = bootstrap_owner(
                    username=opts["username"],
                    display_name=opts["display_name"],
                    password=password,
                    reason=opts["reason"],
                )
                self.stdout.write(
                    f"owner created: {user.username} "
                    "(owner_admin; change password + enrol MFA at first login)"
                )
        except AleekhanError as exc:
            codes = ",".join(e.code for e in exc.errors)
            raise CommandError(f"{exc.code.value}{': ' + codes if codes else ''}") from None
        finally:
            del password
