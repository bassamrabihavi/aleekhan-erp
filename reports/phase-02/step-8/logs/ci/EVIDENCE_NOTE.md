# Evidence note (orchestrator, 2026-11-16, REV-0280)

`commit.txt` is the artifact the CI wrote: `68b3362` (HEAD when the artifacts stage ran). It is not edited.
The run was combined over three worktree states; every stage tested code identical to `b3597158` for the part it tests:

| Stages | Worktree / HEAD when run | Tree that matters | Equal in b3597158 |
|---|---|---|---|
| lint, type, tools, unit, migration, contract, authz, security, ops, artifacts | 68b3362 | backend `7d60380` | yes |
| frontend, e2e (re-run) | 91b921a | frontend `ae7a29f`, backend `7d60380` | yes |
| perf (re-run with PHASE_02 perf) | 91b921a + modified `tools/ci_local.sh` (committed as b3597158) | tools `08bc3f0`, backend `7d60380` | yes |

Check: `git rev-parse b3597158:backend` etc. against `summary.md`. From PHASE_03 on, the Gate CI runs once on a clean HEAD.
