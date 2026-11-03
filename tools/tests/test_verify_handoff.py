"""Unit tests for tools/verify_handoff.py (synthetic files only; never touches handoff/)."""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import verify_handoff as vh


def h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class VerifyHandoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_pkg(self, files: dict, sums: dict):
        for rel, data in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        (self.root / vh.SUMS_NAME).write_text(
            "".join(f"{d}  {rel}\n" for rel, d in sums.items()), encoding="utf-8"
        )

    def statuses(self, known=None):
        return {r["path"]: r["status"] for r in vh.verify(self.root, known or {})}

    def test_exact_match_ok(self):
        self.write_pkg({"a.md": b"x\n"}, {"a.md": h(b"x\n")})
        self.assertEqual(self.statuses(), {"a.md": "OK"})

    def test_crlf_registered_lf_on_disk_is_eol_only(self):
        self.write_pkg({"t.csv": b"a,b\nc,d\n"}, {"t.csv": h(b"a,b\r\nc,d\r\n")})
        self.assertEqual(self.statuses(), {"t.csv": "EOL_ONLY"})

    def test_lf_registered_crlf_on_disk_is_eol_only(self):
        self.write_pkg({"t.csv": b"a\r\nb\r\n"}, {"t.csv": h(b"a\nb\n")})
        self.assertEqual(self.statuses(), {"t.csv": "EOL_ONLY"})

    def test_content_change_is_mismatch(self):
        self.write_pkg({"t.csv": b"a,b\n"}, {"t.csv": h(b"a,X\r\n")})
        self.assertEqual(self.statuses(), {"t.csv": "MISMATCH"})

    def test_private_entries_absent_are_excluded(self):
        self.write_pkg({}, {"09_PRIVATE_FACTORY_SOURCES/p.xlsm": "0" * 64})
        self.assertEqual(self.statuses(), {"09_PRIVATE_FACTORY_SOURCES/p.xlsm": "EXCLUDED"})

    def test_private_file_present_fails(self):
        self.write_pkg(
            {"09_PRIVATE_FACTORY_SOURCES/p.txt": b"s"}, {"09_PRIVATE_FACTORY_SOURCES/p.txt": h(b"s")}
        )
        self.assertEqual(self.statuses(), {"09_PRIVATE_FACTORY_SOURCES/p.txt": "PRIVATE_PRESENT"})

    def test_missing_non_private_fails(self):
        self.write_pkg({}, {"gone.md": "0" * 64})
        self.assertEqual(self.statuses(), {"gone.md": "MISSING"})

    def test_unlisted_file_fails(self):
        self.write_pkg({"a.md": b"x", "extra.md": b"y"}, {"a.md": h(b"x")})
        self.assertEqual(self.statuses()["extra.md"], "UNLISTED")

    def test_known_defect_only_with_exact_observed_hash(self):
        data = b"{}"
        known = {"m.json": {"expected": "1" * 64, "observed": h(data), "ref": "REV"}}
        self.write_pkg({"m.json": data}, {"m.json": "1" * 64})
        self.assertEqual(self.statuses(known), {"m.json": "KNOWN_DEFECT"})
        (self.root / "m.json").write_bytes(b"{ }")  # further drift must not be masked
        self.assertEqual(self.statuses(known), {"m.json": "MISMATCH"})

    def test_unsafe_path_rejected(self):
        (self.root / vh.SUMS_NAME).write_text("0" * 64 + "  ../escape.txt\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            vh.verify(self.root, {})

    def test_windows_drive_path_rejected(self):
        # REV-0003 regression: drive-letter paths must not escape the package root on Windows.
        for bad in ("C:/escape.txt", "c:escape.txt", "Z:/dir/x.txt"):
            line = "0" * 64 + "  " + bad + "\n"
            (self.root / vh.SUMS_NAME).write_text(line, encoding="utf-8")
            with self.subTest(path=bad), self.assertRaises(ValueError):
                vh.verify(self.root, {})

    def test_cli_exit_codes(self):
        self.write_pkg({"t.csv": b"a\n"}, {"t.csv": h(b"a\r\n")})
        self.assertEqual(vh.main(["--root", str(self.root)]), 0)
        self.assertEqual(vh.main(["--root", str(self.root), "--strict"]), 1)


if __name__ == "__main__":
    unittest.main()
