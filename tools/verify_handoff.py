#!/usr/bin/env python3
"""Verify the immutable handoff package against handoff/SHA256SUMS.txt.

Line-ending aware (REV-00.1-B) and aware of documented package defects (REV-00.1-A).

Result classes per SHA256SUMS entry:
  OK            exact byte match
  EOL_ONLY      bytes differ only by CRLF<->LF normalisation (content identical); warning, not failure,
                unless --strict
  KNOWN_DEFECT  documented package defect with the exact expected AND observed hash (see KNOWN_DEFECTS);
                warning, not failure, unless --strict
  EXCLUDED      entry under 09_PRIVATE_FACTORY_SOURCES/ that is absent by design (never in the repo)
  MISSING       non-excluded entry absent                                    -> failure
  MISMATCH      content differs                                              -> failure
  PRIVATE_PRESENT a 09_PRIVATE_FACTORY_SOURCES/ file exists inside the repo   -> failure (privacy guard)
  UNLISTED      file in handoff/ with no SHA256SUMS entry (except SHA256SUMS.txt itself) -> failure

Read-only: this tool never writes into handoff/. Standard library only.
Exit code: 0 = no failures, 1 = failures, 2 = usage / unreadable sums file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

EXCLUDED_PREFIX = "09_PRIVATE_FACTORY_SOURCES/"
SUMS_NAME = "SHA256SUMS.txt"

# Documented package defects. A defect is accepted ONLY if the observed hash equals the recorded one,
# so any further change to the file is still reported as MISMATCH.
KNOWN_DEFECTS = {
    "PACKAGE_MANIFEST.json": {
        "expected": "e3b9ef1b0d915f036943fdfb0a98a001f3fa381ea1736533f227befebf8479a6",
        "observed": "e20b196610e02275bef2decfbf954218b543ce3586265c11fbdc0cb1d4432eaa",
        "ref": "REV-00.1-A / docs/discovery/CONFLICTS.md C-14 / DEC-044",
    },
}

FAIL_CLASSES = {"MISSING", "MISMATCH", "PRIVATE_PRESENT", "UNLISTED"}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def eol_variants(b: bytes) -> list[bytes]:
    """Return LF and CRLF renderings of b (only if b looks like text)."""
    if b"\x00" in b[:8192]:
        return []
    lf = b.replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    return [v for v in (lf, crlf) if v != b]


def parse_sums(text: str) -> list[tuple[str, str]]:
    entries = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ValueError(f"line {n}: malformed sums line")
        digest, rel = parts[0].lower(), parts[1].strip().lstrip("*")
        p = PurePosixPath(rel)
        if p.is_absolute() or ".." in p.parts or "\\" in rel:
            raise ValueError(f"line {n}: unsafe path {rel!r}")
        entries.append((digest, rel))
    return entries


def verify(root: Path, known_defects: dict | None = None) -> list[dict]:
    known = KNOWN_DEFECTS if known_defects is None else known_defects
    sums_path = root / SUMS_NAME
    entries = parse_sums(sums_path.read_text(encoding="utf-8-sig"))
    listed = set()
    results = []
    for expected, rel in entries:
        listed.add(rel)
        f = root / rel
        excluded = rel.startswith(EXCLUDED_PREFIX)
        if not f.is_file():
            results.append({"path": rel, "status": "EXCLUDED" if excluded else "MISSING"})
            continue
        if excluded:
            results.append({"path": rel, "status": "PRIVATE_PRESENT"})
            continue
        data = f.read_bytes()
        actual = sha256_bytes(data)
        if actual == expected:
            results.append({"path": rel, "status": "OK"})
        elif any(sha256_bytes(v) == expected for v in eol_variants(data)):
            results.append({"path": rel, "status": "EOL_ONLY", "actual": actual})
        elif rel in known and known[rel]["expected"] == expected and known[rel]["observed"] == actual:
            results.append({"path": rel, "status": "KNOWN_DEFECT", "actual": actual, "expected": expected,
                            "ref": known[rel]["ref"]})
        else:
            results.append({"path": rel, "status": "MISMATCH", "actual": actual, "expected": expected})
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root).as_posix()
        if rel == SUMS_NAME or rel in listed:
            continue
        status = "PRIVATE_PRESENT" if rel.startswith(EXCLUDED_PREFIX) else "UNLISTED"
        results.append({"path": rel, "status": status})
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent / "handoff"),
                    help="handoff directory (default: <repo>/handoff)")
    ap.add_argument("--strict", action="store_true", help="treat EOL_ONLY and KNOWN_DEFECT as failures")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)
    root = Path(a.root)
    try:
        results = verify(root)
    except (OSError, ValueError) as e:
        print(f"ERROR: cannot read {root / SUMS_NAME}: {e}", file=sys.stderr)
        return 2
    fail = set(FAIL_CLASSES) | ({"EOL_ONLY", "KNOWN_DEFECT"} if a.strict else set())
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    failed = [r for r in results if r["status"] in fail]
    if a.json:
        print(json.dumps({"root": str(root), "counts": counts, "strict": a.strict,
                          "failed": len(failed), "results": [r for r in results if r["status"] != "OK"]},
                         ensure_ascii=False, indent=2))
    else:
        for r in results:
            if r["status"] in ("OK", "EXCLUDED"):
                continue
            extra = f" ({r['ref']}; expected {r['expected']}, actual {r['actual']})" if r["status"] == "KNOWN_DEFECT" else ""
            print(f"{r['status']:<15} {r['path']}{extra}")
        print("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
              + f" | failures={len(failed)}{' (strict)' if a.strict else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
