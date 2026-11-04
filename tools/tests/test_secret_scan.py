"""Unit tests for tools/secret_scan.py.

Every "secret" below is SYNTHETIC and assembled at runtime from fragments, so no secret-shaped literal is
committed (the scanner must still pass on this file).
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import secret_scan as ss

J = "".join
PEM = J(["-----BEGIN ", "RSA PRIVATE KEY-----"])
AWS = J(["AK", "IA", "Q" * 16])
GH = J(["gh", "p_", "a1B2" * 9])
ANT = J(["sk-", "ant-", "z9" * 12])
SLACK = J(["xo", "xb-", "1234567890-abc"])
PW_VALUE = J(["Zq7", "!kLm", "pR2"])


class ScanLineTests(unittest.TestCase):
    def test_detects_each_rule(self) -> None:
        cases = {
            "private-key": PEM,
            "aws-access-key": f"key = {AWS}",
            "github-token": f"token: {GH}",
            "anthropic-key": f"ANTHROPIC={ANT}",
            "slack-token": SLACK,
            "password-literal": J(["db_pass", 'word = "', PW_VALUE, '"']),
            "src-password-assign": J(["ALEEKHAN_SRC_", "PASSWORD=", PW_VALUE]),
            "conn-string-password": J(["postgres://app:", PW_VALUE, "@db.internal:5432/x"]),
        }
        for rule, line in cases.items():
            with self.subTest(rule=rule):
                self.assertIn(rule, ss.scan_line(line))

    def test_placeholders_and_prompts_are_not_findings(self) -> None:
        for line in (
            J(['password = "', "synthetic-not-a-secret", '"']),
            J(['"DJANGO_SECRET_', 'KEY": "CHANGE_ME"']),
            J(['password: "<your-password>"']),
            # split before the opening quote: the raw source line itself must not look like a literal
            J(["password = ", '"${PGPASS', 'WORD}"']),
            "postgres://user:pass@host:5432/dbname",
            "postgres://user:${PGPASSWORD}@host/db",
            J(["$env:ALEEKHAN_SRC_", "PASSWORD = Read-Host -AsSecureString"]),
            "password=hunter2 inside a sentence without quotes is not an assignment literal",
            "a regular line of code = 1",
        ):
            with self.subTest(line=line):
                self.assertEqual(ss.scan_line(line), [])

    def test_allow_pragma(self) -> None:
        self.assertEqual(ss.scan_line(f"{AWS}  # secret-scan: allow"), [])

    def test_env_file_names(self) -> None:
        self.assertTrue(ss.is_env_file(".env"))
        self.assertTrue(ss.is_env_file("backend/.env.local"))
        self.assertFalse(ss.is_env_file("backend/.env.example"))
        self.assertFalse(ss.is_env_file("docs/env.md"))

    def test_env_secret_value_is_reported_but_never_printed(self) -> None:
        value = J(["synthetic", "-env-", "value-", "1234"])
        found = list(ss.scan_text("f.txt", f"x\nconnect with {value}\n", [value]))
        self.assertEqual(found, [ss.Finding("f.txt:2", "env-secret-value")])
        self.assertNotIn(value, repr(found))


def _git(cwd: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "syn", "GIT_AUTHOR_EMAIL": "syn@example.invalid",
           "GIT_COMMITTER_NAME": "syn", "GIT_COMMITTER_EMAIL": "syn@example.invalid"}  # fmt: skip
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, env=env)


class RepoScanTests(unittest.TestCase):
    def test_worktree_and_history_findings_without_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root, "init", "-q")
            (root / "clean.py").write_text("x = 1\n", encoding="utf-8")
            (root / "leak.cfg").write_text(f"a=1\naws={AWS}\n", encoding="utf-8")
            (root / ".env").write_text("A=1\n", encoding="utf-8")
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "synthetic leak")
            (root / "leak.cfg").write_text("a=1\n", encoding="utf-8")  # removed from the tree ...
            _git(root, "rm", "-q", "--cached", ".env")
            (root / ".env").unlink()
            _git(root, "commit", "-q", "-am", "remove")

            tree, scanned = ss.scan_worktree(root)
            self.assertEqual(tree, [])
            self.assertEqual(scanned, 2)
            hist, commits = ss.scan_history(root, 100)  # ... but still in history
            self.assertEqual(commits, 2)
            self.assertEqual({f.rule for f in hist}, {"aws-access-key", "env-file"})
            self.assertTrue(all(":" in f.where for f in hist))

            out = io.StringIO()
            with redirect_stdout(out), mock.patch.dict(os.environ, {}, clear=False):
                rc = ss.main(["--root", str(root), "--history"])
            self.assertEqual(rc, 1)
            self.assertNotIn(AWS, out.getvalue())
            self.assertIn("aws-access-key", out.getvalue())


SHA_A = "a" * 40
SHA_B = "b" * 40


class AllowlistTests(unittest.TestCase):
    def _write(self, text: str) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
        tmp.write(text)
        tmp.close()
        self.addCleanup(os.unlink, tmp.name)
        return Path(tmp.name)

    def test_only_the_exact_fingerprint_matches(self) -> None:
        allow = ss.load_allowlist(self._write(f"# c\n{SHA_A} tools/x.py password-literal reviewed reason\n"))
        self.assertTrue(ss.is_allowed(SHA_A, "tools/x.py", "password-literal", allow))
        self.assertFalse(ss.is_allowed(SHA_B, "tools/x.py", "password-literal", allow))  # other commit
        self.assertFalse(ss.is_allowed(SHA_A[:12], "tools/x.py", "password-literal", allow))  # short sha
        self.assertFalse(ss.is_allowed(SHA_A, "tools/y.py", "password-literal", allow))  # other path
        self.assertFalse(ss.is_allowed(SHA_A, "tools/x.py", "aws-access-key", allow))  # other rule

    def test_malformed_entries_are_rejected(self) -> None:
        for bad in (
            "abc tools/x.py password-literal reason",  # not a full sha
            f"{SHA_A} tools/x.py no-such-rule reason",
            f"{SHA_A} tools/x.py password-literal",  # no reason
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ss.load_allowlist(self._write(bad + "\n"))

    def test_committed_allowlist_is_valid_and_pinned(self) -> None:
        allow = ss.load_allowlist()
        self.assertTrue(all(len(e.commit) == 40 for e in allow))
        self.assertLessEqual(len(allow), 5, "the allowlist must stay exceptional")


class UntrackedScanTests(unittest.TestCase):
    def test_untracked_non_ignored_files_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root, "init", "-q")
            (root / ".gitignore").write_text("ignored.cfg\n", encoding="utf-8")
            (root / "new.cfg").write_text(f"aws={AWS}\n", encoding="utf-8")  # never git-added
            (root / "ignored.cfg").write_text(f"aws={AWS}\n", encoding="utf-8")
            tree, _ = ss.scan_worktree(root)
            self.assertEqual(tree, [ss.Finding("new.cfg:1", "aws-access-key")])

    def test_history_allowlist_suppresses_only_its_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _git(root, "init", "-q")
            (root / "a.cfg").write_text(f"k={AWS}\n", encoding="utf-8")
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "one")
            first = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
            ).stdout.strip()
            (root / "a.cfg").write_text(f"k={AWS}\nk2={AWS}\n", encoding="utf-8")
            _git(root, "commit", "-q", "-am", "two")
            allow = frozenset({ss.AllowEntry(first, "a.cfg", "aws-access-key")})
            suppressed: list[ss.Finding] = []
            hist, _ = ss.scan_history(root, 100, (), allow, suppressed)
            self.assertEqual([f.where.split(":")[0] for f in suppressed], [first[:12]])
            self.assertEqual(len(hist), 1)  # the second commit is still reported
            self.assertNotEqual(hist[0].where.split(":")[0], first[:12])


if __name__ == "__main__":
    unittest.main()
