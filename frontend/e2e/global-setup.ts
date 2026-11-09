// Seed of the throw-away E2E database (scripts/e2e.sh created and migrated it): the first owner through the
// real console bootstrap command (password on stdin, never an argument, never printed) and synthetic job runs
// for page 36. Synthetic data only; the database is dropped after the run.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { OWNER_USERNAME, SYN_LABEL, SYN_PW_OWNER_ONE_TIME } from "./phase01-helpers";

const here = path.dirname(fileURLToPath(import.meta.url));
const backendDir = path.resolve(here, "../../backend");

function manage(args: string[], input?: string): void {
  const python = process.env.E2E_PYTHON;
  if (!python) throw new Error("E2E_PYTHON not set (run through scripts/e2e.sh)");
  const r = spawnSync(python, ["manage.py", ...args], { cwd: backendDir, input, encoding: "utf8", env: process.env });
  if (r.status !== 0) throw new Error(`manage.py ${args[0] ?? ""} failed (exit ${String(r.status)}): ${r.stderr.slice(-400)}`);
}

const SEED_JOBS = `
from platform_core.engine.context import Actor, RequestContext
from platform_core.jobs import service as jobs
ctx = RequestContext(Actor.system())
jobs.enqueue(ctx, job_type="session_expiry_sweep", task_key="syn-e2e-queued-sweep")
jobs.enqueue(ctx, job_type="db_backup", task_key="syn-e2e-protected-backup")
jobs.run_job("audit_integrity_check", task_key="syn-e2e-integrity")
print("seeded synthetic job runs")
`;

export default function globalSetup(): void {
  if (process.env.E2E_MODE === "backend-down") return;
  manage(
    ["bootstrap_owner", "--username", OWNER_USERNAME, "--display-name", `مالک ساختگی (${SYN_LABEL})`, "--reason", "E2E synthetic owner (01.5)", "--password-stdin"],
    `${SYN_PW_OWNER_ONE_TIME}\n`,
  );
  manage(["shell", "-c", SEED_JOBS]);
}
