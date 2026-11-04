#!/usr/bin/env python3
"""Redact personal identifiers from log text (REV-0502): home directory paths and the local account name.

Filter (stdin -> stdout), used by tools/ci_local.sh for every stage log, so committed evidence under
``reports/`` never contains ``C:\\Users\\<name>``, ``/c/Users/<name>``, ``/home/<name>`` (incl. Windows 8.3
short names such as ``ABCDEF~1.XYZ``) or the bare account name.

    some_command 2>&1 | python tools/redact_paths.py > log.txt
"""

from __future__ import annotations

import contextlib
import getpass
import os
import re
import sys

HOME_RES = (
    # C:\Users\name, C:/Users/name, c:\\users\\name (escaped in JSON)
    re.compile(r"(?i)\b[a-z]:(?:\\\\|\\|/)+users(?:\\\\|\\|/)+[^\\/\s\"'`:;,|<>]+"),
    # Git Bash / MSYS: /c/Users/name ; WSL: /mnt/c/Users/name
    re.compile(r"(?i)(?:/mnt)?/[a-z]/users/[^/\s\"'`:;,|<>]+"),
    # Linux / macOS homes
    re.compile(r"/(?:home|Users)/[^/\s\"'`:;,|<>]+"),
)


def _account_names() -> list[str]:
    names = {os.environ.get("USERNAME", ""), os.environ.get("USER", "")}
    with contextlib.suppress(Exception):  # no account info available
        names.add(getpass.getuser())
    return sorted((n for n in names if len(n) >= 3), key=len, reverse=True)


def redact(text: str, names: list[str] | None = None) -> str:
    for rx in HOME_RES:
        text = rx.sub("~", text)
    for name in _account_names() if names is None else names:
        text = re.sub(re.escape(name), "<user>", text, flags=re.I)
    return text


def main() -> int:
    names = _account_names()
    for raw in sys.stdin.buffer:  # streaming, line by line (long stages show progress)
        sys.stdout.buffer.write(redact(raw.decode("utf-8", errors="replace"), names).encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
