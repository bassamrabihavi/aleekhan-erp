// Minimal hash router (no new dependency): "#/security/users" -> "/security/users". Hash routing keeps the
// Vite dev server and any static host free of server-side rewrites.
import { useSyncExternalStore } from "react";

function current(): string {
  const h = window.location.hash.replace(/^#/, "");
  return h.startsWith("/") ? h : "/";
}

function subscribe(cb: () => void): () => void {
  window.addEventListener("hashchange", cb);
  return () => {
    window.removeEventListener("hashchange", cb);
  };
}

export function useRoute(): string {
  return useSyncExternalStore(subscribe, current, () => "/");
}

export function navigate(path: string): void {
  window.location.hash = `#${path}`;
}

/** "/documents/abc" with prefix "/documents" -> ["abc"]. */
export function segments(route: string, prefix: string): string[] {
  if (route !== prefix && !route.startsWith(`${prefix}/`)) return [];
  return route
    .slice(prefix.length)
    .split("/")
    .filter(Boolean)
    .map((s) => decodeURIComponent(s));
}
