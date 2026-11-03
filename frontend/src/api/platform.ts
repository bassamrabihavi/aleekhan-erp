// PHASE_00 platform endpoints (docs/discovery/MOCK_UI_BINDING.md §5).
import { getJson } from "./client";
import { isAccessDecision, isLiveness, isReadiness, isVersionInfo } from "./guards";
import type { AccessDecision, Liveness, Readiness, VersionInfo } from "./types";

export const fetchLiveness = (signal?: AbortSignal): Promise<Liveness> =>
  getJson("/health/live", { signal, guard: isLiveness });

/** 503 + `not_ready` is a valid readiness answer, not a transport error. */
export const fetchReadiness = (signal?: AbortSignal): Promise<Readiness> =>
  getJson("/health/ready", { signal, guard: isReadiness, acceptStatuses: [503] });

export const fetchVersion = (signal?: AbortSignal): Promise<VersionInfo> =>
  getJson("/version", { signal, guard: isVersionInfo });

/** Action id checked by the access-gate demo. PHASE_00 has no authentication: the real answer is 401. */
export const STATUS_VIEW_ACTION = "platform.status.view";

export const fetchAccessCheck = (signal?: AbortSignal): Promise<AccessDecision> =>
  getJson(`/access-gate/check?action=${encodeURIComponent(STATUS_VIEW_ACTION)}`, {
    signal,
    guard: isAccessDecision,
  });
