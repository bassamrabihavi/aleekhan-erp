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
import socket
import sys
from pathlib import Path

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


# junit xml (pytest --junitxml): <testsuite ... hostname="WORKSTATION-01" ...>
JUNIT_HOSTNAME_RE = re.compile(r'\bhostname="[^"]*"')


def _host_names() -> list[str]:
    names = {os.environ.get("COMPUTERNAME", ""), os.environ.get("HOSTNAME", "")}
    with contextlib.suppress(Exception):  # no host name available
        names.add(socket.gethostname())
    names |= {n.split(".")[0] for n in names}
    return sorted((n for n in names if len(n) >= 3), key=len, reverse=True)


def redact(text: str, names: list[str] | None = None, hosts: list[str] | None = None) -> str:
    for rx in HOME_RES:
        text = rx.sub("~", text)
    text = JUNIT_HOSTNAME_RE.sub('hostname="<host>"', text)
    for host in _host_names() if hosts is None else hosts:
        text = re.sub(rf"(?<![\w-]){re.escape(host)}(?![\w-])", "<host>", text, flags=re.I)
    for name in _account_names() if names is None else names:
        text = re.sub(re.escape(name), "<user>", text, flags=re.I)
    return text


def redact_files(paths: list[str]) -> int:
    names, hosts = _account_names(), _host_names()
    for p in paths:
        path = Path(p)
        if not path.is_file():
            continue  # a stage that did not run leaves no junit file; nothing to redact
        raw = path.read_bytes().decode("utf-8", errors="replace")
        path.write_bytes(redact(raw, names, hosts).encode("utf-8"))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["--in-place"]:
        return redact_files(args[1:])
    names, hosts = _account_names(), _host_names()
    for raw in sys.stdin.buffer:  # streaming, line by line (long stages show progress)
        sys.stdout.buffer.write(redact(raw.decode("utf-8", errors="replace"), names, hosts).encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
