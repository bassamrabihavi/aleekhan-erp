// Shared query keys and helpers of the PHASE_01 pages.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { guards, orgGuards, read } from "../api/phase01";

export const QK = {
  users: ["admin", "users"] as const,
  roles: ["admin", "roles"] as const,
  permissions: ["admin", "permissions"] as const,
  assignments: ["admin", "role-assignments"] as const,
  org: ["org"] as const,
  work: ["workflow"] as const,
  documents: ["documents"] as const,
  parameters: ["admin", "parameters"] as const,
  ops: ["ops"] as const,
  sessions: ["auth", "sessions"] as const,
};

/** Cursor paging state: a stack of cursors so "previous page" works without server support. */
export function useCursor(): {
  cursor: string | undefined;
  next: (c: string | null) => void;
  prev: () => void;
  reset: () => void;
  depth: number;
} {
  const [stack, setStack] = useState<string[]>([]);
  return {
    cursor: stack[stack.length - 1],
    depth: stack.length,
    next: (c) => {
      if (c) setStack((s) => [...s, c]);
    },
    prev: () => {
      setStack((s) => s.slice(0, -1));
    },
    reset: () => {
      setStack([]);
    },
  };
}

/** First 100 users (for pickers); enabled only for holders of user.read. */
export function useUserOptions(enabled: boolean) {
  return useQuery({
    queryKey: [...QK.users, "options"],
    enabled,
    queryFn: async ({ signal }) => (await read("/admin/users", guards.userPage, { page_size: 100 }, signal)).data,
  });
}

export function useRoleOptions(enabled: boolean) {
  return useQuery({
    queryKey: [...QK.roles, "options"],
    enabled,
    queryFn: async ({ signal }) => (await read("/admin/roles", guards.rolePage, { page_size: 100 }, signal)).data,
  });
}

export function usePermissionCatalogue(enabled: boolean) {
  return useQuery({
    queryKey: QK.permissions,
    enabled,
    queryFn: async ({ signal }) =>
      (await read("/admin/permissions", guards.permissionPage, { page_size: 100 }, signal)).data,
  });
}

export function useUnitOptions(enabled: boolean) {
  return useQuery({
    queryKey: [...QK.org, "units", "options"],
    enabled,
    queryFn: async ({ signal }) =>
      (await read("/org/units", orgGuards.unitPage, { page_size: 100 }, signal)).data,
  });
}

/** UTC ISO (seconds precision, "Z") of a `datetime-local` value, or null. */
export function localInputToUtc(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function nowUtc(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}
