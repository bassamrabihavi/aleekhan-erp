"""Unit tests for tools/redact_paths.py (REV-0502). Synthetic account names only."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import redact_paths as rp

NAME = "Syn.User"


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
                self.assertEqual(rp.redact(raw, [NAME]), expected)

    def test_account_name_is_replaced_and_other_text_kept(self) -> None:
        out = rp.redact("owner syn.user wrote F:/aleekhan/repo/file.txt", [NAME])
        self.assertEqual(out, "owner <user> wrote F:/aleekhan/repo/file.txt")

    def test_short_names_are_ignored(self) -> None:
        self.assertEqual(rp.redact("ab cd", []), "ab cd")


if __name__ == "__main__":
    unittest.main()
