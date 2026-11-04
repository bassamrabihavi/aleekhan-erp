#!/usr/bin/env python3
"""Repository secret scanner (PHASE_00 / 00.7). Standard library only; cross-platform.

Scans (1) every git-tracked file of the working tree and (2) optionally the added lines of the git history
(``git log -p``), and reports ``file:line rule`` (or ``commit:file rule`` for history). Matched values are
NEVER printed - only the location and the rule id - so the report itself is safe to commit.

Rules (extends ``control/tools/precommit_guard.py``):

* ``private-key``          PEM private key header
* ``aws-access-key``       ``AKIA`` access key id
* ``github-token``         ``ghp_/gho_/ghu_/ghs_/ghr_`` tokens and fine-grained ``github_pat_``
* ``anthropic-key``        ``sk-ant-`` keys; ``openai-key`` ``sk-`` / ``sk-proj-`` keys
* ``slack-token``          ``xox[abprs]-`` tokens
* ``password-literal``     ``password|passwd|pwd|secret|token|api_key ... = "<literal>"``
* ``src-password-assign``  ``ALEEKHAN_SRC_PASSWORD=<literal>``
* ``conn-string-password`` ``scheme://user:<password>@host``
* ``env-file``             a tracked ``.env`` / ``.env.*`` file (only ``.env.example`` is allowed)
* ``env-secret-value``     the *value* of ``ALEEKHAN_SRC_PASSWORD`` / ``PGPASSWORD`` from the current
  environment appears in a file (checked only when set and >= 8 characters; never printed)

Placeholders are not findings: values containing ``synthetic``, ``example``, ``placeholder``, ``change_me``,
``dummy``, ``redacted``, ``not-a-real``, ``<...>``, ``${...}``, ``$(...)``, ``%(...)s``, ``{{...}}``, ``***``,
``xxxx`` or the literal words ``pass``/``password``/``secret``. A line may opt out explicitly with the
pragma ``secret-scan: allow`` (reviewed like any other change).

The working-tree scan covers tracked AND untracked, non-ignored files (``git ls-files --cached --others
--exclude-standard``), so a finding is caught before ``git add``.

History allowlist (``tools/secret_scan_allowlist.txt``): published history cannot be rewritten, so a reviewed
false positive in an old commit is suppressed only by an exact fingerprint ``<full 40-char commit sha> <path>
<rule> <reason>``. It never applies to the working tree or to any other commit, path or rule. Suppressed
entries are counted in the output.

Usage::

    python tools/secret_scan.py [--history] [--max-commits N] [--json OUT] [--root DIR]

Exit code: 0 = no findings, 1 = findings, 2 = usage / git error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

ALLOW_PRAGMA = "secret-scan: allow"
SKIP_EXT = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".zip", ".7z", ".rar", ".gz", ".xlsx", ".xlsm", ".xls", ".dwg", ".dxf",
)  # fmt: skip
MAX_FILE_BYTES = 5 * 1024 * 1024

_PLACEHOLDER_RE = re.compile(
    r"synthetic|example|placeholder|change_?me|dummy|redacted|not-a-real|fake|sample|"
    r"<[^>]*>|\$\{[^}]*\}|\$\([^)]*\)|%\([^)]*\)s|\{\{[^}]*\}\}|\*{3,}|x{4,}|^(?:pass|password|secret)$",
    re.I,
)

RULES: tuple[tuple[str, re.Pattern[str], int | None], ...] = (
    # (rule id, pattern, capture group holding the value to check for placeholders - None = always a finding)
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY"), None),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), None),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"), None),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"), None),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b"), None),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), None),
    (
        "password-literal",
        re.compile(
            r"""(?i)\b[\w-]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)"""
            r"""["']?\s*[:=]\s*["']([^"'\s]{4,})["']"""
        ),
        1,
    ),
    # PowerShell prompt (``= Read-Host -AsSecureString``) is the documented way to set it: not a literal.
    ("src-password-assign", re.compile(r"ALEEKHAN_SRC_PASSWORD\s*=\s*['\"]?(?!Read-Host)([^\s'\"$]{4,})"), 1),
    (
        "conn-string-password",
        re.compile(r"\b[a-z][a-z0-9+.-]{1,20}://[^/\s:@'\"]+:([^@\s/'\"]{3,})@[^\s'\"]+"),
        1,
    ),
)

ENV_SECRET_VARS = ("ALEEKHAN_SRC_PASSWORD", "PGPASSWORD")
RULE_IDS = frozenset([r[0] for r in RULES] + ["env-file", "env-secret-value"])
ALLOWLIST_FILE = Path(__file__).resolve().parent / "secret_scan_allowlist.txt"
_SHA_RE = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class Finding:
    where: str  # "path:line" or "commit12:path"
    rule: str


@dataclass(frozen=True)
class AllowEntry:
    commit: str  # full 40-char sha
    path: str
    rule: str


def load_allowlist(path: Path = ALLOWLIST_FILE) -> frozenset[AllowEntry]:
    """``<sha40> <path> <rule> <reason...>`` per line, ``#`` comments. A malformed line is an error."""
    if not path.is_file():
        return frozenset()
    out = set()
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=3)
        if len(parts) < 4 or not _SHA_RE.fullmatch(parts[0]) or parts[2] not in RULE_IDS:
            raise ValueError(f"{path.name}:{no}: expected '<sha40> <path> <rule> <reason>'")
        out.add(AllowEntry(parts[0], parts[1], parts[2]))
    return frozenset(out)


def is_allowed(commit: str, path: str, rule: str, allow: frozenset[AllowEntry]) -> bool:
    """Exact fingerprint match only (full commit sha + path + rule)."""
    return AllowEntry(commit, path, rule) in allow


def is_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(value))


def scan_line(line: str) -> list[str]:
    """Rule ids that match ``line`` (values are never returned)."""
    if ALLOW_PRAGMA in line:
        return []
    hits: list[str] = []
    for rule, pattern, group in RULES:
        for m in pattern.finditer(line):
            if group is not None and is_placeholder(m.group(group)):
                continue
            hits.append(rule)
            break
    return hits


def _env_secret_values() -> list[str]:
    out = []
    for name in ENV_SECRET_VARS:
        value = os.environ.get(name, "")
        if len(value) >= 8:
            out.append(value)
    return out


def is_env_file(path: str) -> bool:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return (name == ".env" or name.startswith(".env.")) and name != ".env.example"


def scan_text(label: str, text: str, env_values: Iterable[str] = ()) -> Iterator[Finding]:
    values = [v for v in env_values if v]
    for no, line in enumerate(text.splitlines(), start=1):
        for rule in scan_line(line):
            yield Finding(f"{label}:{no}", rule)
        if values and ALLOW_PRAGMA not in line and any(v in line for v in values):
            yield Finding(f"{label}:{no}", "env-secret-value")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed (rc={proc.returncode})")
    return proc.stdout


def tracked_files(root: Path) -> list[str]:
    """Tracked plus untracked-but-not-ignored files (a leak is caught before ``git add``)."""
    out = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted({p for p in out.split("\0") if p})


def scan_worktree(root: Path, env_values: Iterable[str] = ()) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    scanned = 0
    values = list(env_values)
    for rel in tracked_files(root):
        if is_env_file(rel):
            findings.append(Finding(f"{rel}:0", "env-file"))
        if rel.lower().endswith(SKIP_EXT):
            continue
        path = root / rel
        try:
            if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue  # binary
        scanned += 1
        findings.extend(scan_text(rel, data.decode("utf-8", errors="replace"), values))
    return findings, scanned


def scan_history(
    root: Path,
    max_commits: int,
    env_values: Iterable[str] = (),
    allow: frozenset[AllowEntry] = frozenset(),
    suppressed: list[Finding] | None = None,
) -> tuple[list[Finding], int]:
    """Added lines of every commit on every ref (newest ``max_commits``); one finding per commit/file/rule.

    Findings whose exact (full sha, path, rule) fingerprint is in ``allow`` go to ``suppressed`` instead.
    """
    log = _git(root, "log", "--all", "-p", "--no-color", "-U0", "--no-ext-diff", f"--max-count={max_commits}",
               "--format=commit %H")  # fmt: skip
    values = [v for v in env_values if v]
    seen: set[Finding] = set()
    findings: list[Finding] = []
    commit = ""
    path = ""
    commits = 0

    def add(rule: str) -> None:
        f = Finding(f"{commit[:12]}:{path}", rule)
        if f in seen:
            return
        seen.add(f)
        if is_allowed(commit, path, rule, allow):
            if suppressed is not None:
                suppressed.append(f)
        else:
            findings.append(f)

    for raw in log.splitlines():
        if raw.startswith("commit ") and len(raw) == 47:
            commit, commits = raw[7:47], commits + 1
            continue
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else raw[4:]
            if is_env_file(path):
                add("env-file")
            continue
        if not raw.startswith("+") or path.lower().endswith(SKIP_EXT):
            continue
        line = raw[1:]
        rules = scan_line(line)
        if values and ALLOW_PRAGMA not in line and any(v in line for v in values):
            rules.append("env-secret-value")
        for rule in rules:
            add(rule)
    return findings, commits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--history", action="store_true", help="also scan added lines of the git history")
    ap.add_argument("--max-commits", type=int, default=5000)
    ap.add_argument("--json", dest="json_out", help="write findings as JSON (locations + rule ids only)")
    ap.add_argument("--allowlist", default=str(ALLOWLIST_FILE), help="history allowlist (exact fingerprints)")
    args = ap.parse_args(argv)
    root = Path(args.root)
    env_values = _env_secret_values()
    suppressed: list[Finding] = []
    try:
        allow = load_allowlist(Path(args.allowlist))
        tree, scanned = scan_worktree(root, env_values)
        hist, commits = (
            scan_history(root, args.max_commits, env_values, allow, suppressed) if args.history else ([], 0)
        )
    except (RuntimeError, ValueError) as exc:
        print(f"secret_scan: {exc}", file=sys.stderr)
        return 2
    print(
        f"secret_scan: rules={len(RULE_IDS)} text_files={scanned} (tracked + untracked non-ignored) "
        f"env_values_checked={len(env_values)}"
    )
    if args.history:
        print(f"secret_scan: history commits scanned={commits} (max {args.max_commits})")
        print(f"secret_scan: history allowlist entries={len(allow)} suppressed={len(suppressed)}")
        for f in suppressed:
            print(f"ALLOWLISTED history {f.where} {f.rule}")
    else:
        print("secret_scan: history scan skipped (pass --history)")
    for f in tree:
        print(f"FINDING worktree {f.where} {f.rule}")
    for f in hist:
        print(f"FINDING history {f.where} {f.rule}")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "tracked_text_files": scanned,
                    "history_commits": commits,
                    "worktree": [asdict(f) for f in tree],
                    "history": [asdict(f) for f in hist],
                    "history_allowlisted": [asdict(f) for f in suppressed],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    total = len(tree) + len(hist)
    print(f"secret_scan: findings={total} -> {'FAIL' if total else 'PASS'}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
