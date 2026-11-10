// Auth context object, state type and hook (kept apart from the provider component for fast refresh).
import { createContext, useContext } from "react";

import type { Me } from "../api/phase01";

export type AuthStatus =
  | "loading"
  | "anonymous"
  | "mfa_pending"
  | "password_change"
  | "mfa_enrolment"
  | "ready"
  | "boot_error";

export interface AuthState {
  status: AuthStatus;
  me: Me | null;
  permissions: ReadonlySet<string>;
  /** Persian notice shown on the login screen (e.g. the session ended). */
  notice: string | null;
  bootError: unknown;
  can: (action: string) => boolean;
  canAny: (actions: readonly string[]) => boolean;
  /** Roles through which the caller holds ``action`` (``via_role`` of GET /me/permissions). */
  rolesFor: (action: string) => ReadonlySet<string>;
  refresh: (notice?: string | null) => Promise<void>;
  logout: () => Promise<void>;
  /** Opens the MFA step-up dialog; resolves after a successful verification, rejects when cancelled. */
  requireStepUp: () => Promise<void>;
}

export const AuthCtx = createContext<AuthState | null>(null);

export const SESSION_ENDED_NOTICE =
  "جلسه شما پایان یافته است (بی‌کاری، پایان مهلت یا ابطال). لطفاً دوباره وارد شوید.";

export function useAuth(): AuthState {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
