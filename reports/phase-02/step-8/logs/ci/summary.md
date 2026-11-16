# CI summary

Commit `91b921ab3d23603abb93ce9916196a00e3e85631` | machine work-windows | 2026-11-16T06:18:21Z

Worktree at the end of the run: 1 modified tracked file(s), 5 untracked path(s) (0/0 = exactly the commit above).

Tested code (git tree id of the worktree per directory; compare with `git rev-parse <commit>:<dir>`):

- `backend` 7d603803a804837d81477323e7739c39ec3ac91d
- `frontend` ae7a29f51d9de1b7dc4d59e45e5c0c5060f46f10
- `tools` 08bc3f04c9af60cd94167287d72e59d2a04ae3f1
- `ops` 0da067a1e36f7a26f0109a1ed10de74da9d99d8b
- `docs` e6bccd211fc0c53369cbb78fd1205819ebf696de
- `.github` 798f6bcddc477151f91f7800ebad754161f6d610

| Stage | Result | Exit code | Seconds | Log | Skip reason |
|---|---|---|---|---|---|
| lint | PASS | 0 | 2 | 01_lint.log |  |
| type | PASS | 0 | 3 | 02_type.log |  |
| tools | PASS | 0 | 3 | 03_tools.log |  |
| unit | PASS | 0 | 586 | 04_unit.log |  |
| migration | PASS | 0 | 346 | 05_migration.log |  |
| contract | PASS | 0 | 62 | 06_contract.log |  |
| authz | PASS | 0 | 62 | 07_authz.log |  |
| security | PASS | 0 | 125 | 11_security.log |  |
| ops | PASS | 0 | 804 | 12_ops.log |  |
| artifacts | PASS | 0 | 9 | 13_artifacts.log |  |
| frontend | PASS | 0 | 167 | 08_frontend.log |  |
| e2e | PASS | 0 | 399 | 09_e2e.log |  |
| perf | PASS | 0 | 284 | 10_perf.log |  |
