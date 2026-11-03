// Queries of the system-status page. Every value shown on the page comes from these real API calls.
import { useQueries, type UseQueryResult } from "@tanstack/react-query";

import { fetchAccessCheck, fetchLiveness, fetchReadiness, fetchVersion } from "../api/platform";
import type { AccessDecision, Liveness, Readiness, VersionInfo } from "../api/types";

/** Auto-refresh period of the operational probes. */
export const REFRESH_INTERVAL_MS = 30_000;
/** Data older than this (by client clock since the last successful answer) is flagged as stale. */
export const STALE_AFTER_MS = 60_000;

export interface SystemStatus {
  readiness: UseQueryResult<Readiness>;
  liveness: UseQueryResult<Liveness>;
  version: UseQueryResult<VersionInfo>;
  access: UseQueryResult<AccessDecision>;
  refetchAll: () => void;
  isFetchingAny: boolean;
}

export function useSystemStatus(): SystemStatus {
  const [readiness, liveness, version, access] = useQueries({
    queries: [
      {
        queryKey: ["platform", "health", "ready"],
        queryFn: ({ signal }) => fetchReadiness(signal),
        refetchInterval: REFRESH_INTERVAL_MS,
      },
      {
        queryKey: ["platform", "health", "live"],
        queryFn: ({ signal }) => fetchLiveness(signal),
        refetchInterval: REFRESH_INTERVAL_MS,
      },
      {
        queryKey: ["platform", "version"],
        queryFn: ({ signal }) => fetchVersion(signal),
      },
      {
        queryKey: ["platform", "access-gate", "check"],
        queryFn: ({ signal }) => fetchAccessCheck(signal),
      },
    ],
  });

  const refetchAll = () => {
    void readiness.refetch();
    void liveness.refetch();
    void version.refetch();
    void access.refetch();
  };

  return {
    readiness,
    liveness,
    version,
    access,
    refetchAll,
    isFetchingAny: readiness.isFetching || liveness.isFetching || version.isFetching || access.isFetching,
  };
}

/** Freshness of a query result: null = fresh (or no data yet). */
export function staleness(
  q: Pick<UseQueryResult, "data" | "isError" | "dataUpdatedAt">,
  now: number,
): "failed" | "age" | null {
  if (q.data === undefined) return null;
  if (q.isError) return "failed";
  if (now - q.dataUpdatedAt > STALE_AFTER_MS) return "age";
  return null;
}
