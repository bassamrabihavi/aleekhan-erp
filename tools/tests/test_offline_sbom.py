"""Unit tests for tools/offline_sbom.py (no network)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import offline_sbom as ob

LOCK = '# header\nDjango==5.2.18\ntyping_extensions==4.16.0 ; python_version < "3.13"\n'


class OfflineSbomTests(unittest.TestCase):
    def test_components_have_purls_and_markers(self) -> None:
        comps = ob.components(LOCK)
        self.assertEqual(
            [c["purl"] for c in comps], ["pkg:pypi/django@5.2.18", "pkg:pypi/typing-extensions@4.16.0"]
        )
        self.assertEqual(
            comps[1]["properties"],
            [{"name": "aleekhan:environment-marker", "value": 'python_version < "3.13"'}],
        )

    def test_document_is_labelled_offline(self) -> None:
        doc = ob.build(LOCK)
        self.assertEqual((doc["bomFormat"], doc["specVersion"]), ("CycloneDX", "1.5"))
        props = {p["name"]: p["value"] for p in doc["metadata"]["properties"]}  # type: ignore[index]
        self.assertEqual(props["aleekhan:sbom-source"], "offline-lock")

    def test_bad_line_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            ob.components("Django>=5\n")

    def test_committed_lock_parses(self) -> None:
        self.assertGreaterEqual(len(ob.components(ob.LOCK.read_text(encoding="utf-8"))), 4)


if __name__ == "__main__":
    unittest.main()
