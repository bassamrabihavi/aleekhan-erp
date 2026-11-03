// Response shapes of docs/api/openapi-draft.yaml (0.3.0-draft), PHASE_00 platform endpoints only.

export interface Liveness {
  status: "ok";
}

export type ComponentName = "database" | "migrations" | "cache" | "object_storage" | "worker";
export type ComponentState = "up" | "down" | "unknown";

export interface ComponentStatus {
  name: ComponentName;
  status: ComponentState;
}

export interface Readiness {
  status: "ready" | "not_ready";
  /** RFC 3339 UTC timestamp (server clock). */
  checked_at: string;
  components: ComponentStatus[];
}

export type EnvironmentName = "dev" | "test" | "staging" | "production";

export interface VersionInfo {
  api_version: "v1";
  contract_version: string;
  build_commit: string;
  environment: EnvironmentName;
}

export type AccessDecisionValue = "ALLOW" | "DENY";

export interface AccessDecision {
  decision: AccessDecisionValue;
  reason_code: string;
  action: string;
  decision_id?: string | null;
  request_id: string;
}

/** RFC 9457 problem + Aleekhan stable fields (`code`, `message_fa`, `request_id`). */
export interface Problem {
  type: string;
  title: string;
  status: number;
  code: string;
  message_fa?: string;
  detail?: string;
  request_id: string;
  decision_id?: string;
}
