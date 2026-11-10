# CI summary

Commit `e3d56a03a4a08dfe3557dffd14687be4787449b5` | machine work-windows | 2026-11-10T18:28:39Z

Worktree at the end of the run: 12 modified tracked file(s), 4 untracked path(s) (0/0 = exactly the commit above).

Tested code (git tree id of the worktree per directory; compare with `git rev-parse <commit>:<dir>`):

- `backend` 6153515b7952e5c4e84d0c8e733e575d65997dd6
- `frontend` ac7654d1d80080e79bf3889cf5ecf83351e140c3
- `tools` b3901ca2f5061ce6fbab0fa0f460b3b87d44b63a
- `ops` 4cbdc49093229426f8d69e58784b2e213a628d20
- `docs` cd60003abb7f76bb3440f7d81226b5a7b255a485
- `.github` 798f6bcddc477151f91f7800ebad754161f6d610

| Stage | Result | Exit code | Seconds | Log | Skip reason |
|---|---|---|---|---|---|
| lint | PASS | 0 | 1 | 01_lint.log |  |
| type | PASS | 0 | 3 | 02_type.log |  |
| tools | PASS | 0 | 2 | 03_tools.log |  |
| unit | PASS | 0 | 190 | 04_unit.log |  |
| migration | PASS | 0 | 133 | 05_migration.log |  |
| contract | PASS | 0 | 27 | 06_contract.log |  |
| authz | PASS | 0 | 26 | 07_authz.log |  |
| frontend | PASS | 0 | 152 | 08_frontend.log |  |
| e2e | PASS | 0 | 180 | 09_e2e.log |  |
| perf | PASS | 0 | 123 | 10_perf.log |  |
| security | PASS | 0 | 143 | 11_security.log |  |
| ops | PASS | 0 | 209 | 12_ops.log |  |
| artifacts | PASS | 0 | 7 | 13_artifacts.log |  |
