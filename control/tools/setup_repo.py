#!/usr/bin/env python3
"""Cross-platform (Windows / Ubuntu) setup for the Aleekhan development repo.

First machine (creates the repo):
    python setup_repo.py new   --handoff <ALEEKHAN_MASTER_HANDOFF_V1 dir> --repo <new repo dir> [--remote <git url>]
Second machine (clone of the shared repo):
    python setup_repo.py clone --remote <git url> --repo <dir>
Re-install hooks only (e.g. after a fresh clone made by hand):
    python setup_repo.py hooks --repo <dir>

Only documentation is copied: 09_PRIVATE_FACTORY_SOURCES is never copied into the repo.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
KIT_ITEMS = [".claude", "control", "CLAUDE.md", ".gitignore", ".gitattributes", "README_FA.md"]
HOOK = """#!/bin/sh
# Aleekhan guard: blocks private/source files and secrets (works with Git for Windows and Linux)
for p in python3 python "py -3"; do
  if $p -c "import sys" >/dev/null 2>&1; then exec $p control/tools/precommit_guard.py; fi
done
echo "precommit: python not found"; exit 1
"""


def run(cmd, cwd=None, check=True):
    print("  $", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=cwd, check=check)


def need_git():
    if not shutil.which("git"):
        sys.exit("git not found. Windows: install 'Git for Windows'; Ubuntu: sudo apt install git")


def install_hook(repo: Path):
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(HOOK, encoding="utf-8", newline="\n")
    try:
        hook.chmod(0o755)
    except OSError:
        pass
    print(f"  pre-commit guard installed: {hook}")


def ignore_private(_dir, names):
    return [n for n in names if n == "09_PRIVATE_FACTORY_SOURCES" or n == "__pycache__"]


def cmd_new(a):
    need_git()
    handoff = Path(a.handoff).resolve()
    repo = Path(a.repo).resolve()
    if not (handoff / "AGENTS.md").exists():
        sys.exit(f"not a handoff folder (AGENTS.md missing): {handoff}")
    if (repo / ".git").exists():
        sys.exit(f"{repo} is already a git repo; use 'hooks' or work in it directly")
    repo.mkdir(parents=True, exist_ok=True)
    print("1) copying kit")
    for item in KIT_ITEMS:
        src = KIT / item
        if src.is_dir():
            shutil.copytree(src, repo / item, dirs_exist_ok=True, ignore=ignore_private)
        elif src.exists():
            shutil.copy2(src, repo / item)
    print("2) copying handoff docs (without 09_PRIVATE_FACTORY_SOURCES)")
    shutil.copytree(handoff, repo / "handoff", dirs_exist_ok=True, ignore=ignore_private)
    (repo / "reports").mkdir(exist_ok=True)
    (repo / "reports" / ".keep").write_text("", encoding="utf-8")
    print("3) git init + status")
    run(["git", "init", "-q", "-b", "main"], cwd=repo)
    install_hook(repo)
    run([sys.executable, "control/tools/status.py", "init", "--handoff", "handoff/"], cwd=repo)
    run([sys.executable, "control/tools/status.py", "render"], cwd=repo)
    run(["git", "add", "-A"], cwd=repo)
    run(["git", "commit", "-qm", "[PHASE_00][setup] control kit + handoff v1.0 docs (no private sources)"], cwd=repo)
    if a.remote:
        print("4) pushing to shared remote")
        run(["git", "remote", "add", "origin", a.remote], cwd=repo)
        run(["git", "push", "-u", "origin", "main"], cwd=repo)
    print(f"\nDONE: {repo}")
    print_env_help()


def cmd_clone(a):
    need_git()
    repo = Path(a.repo).resolve()
    run(["git", "clone", a.remote, str(repo)])
    install_hook(repo)
    run([sys.executable, "control/tools/status.py", "brief"], cwd=repo)
    print(f"\nDONE: {repo}")
    print_env_help()


def cmd_hooks(a):
    install_hook(Path(a.repo).resolve())


def print_env_help():
    print("""
Next (set once per machine):
  Windows PowerShell:
    setx ALEEKHAN_MACHINE "work-windows"
    setx ALEEKHAN_PRIVATE_DIR "D:\\aleekhan-private"      # only on a machine allowed to hold private files
    # password: set it only for the current window, not permanently:
    $env:ALEEKHAN_SRC_PASSWORD = Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText
  Ubuntu (~/.bashrc):
    export ALEEKHAN_MACHINE=home-ubuntu
    export ALEEKHAN_PRIVATE_DIR=$HOME/aleekhan-private    # only if allowed (DEC-028)
    read -rs ALEEKHAN_SRC_PASSWORD; export ALEEKHAN_SRC_PASSWORD
Then:  cd <repo>  ->  claude  ->  /kickoff   (first machine)   or   /sync  (other machine)
""")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("new"); x.add_argument("--handoff", required=True); x.add_argument("--repo", required=True); x.add_argument("--remote"); x.set_defaults(f=cmd_new)
    x = sub.add_parser("clone"); x.add_argument("--remote", required=True); x.add_argument("--repo", required=True); x.set_defaults(f=cmd_clone)
    x = sub.add_parser("hooks"); x.add_argument("--repo", required=True); x.set_defaults(f=cmd_hooks)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
