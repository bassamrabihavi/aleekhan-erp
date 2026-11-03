// "وضعیت سامانه" - PHASE_00 smoke page (CONFLICTS C-16: smoke shell, no business page of the catalog).
// Bindings (MOCK_UI_BINDING §5): readiness chip <- GET /health/ready, liveness <- GET /health/live,
// build/version <- GET /version, no-access demo <- GET /access-gate/check (401 without login in PHASE_00).
import { ApiError } from "../api/client";
import { EmptyState, ErrorState, LoadingState, StaleBadge } from "../components/States";
import { StatusChip } from "../components/StatusChip";
import { formatAge, formatJalaliDateTime, toFaDigits } from "../lib/format";
import { useNow } from "../lib/hooks";
import { COMPONENT_LABELS, COMPONENT_STATE, ENVIRONMENT_LABELS } from "../lib/labels";
import { REFRESH_INTERVAL_MS, staleness, type SystemStatus } from "./useSystemStatus";

function summary(s: SystemStatus): string {
  const r = s.readiness;
  if (r.isPending) return "در حال بررسی وضعیت سامانه…";
  if (r.isError && r.data === undefined) {
    const msg = r.error instanceof ApiError ? r.error.messageFa : "";
    return `بررسی وضعیت سامانه ناموفق بود. ${msg}`;
  }
  if (r.isError) return "آخرین بررسی ناموفق بود؛ وضعیت نمایش‌داده‌شده قدیمی است.";
  return r.data.status === "ready" ? "سامانه آماده است." : "سامانه آماده نیست.";
}

export function SystemStatusPage({ status }: { status: SystemStatus }) {
  const now = useNow(1000);
  const { readiness, liveness, version, access } = status;
  const lastOk = readiness.dataUpdatedAt;
  const readinessStale = staleness(readiness, now);
  const livenessStale = staleness(liveness, now);

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <p className="eyebrow">پایش زیرساخت · فاز ۰</p>
          <h1>وضعیت سامانه</h1>
          <p className="lead">
            وضعیت سرویس‌های پایه مستقیماً از API سامانه خوانده می‌شود؛ این صفحه هیچ داده کسب‌وکاری نمایش نمی‌دهد.
          </p>
        </div>
        <div className="toolbar">
          <button
            type="button"
            className="btn btn--primary"
            onClick={status.refetchAll}
            disabled={status.isFetchingAny}
            aria-describedby="last-checked"
            data-testid="refresh"
          >
            {status.isFetchingAny ? "در حال بررسی…" : "بررسی مجدد"}
          </button>
          <p id="last-checked" className="toolbar__meta" data-testid="last-checked">
            {lastOk > 0 ? (
              <>
                آخرین بررسی موفق:{" "}
                <time dateTime={new Date(lastOk).toISOString()}>{formatJalaliDateTime(lastOk)}</time> (
                {formatAge(lastOk, now)})
              </>
            ) : (
              "هنوز بررسی موفقی ثبت نشده است."
            )}
            <br />
            به‌روزرسانی خودکار هر {toFaDigits(REFRESH_INTERVAL_MS / 1000)} ثانیه
          </p>
        </div>
      </div>

      <div role="status" aria-live="polite" className="sr-only" data-testid="live-region">
        {summary(status)}
      </div>

      <div className="grid">
        <section className="panel panel--wide" aria-labelledby="h-ready" aria-busy={readiness.isFetching}>
          <div className="panel__head">
            <h2 id="h-ready">آمادگی سامانه</h2>
            {readiness.data ? (
              <StatusChip
                testId="ready-chip"
                tone={readiness.data.status === "ready" ? "success" : "danger"}
                label={readiness.data.status === "ready" ? "آماده" : "آماده نیست"}
              />
            ) : null}
          </div>
          {readinessStale ? <StaleBadge updatedAt={lastOk} now={now} reason={readinessStale} /> : null}
          {readiness.isPending ? <LoadingState label="در حال بررسی آمادگی سامانه…" /> : null}
          {readiness.isError ? (
            <ErrorState
              title="بررسی آمادگی ناموفق بود"
              error={readiness.error}
              onRetry={() => void readiness.refetch()}
              retrying={readiness.isFetching}
            />
          ) : null}
          {readiness.data ? (
            <>
              <p className="panel__meta">
                زمان بررسی در سرور:{" "}
                <time dateTime={readiness.data.checked_at} data-testid="ready-checked-at">
                  {formatJalaliDateTime(readiness.data.checked_at)}
                </time>{" "}
                (به وقت تهران)
              </p>
              {readiness.data.components.length === 0 ? (
                <EmptyState
                  title="هیچ مؤلفه‌ای گزارش نشده است."
                  hint="سرور پاسخ داد اما فهرست مؤلفه‌ها خالی است؛ به مسئول فنی اطلاع دهید."
                />
              ) : (
                <table className="table" data-testid="components-table">
                  <caption className="sr-only">وضعیت مؤلفه‌های زیرساخت</caption>
                  <thead>
                    <tr>
                      <th scope="col">مؤلفه</th>
                      <th scope="col">شناسه فنی</th>
                      <th scope="col">وضعیت</th>
                    </tr>
                  </thead>
                  <tbody>
                    {readiness.data.components.map((c) => (
                      <tr key={c.name} data-testid={`component-${c.name}`}>
                        <th scope="row" data-label="مؤلفه">
                          {COMPONENT_LABELS[c.name]}
                        </th>
                        <td data-label="شناسه فنی">
                          <code dir="ltr">{c.name}</code>
                        </td>
                        <td data-label="وضعیت">
                          <StatusChip tone={COMPONENT_STATE[c.status].tone} label={COMPONENT_STATE[c.status].label} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          ) : null}
        </section>

        <section className="panel" aria-labelledby="h-live" aria-busy={liveness.isFetching}>
          <div className="panel__head">
            <h2 id="h-live">زنده بودن سرویس</h2>
            {liveness.data ? <StatusChip testId="live-chip" tone="success" label="پاسخ‌گو" /> : null}
          </div>
          {livenessStale ? (
            <StaleBadge updatedAt={liveness.dataUpdatedAt} now={now} reason={livenessStale} />
          ) : null}
          {liveness.isPending ? <LoadingState label="در حال بررسی…" /> : null}
          {liveness.isError ? (
            <ErrorState
              title="سرویس پاسخ نداد"
              error={liveness.error}
              onRetry={() => void liveness.refetch()}
              retrying={liveness.isFetching}
            />
          ) : null}
          {liveness.data ? <p className="panel__meta">فرایند سرور در حال اجرا است و به درخواست پاسخ می‌دهد.</p> : null}
        </section>

        <section className="panel" aria-labelledby="h-version" aria-busy={version.isFetching}>
          <div className="panel__head">
            <h2 id="h-version">نسخه و ساخت</h2>
          </div>
          {version.isPending ? <LoadingState label="در حال دریافت نسخه…" /> : null}
          {version.isError ? (
            <ErrorState
              title="دریافت نسخه ناموفق بود"
              error={version.error}
              onRetry={() => void version.refetch()}
              retrying={version.isFetching}
            />
          ) : null}
          {version.data ? (
            <dl className="meta meta--rows" data-testid="version-info">
              <div>
                <dt>نسخه API</dt>
                <dd>
                  <code dir="ltr">{version.data.api_version}</code>
                </dd>
              </div>
              <div>
                <dt>نسخه قرارداد</dt>
                <dd>
                  <code dir="ltr" data-testid="version-contract">
                    {version.data.contract_version}
                  </code>
                </dd>
              </div>
              <div>
                <dt>شناسه ساخت (commit)</dt>
                <dd>
                  <code dir="ltr" data-testid="version-build">
                    {version.data.build_commit}
                  </code>
                </dd>
              </div>
              <div>
                <dt>محیط</dt>
                <dd data-testid="version-env">{ENVIRONMENT_LABELS[version.data.environment]}</dd>
              </div>
            </dl>
          ) : null}
        </section>

        <section className="panel" aria-labelledby="h-access" aria-busy={access.isFetching}>
          <div className="panel__head">
            <h2 id="h-access">درگاه دسترسی</h2>
          </div>
          <p className="panel__meta">
            پاسخ واقعی درگاه مرکزی مجوز برای عملیات <code dir="ltr">platform.status.view</code>. ورود کاربران در فاز ۱
            ساخته می‌شود؛ تا آن زمان درگاه به‌صورت پیش‌فرض رد می‌کند.
          </p>
          {access.isPending ? <LoadingState label="در حال بررسی دسترسی…" /> : null}
          {access.isError ? <AccessErrorView error={access.error} /> : null}
          {access.data ? (
            <div data-testid="access-decision">
              <StatusChip
                tone={access.data.decision === "ALLOW" ? "success" : "warning"}
                label={access.data.decision === "ALLOW" ? "مجاز" : "رد شد"}
              />{" "}
              <code dir="ltr">{access.data.reason_code}</code>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}

/** 401/403 from the access gate is the expected "no access" state, not a failure of the page. */
function AccessErrorView({ error }: { error: unknown }) {
  if (error instanceof ApiError && error.kind === "problem" && (error.status === 401 || error.status === 403)) {
    return (
      <div className="state state--forbidden" data-testid="state-forbidden">
        <StatusChip tone="warning" label={error.status === 401 ? "ورود انجام نشده" : "فاقد دسترسی"} />
        <p className="state__message" data-testid="forbidden-message">
          {error.messageFa}
        </p>
        <dl className="meta">
          <div>
            <dt>کد</dt>
            <dd>
              <code dir="ltr" data-testid="forbidden-code">
                {error.code}
              </code>
            </dd>
          </div>
          <div>
            <dt>شناسه درخواست</dt>
            <dd>
              <code dir="ltr" className="code-id" data-testid="forbidden-request-id">
                {error.requestId}
              </code>
            </dd>
          </div>
        </dl>
      </div>
    );
  }
  return <ErrorState title="بررسی دسترسی ناموفق بود" error={error} />;
}
