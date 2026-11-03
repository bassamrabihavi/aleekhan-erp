import { QueryClient } from "@tanstack/react-query";

/**
 * retry: false  - a failed probe is shown at once (with its request id) instead of being hidden by retries.
 * networkMode "always" - queries run even when the browser reports offline, so the real failure is shown.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        networkMode: "always",
        refetchOnWindowFocus: true,
        staleTime: 0,
      },
    },
  });
}
