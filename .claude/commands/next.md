---
description: ادامه کار — اجرای حلقه گام‌ها تا رسیدن به Gate، مانع، یا سقف تعداد گام (مثال: /next 3)
argument-hint: "[max steps, default 1]"
---
Before the loop (multi-machine protocol, see CLAUDE.md): `git pull --rebase`; `status.py lock acquire --note "next $ARGUMENTS"` (if REFUSED: stop and tell the employer which machine is working); commit+push the lock.
Run the loop defined in CLAUDE.md ("The loop") for at most $ARGUMENTS steps (default 1 if empty).
Rules: implement via `aleekhan-implementer`, verify yourself, review via `aleekhan-reviewer`, update status only through `control/tools/status.py`. Stop early at: Gate pending, P0 blocker, 3 rework cycles, failing environment, or any action that needs employer authority.
After every PASSED step: commit and `git push` (so the other machine sees progress). At the end: `status.py lock release`, commit, push. Finish with `python3 control/tools/status.py render` and the Persian report block from CLAUDE.md.
