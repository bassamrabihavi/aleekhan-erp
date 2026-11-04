"""Unit tests for tools/lock_runtime.py (runtime dependency lock)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lock_runtime as lr


class LockTests(unittest.TestCase):
    def test_entries_skip_other_platform_markers(self) -> None:
        text = (
            "# header\n"
            "Django==5.2.18\n"
            'tzdata==2026.6 ; sys_platform == "no-such-platform"\n'
            'typing_extensions==4.16.0 ; python_version >= "3"\n'
        )
        self.assertEqual(lr._entries(text), {"django": "5.2.18", "typing-extensions": "4.16.0"})

    def test_render_is_sorted_and_keeps_markers(self) -> None:
        out = lr.render({"b": ("B", "2", None), "a": ("A", "1", 'sys_platform == "win32"')})
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("# GENERATED"))
        self.assertEqual(lines[-2:], ['A==1 ; sys_platform == "win32"', "B==2"])

    def test_committed_lock_matches_this_venv(self) -> None:
        """The lock covers every runtime requirement installed here (same check as CI ``--check``)."""
        self.assertEqual(lr.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
