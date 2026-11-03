---
description: همگام‌سازی این سیستم (خانه/محل کار) با مخزن مشترک و نمایش وضعیت
---
1. `git status --short`. If there are uncommitted changes from an interrupted session on THIS machine, show them and ask before doing anything.
2. `git pull --rebase` (if it fails with a conflict in `control/PROJECT_STATUS.json`, do NOT hand-merge: take the remote version, then re-apply only this machine's recorded events with `status.py`, and report).
3. Run the status tool (`python3`, or on Windows `python` / `py -3`) with `lock show` and `brief`, then `render`.
4. Report in Persian: which machine holds the work lock, what changed since this machine last synced (`git log --oneline HEAD@{1}..HEAD` if available), and the standard report block from CLAUDE.md. Do not start work.
