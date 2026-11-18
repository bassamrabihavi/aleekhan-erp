// Navigation catalogue (role-aware: an item is shown when any of its actions is granted - cosmetic only, the
// server re-checks every call) and the shared /version query.
import { useQuery } from "@tanstack/react-query";

import { DECIDE_PERMS, PERM } from "../api/phase02";
import type { IconName } from "../components/Icon";
import { fetchVersion } from "../api/platform";

export interface NavItem {
  path: string;
  label: string;
  /** Page number of the DRAFT catalog (UI_PAGE_PHASE_MAP.csv), if any. */
  page?: number;
  /** Shown when any of these actions is granted (cosmetic: the server re-checks every call). */
  anyOf?: readonly string[];
  /** Side-menu icon (DEC-061 icon rail). */
  icon: IconName;
}

export const NAV: readonly NavItem[] = [
  { path: "/", label: "پیشخوان", icon: "home" },
  {
    path: "/work",
    label: "کارها و تأییدها",
    icon: "tasks",
    page: 39,
    anyOf: ["platform.workflow.task.read", "platform.workflow.approval.read", ...DECIDE_PERMS],
  },
  // PHASE_02 (02.5)
  { path: "/serials", label: "مرکز کنترل سریال", icon: "serial", page: 1, anyOf: [PERM.serialRead] },
  { path: "/orders", label: "ثبت سفارش و کدگذاری", icon: "order", page: 29, anyOf: [PERM.orderRead] },
  // REV-0295: shortcut to the order wizard (page 29 «ثبت سفارش جدید»), only for users who may create orders
  { path: "/orders/new", label: "ثبت سفارش جدید", icon: "orderNew", page: 29, anyOf: [PERM.orderManage] },
  { path: "/changes", label: "تغییرات سفارش", icon: "change", page: 33, anyOf: [PERM.changeRead] },
  { path: "/products", label: "محصولات و استایل‌ها", icon: "product", page: 4, anyOf: [PERM.productRead] },
  { path: "/customers", label: "مشتریان و برندها", icon: "customers", anyOf: [PERM.customerRead] },
  { path: "/code-rules", label: "قاعده کد ۱۴رقمی", icon: "code", anyOf: [PERM.ruleRead] },
  { path: "/documents", label: "اسناد", icon: "documents", page: 40, anyOf: ["platform.document.read"] },
  { path: "/org", label: "درخت سازمانی", icon: "org", anyOf: ["platform.org.read"] },
  {
    path: "/security",
    label: "امنیت و کاربران",
    icon: "security",
    page: 46,
    anyOf: [
      "platform.identity.user.read",
      "platform.identity.role.read",
      "platform.identity.assignment.read",
    ],
  },
  { path: "/parameters", label: "پارامترها", icon: "parameters", page: 42, anyOf: ["platform.config.parameter.read"] },
  {
    path: "/ops",
    label: "سلامت سامانه و Job",
    icon: "ops",
    page: 36,
    anyOf: ["platform.ops.health.read", "platform.ops.job.read", "platform.audit.integrity.read"],
  },
  { path: "/me/sessions", label: "جلسه‌های من", icon: "sessions" },
  { path: "/status", label: "وضعیت زیرساخت", icon: "status" },
];

export function useVersion() {
  return useQuery({ queryKey: ["platform", "version"], queryFn: ({ signal }) => fetchVersion(signal), staleTime: 300_000 });
}
