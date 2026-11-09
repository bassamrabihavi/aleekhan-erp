// One mutating action: a fresh Idempotency-Key per attempt, MFA step-up on 401 MFA_REQUIRED (then one retry),
// query invalidation after success, error kept for <ActionError>.
import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useCallback, useState } from "react";

import { ApiError } from "../api/client";
import { newIdempotencyKey } from "../api/http";
import { useAuth } from "../auth/context";

export interface Action {
  pending: boolean;
  error: unknown;
  reset: () => void;
  run: <T>(fn: (idempotencyKey: string) => Promise<T>, invalidate?: QueryKey[]) => Promise<T | undefined>;
}

export function useAction(): Action {
  const { requireStepUp } = useAuth();
  const qc = useQueryClient();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const run = useCallback(
    async <T,>(fn: (key: string) => Promise<T>, invalidate: QueryKey[] = []): Promise<T | undefined> => {
      setPending(true);
      setError(null);
      try {
        let out: T;
        try {
          out = await fn(newIdempotencyKey());
        } catch (e) {
          if (!(e instanceof ApiError && e.code === "MFA_REQUIRED")) throw e;
          await requireStepUp();
          out = await fn(newIdempotencyKey());
        }
        await Promise.all(invalidate.map((k) => qc.invalidateQueries({ queryKey: k })));
        return out;
      } catch (e) {
        setError(e);
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [qc, requireStepUp],
  );

  return {
    pending,
    error,
    run,
    reset: () => {
      setError(null);
    },
  };
}
