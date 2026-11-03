// Minimal runtime checks of API responses against the contract (docs/api/openapi-draft.yaml). A body that
// does not match is rejected and shown as an error - it is never rendered as if it were valid data.
import type { AccessDecision, ComponentStatus, Liveness, Problem, Readiness, VersionInfo } from "./types";

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";

const COMPONENT_NAMES = new Set(["database", "migrations", "cache", "object_storage", "worker"]);
const COMPONENT_STATES = new Set(["up", "down", "unknown"]);
const ENVIRONMENTS = new Set(["dev", "test", "staging", "production"]);
const UTC_TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;
const COMMIT = /^[0-9a-f]{7,40}$/;

export function isLiveness(v: unknown): v is Liveness {
  return isObj(v) && v.status === "ok";
}

function isComponent(v: unknown): v is ComponentStatus {
  return (
    isObj(v) && isStr(v.name) && COMPONENT_NAMES.has(v.name) && isStr(v.status) && COMPONENT_STATES.has(v.status)
  );
}

export function isReadiness(v: unknown): v is Readiness {
  return (
    isObj(v) &&
    (v.status === "ready" || v.status === "not_ready") &&
    isStr(v.checked_at) &&
    UTC_TS.test(v.checked_at) &&
    Array.isArray(v.components) &&
    v.components.length <= 16 &&
    v.components.every(isComponent)
  );
}

export function isVersionInfo(v: unknown): v is VersionInfo {
  return (
    isObj(v) &&
    v.api_version === "v1" &&
    isStr(v.contract_version) &&
    isStr(v.build_commit) &&
    COMMIT.test(v.build_commit) &&
    isStr(v.environment) &&
    ENVIRONMENTS.has(v.environment)
  );
}

export function isAccessDecision(v: unknown): v is AccessDecision {
  return (
    isObj(v) &&
    (v.decision === "ALLOW" || v.decision === "DENY") &&
    isStr(v.reason_code) &&
    isStr(v.action) &&
    isStr(v.request_id)
  );
}

export function isProblem(v: unknown): v is Problem {
  return isObj(v) && isStr(v.code) && typeof v.status === "number" && isStr(v.request_id);
}
