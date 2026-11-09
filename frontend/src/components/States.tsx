// Shared loading / error / empty / stale presentations (UI_HANDOFF_INSTRUCTIONS_FA: every page shows them).
import { ApiError, FALLBACK_MESSAGES } from "../api/client";
import { formatAge, formatJalaliDateTime, toFaDigits } from "../lib/format";

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="state state--loading" data-testid="state-loading">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string | undefined }) {
  return (
    <div className="state state--empty" data-testid="state-empty">
      <p className="state__title">{title}</p>
      {hint ? <p className="state__hint">{hint}</p> : null}
    </div>
  );
}

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError({ kind: "network", status: null });
}

interface ErrorProps {
  error: unknown;
  onRetry?: () => void;
  retrying?: boolean;
  /** Title prefix, e.g. "بررسی آمادگی ناموفق بود". */
  title: string;
}

/** Error with the server's Persian message, machine code and request id (for support / log lookup). */
export function ErrorState({ error, onRetry, retrying = false, title }: ErrorProps) {
  const e = asApiError(error);
  return (
    <div className="state state--error" data-testid="state-error">
      <p className="state__title">{title}</p>
      <p className="state__message" data-testid="error-message">
        {e.messageFa || FALLBACK_MESSAGES[e.kind]}
      </p>
      <dl className="meta">
        <div>
          <dt>کد خطا</dt>
          <dd>
            <code dir="ltr" data-testid="error-code">
              {e.code ?? (e.kind === "network" ? "NETWORK" : "CONTRACT")}
            </code>
          </dd>
        </div>
        {e.status !== null ? (
          <div>
            <dt>وضعیت HTTP</dt>
            <dd>{toFaDigits(e.status)}</dd>
          </div>
        ) : null}
        <div>
          <dt>شناسه درخواست</dt>
          <dd>
            {e.requestId ? (
              <code dir="ltr" className="code-id" data-testid="error-request-id">
                {e.requestId}
              </code>
            ) : (
              <span>ثبت نشده (پاسخی از سرور نرسید)</span>
            )}
          </dd>
        </div>
      </dl>
      {onRetry ? (
        <button type="button" className="btn btn--secondary" onClick={onRetry} disabled={retrying}>
          {retrying ? "در حال تلاش…" : "تلاش مجدد"}
        </button>
      ) : null}
    </div>
  );
}

interface StaleProps {
  updatedAt: number;
  now: number;
  reason: "age" | "failed";
}

/** Shown when displayed data is older than the freshness window or the latest refresh failed. */
export function StaleBadge({ updatedAt, now, reason }: StaleProps) {
  return (
    <p className="stale" data-testid="state-stale">
      <strong>داده قدیمی</strong>
      <span>
        {reason === "failed" ? "آخرین بررسی ناموفق بود؛ " : "به‌روزرسانی انجام نشده؛ "}
        آخرین داده موفق: <time dateTime={new Date(updatedAt).toISOString()}>{formatJalaliDateTime(updatedAt)}</time>{" "}
        ({formatAge(updatedAt, now)})
      </span>
    </p>
  );
}
