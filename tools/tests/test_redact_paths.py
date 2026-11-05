"""Unit tests for tools/redact_paths.py (REV-0502). Synthetic account names only."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import redact_paths as rp

NAME = "Syn.User"
HOST = "SYN-WORKSTATION-07"


class RedactTests(unittest.TestCase):
    def test_home_paths_are_replaced(self) -> None:
        cases = {
            r"C:\Users\Syn.User\AppData\Local\x.log": r"~\AppData\Local\x.log",
            "C:/Users/Syn.User/AppData/x": "~/AppData/x",
            r'{"p": "C:\\Users\\Syn.User\\x"}': r'{"p": "~\\x"}',
            "/c/Users/Syn.User/AppData/node": "~/AppData/node",
            "/mnt/c/Users/Syn.User/x": "~/x",
            r"C:\Users\SYNUSE~1.USR\AppData\Local\Temp": r"~\AppData\Local\Temp",
            "/home/synuser/aleekhan": "~/aleekhan",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(rp.redact(raw, [NAME], []), expected)

    def test_account_name_is_replaced_and_other_text_kept(self) -> None:
        out = rp.redact("owner syn.user wrote F:/aleekhan/repo/file.txt", [NAME], [])
        self.assertEqual(out, "owner <user> wrote F:/aleekhan/repo/file.txt")

    def test_short_names_are_ignored(self) -> None:
        self.assertEqual(rp.redact("ab cd", [], []), "ab cd")

    def test_junit_hostname_attribute_is_redacted(self) -> None:
        """REV-0103: pytest junit xml records the workstation host name; evidence is public (DEC-046)."""
        xml = '<testsuite name="pytest" errors="0" hostname="ANY-OTHER-HOST" tests="3">'
        self.assertEqual(
            rp.redact(xml, [], []), '<testsuite name="pytest" errors="0" hostname="<host>" tests="3">'
        )

    def test_host_name_is_redacted_as_a_whole_word_only(self) -> None:
        out = rp.redact(f"run on {HOST.lower()} ({HOST}.corp.local); kept: X{HOST}Y", [], [HOST])
        self.assertEqual(out, f"run on <host> (<host>.corp.local); kept: X{HOST}Y")

    def test_in_place_rewrites_junit_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "pytest.xml"
            p.write_text(f'<testsuite hostname="{HOST}" timestamp="2026-11-04T00:00:00"/>', encoding="utf-8")
            self.assertEqual(rp.main(["--in-place", str(p), str(Path(tmp) / "missing.xml")]), 0)
            self.assertEqual(
                p.read_text(encoding="utf-8"),
                '<testsuite hostname="<host>" timestamp="2026-11-04T00:00:00"/>',
            )


if __name__ == "__main__":
    unittest.main()
