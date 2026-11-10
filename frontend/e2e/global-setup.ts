// Seed of the throw-away E2E database (scripts/e2e.sh created and migrated it): the first owner through the
// real console bootstrap command (password on stdin, never an argument, never printed) and synthetic job runs
// for page 36. Synthetic data only; the database is dropped after the run.
import { manage, OWNER_USERNAME, SYN_LABEL, SYN_PW_OWNER_ONE_TIME } from "./phase01-helpers";

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
