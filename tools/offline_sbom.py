#!/usr/bin/env python3
"""Offline CycloneDX SBOM of the Python runtime (fallback for the CI ``artifacts`` stage, 00.7).

``pip-audit -f cyclonedx-json`` needs PyPI. When the network is unavailable after retries, this tool builds an
inventory-only SBOM from ``backend/requirements.lock`` (no network, no vulnerability data) so the build still
records exactly what is shipped. The document says so in ``metadata.properties``
(``aleekhan:sbom-source = offline-lock``).

    python tools/offline_sbom.py <out.json>
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

LOCK = Path(__file__).resolve().parents[1] / "backend" / "requirements.lock"
_ENTRY = re.compile(r"([A-Za-z0-9_.-]+)==([^\s;]+)\s*(?:;\s*(.+))?")


def components(lock_text: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for raw in lock_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _ENTRY.fullmatch(line)
        if not m:
            raise ValueError(f"unexpected lock line: {line!r}")
        name, version, marker = m.group(1), m.group(2), m.group(3)
        purl_name = re.sub(r"[-_.]+", "-", name).lower()
        comp: dict[str, object] = {
            "type": "library",
            "bom-ref": f"pkg:pypi/{purl_name}@{version}",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{purl_name}@{version}",
        }
        if marker:
            comp["properties"] = [{"name": "aleekhan:environment-marker", "value": marker}]
        out.append(comp)
    return out


def build(lock_text: str) -> dict[str, object]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": {"type": "application", "name": "aleekhan-backend", "bom-ref": "aleekhan-backend"},
            "properties": [
                {"name": "aleekhan:sbom-source", "value": "offline-lock"},
                {
                    "name": "aleekhan:note",
                    "value": "inventory only, no vulnerability data (network unavailable)",
                },
            ],
        },
        "components": components(lock_text),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: offline_sbom.py <out.json>", file=sys.stderr)
        return 2
    doc = build(LOCK.read_text(encoding="utf-8"))
    Path(argv[0]).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"offline_sbom: {len(doc['components'])} components from backend/requirements.lock")  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
