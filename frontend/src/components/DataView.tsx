// Uniform loading / error / forbidden / empty / stale rendering of one query (UI_HANDOFF_INSTRUCTIONS_FA).
import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import { useNow } from "../lib/hooks";
import { EmptyState, ErrorState, LoadingState, StaleBadge } from "./States";

/** Data older than this (since the last successful answer) is flagged stale. */
export const STALE_AFTER_MS = 120_000;

interface Props<T> {
  query: UseQueryResult<T>;
  loading: string;
  errorTitle: string;
  isEmpty?: (data: T) => boolean;
  empty?: { title: string; hint?: string | undefined };
  children: (data: T) => ReactNode;
}

export function ForbiddenState({ error }: { error?: unknown }) {
  const e = error instanceof ApiError ? error : null;
  return (
    <div className="state state--forbidden" data-testid="state-forbidden" role="status">
      <p className="state__title">به این بخش دسترسی ندارید.</p>
      <p className="state__hint">
        سرور این درخواست را برای نقش‌های شما رد کرد. اگر لازم است، از مالک سامانه بخواهید نقش مناسب را انتساب دهد.
      </p>
      {e?.requestId ? (
        <p className="state__hint">
          کد خطا <code dir="ltr">{e.code}</code> · شناسه درخواست <code dir="ltr">{e.requestId}</code>
        </p>
      ) : null}
    </div>
  );
}

export function DataView<T>({ query, loading, errorTitle, isEmpty, empty, children }: Props<T>) {
  const now = useNow(5000);
  if (query.isPending) return <LoadingState label={loading} />;
  if (query.isError && query.data === undefined) {
    const e = query.error;
    if (e instanceof ApiError && e.kind === "problem" && (e.status === 403 || e.code === "ACCESS_DENIED")) {
      return <ForbiddenState error={e} />;
    }
    return (
      <ErrorState
        error={e}
        title={errorTitle}
        onRetry={() => void query.refetch()}
        retrying={query.isFetching}
      />
    );
  }
  const data = query.data as T;
  const stale =
    query.isError ? "failed" : now - query.dataUpdatedAt > STALE_AFTER_MS ? "age" : null;
  return (
    <>
      {stale ? <StaleBadge updatedAt={query.dataUpdatedAt} now={now} reason={stale} /> : null}
      {isEmpty?.(data) && empty ? <EmptyState title={empty.title} hint={empty.hint} /> : children(data)}
    </>
  );
}
