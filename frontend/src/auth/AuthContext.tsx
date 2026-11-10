// Session state of the shell (MOCK_UI_BINDING §6.0). The server is the authority: the state is always derived
// from GET /auth/session, GET /me and GET /me/permissions; the permission set only hides navigation
// (cosmetic) - every action is re-checked by the backend.
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { AUTH_LOST_EVENT } from "../api/http";
import { auth, type Me } from "../api/phase01";
import { AuthCtx as Ctx, SESSION_ENDED_NOTICE, type AuthState, type AuthStatus } from "./context";
import { StepUpDialog } from "./StepUpDialog";


export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [permissions, setPermissions] = useState<ReadonlySet<string>>(new Set());
  const [viaRoles, setViaRoles] = useState<ReadonlyMap<string, ReadonlySet<string>>>(new Map());
  const [notice, setNotice] = useState<string | null>(null);
  const [bootError, setBootError] = useState<unknown>(null);
  const [stepUp, setStepUp] = useState<{ resolve: () => void; reject: (e: unknown) => void } | null>(null);
  const statusRef = useRef(status);
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  /** Session data is dropped on sign-out / session end; public probes (["platform", …]) are kept. */
  const dropPrivateData = useCallback(() => {
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "platform" });
  }, [qc]);

  const resolveState = useCallback(
    async (nextNotice: string | null = null) => {
      setBootError(null);
      try {
        await auth.session();
      } catch (e) {
        setMe(null);
        setPermissions(new Set());
        setViaRoles(new Map());
        if (e instanceof ApiError && e.code === "MFA_REQUIRED") {
          setStatus("mfa_pending");
          return;
        }
        if (e instanceof ApiError && e.kind === "problem" && e.status === 401) {
          dropPrivateData();
          setNotice(nextNotice);
          setStatus("anonymous");
          return;
        }
        setBootError(e);
        setStatus("boot_error");
        return;
      }
      try {
        const m = (await auth.me()).data;
        setMe(m);
        if (m.user.mfa_required && !m.user.mfa_enrolled) {
          setStatus("mfa_enrolment");
          return;
        }
        const p = (await auth.myPermissions()).data;
        setPermissions(new Set(p.grants.map((g) => g.action)));
        const via = new Map<string, Set<string>>();
        for (const g of p.grants) {
          const set = via.get(g.action) ?? new Set<string>();
          set.add(g.via_role);
          via.set(g.action, set);
        }
        setViaRoles(via);
        setNotice(null);
        setStatus("ready");
      } catch (e) {
        if (e instanceof ApiError && e.code === "PASSWORD_CHANGE_REQUIRED") {
          setStatus("password_change");
          return;
        }
        if (e instanceof ApiError && e.kind === "problem" && e.status === 401) {
          dropPrivateData();
          setNotice(nextNotice);
          setStatus(e.code === "MFA_REQUIRED" ? "mfa_pending" : "anonymous");
          return;
        }
        setBootError(e);
        setStatus("boot_error");
      }
    },
    [dropPrivateData],
  );

  useEffect(() => {
    // first resolution after mount; deferred so no state is set synchronously inside the effect
    const id = window.setTimeout(() => {
      void resolveState();
    }, 0);
    return () => {
      window.clearTimeout(id);
    };
  }, [resolveState]);

  useEffect(() => {
    function onLost(ev: Event): void {
      const code = (ev as CustomEvent<string>).detail;
      if (statusRef.current !== "ready") return;
      void resolveState(code === "AUTHENTICATION_REQUIRED" ? SESSION_ENDED_NOTICE : null);
    }
    window.addEventListener(AUTH_LOST_EVENT, onLost);
    return () => {
      window.removeEventListener(AUTH_LOST_EVENT, onLost);
    };
  }, [resolveState]);

  const logout = useCallback(async () => {
    try {
      await auth.logout();
    } catch {
      // the session may already be gone; the state below is read from the server anyway
    }
    dropPrivateData();
    await resolveState("از سامانه خارج شدید.");
  }, [dropPrivateData, resolveState]);

  const requireStepUp = useCallback(
    () =>
      new Promise<void>((resolve, reject) => {
        setStepUp({ resolve, reject });
      }),
    [],
  );

  const value = useMemo<AuthState>(() => {
    return {
      status,
      me,
      permissions,
      notice,
      bootError,
      can: (a) => permissions.has(a),
      canAny: (as) => as.some((a) => permissions.has(a)),
      rolesFor: (a) => viaRoles.get(a) ?? new Set<string>(),
      refresh: resolveState,
      logout,
      requireStepUp,
    };
  }, [status, me, permissions, viaRoles, notice, bootError, resolveState, logout, requireStepUp]);

  return (
    <Ctx.Provider value={value}>
      {children}
      {stepUp ? (
        <StepUpDialog
          onDone={() => {
            stepUp.resolve();
            setStepUp(null);
          }}
          onCancel={() => {
            stepUp.reject(
              new ApiError({
                kind: "problem",
                status: 401,
                code: "MFA_REQUIRED",
                messageFa: "تأیید دومرحله‌ای انجام نشد؛ اقدام اجرا نشد.",
              }),
            );
            setStepUp(null);
          }}
        />
      ) : null}
    </Ctx.Provider>
  );
}
