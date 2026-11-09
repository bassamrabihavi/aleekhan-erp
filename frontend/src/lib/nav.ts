// Navigation catalogue (role-aware: an item is shown when any of its actions is granted - cosmetic only, the
// server re-checks every call) and the shared /version query.
import { useQuery } from "@tanstack/react-query";

import { fetchVersion } from "../api/platform";

export interface NavItem {
  path: string;
  label: string;
  /** Page number of the DRAFT catalog (UI_PAGE_PHASE_MAP.csv), if any. */
  page?: number;
  /** Shown when any of these actions is granted (cosmetic: the server re-checks every call). */
  anyOf?: readonly string[];
}

export const NAV: readonly NavItem[] = [
  { path: "/", label: "پیشخوان" },
  {
    path: "/work",
    label: "کارها و تأییدها",
    page: 39,
    anyOf: ["platform.workflow.task.read", "platform.workflow.approval.read"],
  },
  { path: "/documents", label: "اسناد", page: 40, anyOf: ["platform.document.read"] },
  { path: "/org", label: "درخت سازمانی", anyOf: ["platform.org.read"] },
  {
    path: "/security",
    label: "امنیت و کاربران",
    page: 46,
    anyOf: [
      "platform.identity.user.read",
      "platform.identity.role.read",
      "platform.identity.assignment.read",
    ],
  },
  { path: "/parameters", label: "پارامترها", page: 42, anyOf: ["platform.config.parameter.read"] },
  {
    path: "/ops",
    label: "سلامت سامانه و Job",
    page: 36,
    anyOf: ["platform.ops.health.read", "platform.ops.job.read", "platform.audit.integrity.read"],
  },
  { path: "/me/sessions", label: "جلسه‌های من" },
  { path: "/status", label: "وضعیت زیرساخت" },
];

export function useVersion() {
  return useQuery({ queryKey: ["platform", "version"], queryFn: ({ signal }) => fetchVersion(signal), staleTime: 300_000 });
}
