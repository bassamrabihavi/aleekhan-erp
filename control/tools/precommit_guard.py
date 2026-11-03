#!/usr/bin/env python3
"""Pre-commit guard (cross-platform): blocks private sources, office/CAD files and secrets."""
import os
import re
import subprocess
import sys

BLOCK_EXT = (".xlsm", ".xlsx", ".xls", ".dxf", ".dwg", ".zip", ".7z", ".rar")
SECRET_RE = re.compile(
    r"(ALEEKHAN_SRC_PASSWORD\s*=\s*['\"]?(?!Read-Host)[A-Za-z0-9!@#%^&*_+=-]{4,}|password\s*[:=]\s*['\"][A-Za-z0-9!@#%^&*_+=-]{4,}['\"]|"
    r"BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|AKIA[0-9A-Z]{16}|sk-ant-[A-Za-z0-9_-]{10,})", re.I)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def main():
    bad = []
    for f in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines():
        low = f.lower()
        if "09_private_factory_sources" in low or low.endswith(BLOCK_EXT):
            bad.append(f"private/source-type file staged: {f}")
    added = [l[1:] for l in git("diff", "--cached", "-U0").splitlines() if l.startswith("+") and not l.startswith("+++")]
    pw = os.environ.get("ALEEKHAN_SRC_PASSWORD")
    for line in added:
        if SECRET_RE.search(line):
            bad.append("possible secret in staged diff: " + line.strip()[:60] + "...")
        if pw and pw in line:
            bad.append("source password found in staged diff")
    if bad:
        print("BLOCKED by Aleekhan guard:")
        for b in dict.fromkeys(bad):
            print("  -", b)
        sys.exit(1)


if __name__ == "__main__":
    main()
