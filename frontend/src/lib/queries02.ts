// Shared PHASE_02 queries of the 02.5 pages.
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { g, get, K2, PERM, type Customer } from "../api/phase02";
import { useAuth } from "../auth/context";

/** Customer id -> name (first 100 customers; only for holders of identity.customer.read). */
export function useCustomerNames(): Map<string, Customer> {
  const { can } = useAuth();
  const q = useQuery({
    queryKey: [...K2.customers, "names"],
    enabled: can(PERM.customerRead),
    queryFn: async ({ signal }) => (await get("/identity/customers", g.customerPage, { page_size: 100 }, signal)).data,
    staleTime: 60_000,
  });
  return new Map((q.data?.items ?? []).map((c) => [c.customer_id, c]));
}


/** True when an action failed with the PHASE_02 refusal reason ``code`` (errors[].code). */
export function hasReason(error: unknown, code: string): boolean {
  return error instanceof ApiError && error.fieldErrors.some((f) => f.code === code);
}
