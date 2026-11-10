// Page 36 «سلامت سامانه و Job» (MOCK_UI_BINDING §6.1, PHASE_01 part): component status, outbox / job / security
// counters from GET /admin/health, audit integrity, job definitions (protected / cancellable flags), job runs
// with safe cancel (reason + MFA step-up). Force cancel is not offered (C-31); no invented "overall health %".
// 01.6: event delivery freshness (lag, stale flag, aggregates blocked by a dead letter, open compensations).
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { opsGuards, read, write, type HealthDetail, type Job, type JobDefinition } from "../api/phase01";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView } from "../components/DataView";
import { Field, ReasonDialog, ShortId } from "../components/Form";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import { COMPONENT_LABELS, COMPONENT_STATE, INTEGRITY_STATUS, JOB_STATE, toneLabel } from "../lib/labels";
import { QK, useCursor } from "../lib/queries";
import { useAction } from "../lib/useAction";
import { Pager } from "./SecurityPage";

const O = {
  health: "platform.ops.health.read",
  jobRead: "platform.ops.job.read",
  jobCancel: "platform.ops.job.cancel",
  integrity: "platform.audit.integrity.read",
};
const REFRESH_MS = 30_000;

function duration(j: Job): string {
  if (!j.started_at) return "—";
  const end = j.finished_at ? Date.parse(j.finished_at) : Date.now();
  const s = Math.max(0, Math.round((end - Date.parse(j.started_at)) / 1000));
  if (s < 60) return `${toFaDigits(s)} ثانیه`;
  return `${toFaDigits(Math.floor(s / 60))} دقیقه`;
}

export function OpsPage() {
  const { can } = useAuth();
  return (
    <div className="page" data-testid="page-ops">
      <div className="page__head">
        <div>
          <p className="eyebrow">صفحه ۳۶ · فاز ۱</p>
          <h1>سلامت سامانه و Job</h1>
          <p className="lead">
            اعداد مستقیماً از سرور خوانده می‌شوند و هر {toFaDigits(REFRESH_MS / 1000)} ثانیه تازه می‌شوند. لغو اجباری Job در
            فاز ۱ وجود ندارد؛ فقط «پایان امن» با دلیل و تأیید دومرحله‌ای.
          </p>
        </div>
      </div>
      {can(O.health) ? <HealthPanel /> : null}
      {can(O.integrity) ? <IntegrityPanel /> : null}
      {can(O.jobRead) ? <JobsPanel /> : null}
    </div>
  );
}

function Counter({ label, value, testId }: { label: string; value: number; testId: string }) {
  return (
    <div className="counter" data-testid={testId}>
      <span className="counter__value">{toFaDigits(value)}</span>
      <span className="counter__label">{label}</span>
    </div>
  );
}

function HealthPanel() {
  const q = useQuery({
    queryKey: [...QK.ops, "health"],
    refetchInterval: REFRESH_MS,
    queryFn: async ({ signal }) => (await read("/admin/health", opsGuards.health, undefined, signal)).data,
  });
  return (
    <section className="panel panel--wide" aria-labelledby="health-title" data-testid="health-panel">
      <h2 id="health-title">سلامت اجزا</h2>
      <DataView query={q} loading="در حال دریافت سلامت سامانه…" errorTitle="سلامت سامانه دریافت نشد">
        {(h) => (
          <>
            <p className="panel__meta">بررسی سرور: {formatJalaliDateTime(h.checked_at)}</p>
            <ul className="chips" aria-label="وضعیت اجزا">
              {h.components.map((c) => {
                const st = COMPONENT_STATE[c.status];
                return (
                  <li key={c.name}>
                    {(COMPONENT_LABELS as Record<string, string | undefined>)[c.name] ?? c.name}: <StatusChip tone={st.tone} label={st.label} />
                  </li>
                );
              })}
            </ul>
            <div className="counters">
              <Counter label="رویداد خروجی در انتظار" value={h.outbox.pending} testId="c-outbox-pending" />
              <Counter label="رویداد خروجی ناموفق" value={h.outbox.failed} testId="c-outbox-failed" />
              <Counter label="رویداد ماندگار (dead letter)" value={h.outbox.dead_letter} testId="c-outbox-dead" />
              <Counter label="Job در حال اجرا" value={h.jobs.running} testId="c-jobs-running" />
              <Counter label="Job در صف" value={h.jobs.queued} testId="c-jobs-queued" />
              <Counter label="Job ناموفق (۲۴ ساعت)" value={h.jobs.failed_24h} testId="c-jobs-failed" />
              {h.security ? (
                <>
                  <Counter label="ورود ناموفق (۲۴ ساعت)" value={h.security.failed_logins_24h} testId="c-failed-logins" />
                  <Counter label="کاربر قفل‌شده" value={h.security.locked_users} testId="c-locked-users" />
                </>
              ) : null}
            </div>
            {h.outbox.oldest_pending_at ? <p className="panel__meta">قدیمی‌ترین رویداد در انتظار: {formatJalaliDateTime(h.outbox.oldest_pending_at)}</p> : null}
            {h.integration ? <IntegrationBlock i={h.integration} /> : null}
          </>
        )}
      </DataView>
    </section>
  );
}

function lagText(seconds: number | null): string {
  if (seconds === null) return "رویداد تحویل‌نشده‌ای نیست";
  if (seconds < 60) return `${toFaDigits(seconds)} ثانیه`;
  return `${toFaDigits(Math.floor(seconds / 60))} دقیقه`;
}

// 01.6: delivery of events between modules (outbox -> consumers). "Stale" = the oldest undelivered event is older
// than the server's TECHNICAL DEFAULT threshold; aggregates blocked by a dead letter wait for an administrator.
function IntegrationBlock({ i }: { i: NonNullable<HealthDetail["integration"]> }) {
  // never "up to date" while events are still waiting: no lag -> all delivered; lag under the threshold -> in progress
  const [tone, label] =
    i.blocked_aggregates > 0
      ? (["danger", "رویداد متوقف پشت dead letter"] as const)
      : i.stale
        ? (["warning", "تأخیر در تحویل"] as const)
        : i.lag_seconds === null
          ? (["success", "همه رویدادها تحویل شده"] as const)
          : (["info", "در انتظار تحویل (زیر آستانه)"] as const);
  return (
    <div className="detail" data-testid="integration-health">
      <h3>تحویل رویداد بین ماژول‌ها</h3>
      <p className="panel__meta">
        وضعیت: <StatusChip tone={tone} label={label} testId="integration-stale" /> · تأخیر قدیمی‌ترین رویداد: {lagText(i.lag_seconds)}
        {" "}(آستانه {toFaDigits(Math.round(i.stale_after_seconds / 60))} دقیقه، پیش‌فرض فنی)
      </p>
      <div className="counters">
        <Counter label="جریان متوقف پشت dead letter" value={i.blocked_aggregates} testId="c-int-blocked" />
        <Counter label="رویداد منتظر پشت آن" value={i.held_events} testId="c-int-held" />
        <Counter label="تعارض باز" value={i.open_conflicts} testId="c-int-conflicts" />
        <Counter label="جبران دستی لازم" value={i.compensation_open} testId="c-int-compensation" />
      </div>
      {i.last_acked_at ? <p className="panel__meta">آخرین تحویل موفق: {formatJalaliDateTime(i.last_acked_at)}</p> : null}
    </div>
  );
}

function IntegrityPanel() {
  const q = useQuery({
    queryKey: [...QK.ops, "integrity"],
    queryFn: async ({ signal }) => (await read("/audits/integrity", opsGuards.integrity, undefined, signal)).data,
  });
  return (
    <section className="panel" aria-labelledby="integrity-title" data-testid="integrity-panel">
      <h2 id="integrity-title">یکپارچگی زنجیره ممیزی</h2>
      <DataView query={q} loading="در حال دریافت نتیجه بررسی…" errorTitle="نتیجه بررسی دریافت نشد">
        {(i) => {
          const st = toneLabel(INTEGRITY_STATUS, i.status);
          return (
            <dl className="meta meta--rows">
              <div><dt>وضعیت</dt><dd><StatusChip tone={st.tone} label={st.label} testId="integrity-status" /></dd></div>
              <div><dt>آخرین بررسی</dt><dd>{i.checked_at ? formatJalaliDateTime(i.checked_at) : "—"}</dd></div>
              <div><dt>رویدادهای بررسی‌شده</dt><dd>{toFaDigits(i.events_checked)}</dd></div>
              {i.first_broken_event_id ? <div><dt>نخستین رویداد ناسازگار</dt><dd><ShortId id={i.first_broken_event_id} /></dd></div> : null}
            </dl>
          );
        }}
      </DataView>
      <p className="field__hint">رویدادهای ممیزی فقط افزوده می‌شوند؛ هیچ API برای ویرایش یا حذف آن‌ها وجود ندارد.</p>
    </section>
  );
}

function JobsPanel() {
  const { can } = useAuth();
  const [state, setState] = useState("");
  const cursor = useCursor();
  const action = useAction();
  const [cancel, setCancel] = useState<Job | null>(null);
  const defs = useQuery({
    queryKey: [...QK.ops, "job-definitions"],
    queryFn: async ({ signal }) => (await read("/admin/job-definitions", opsGuards.defPage, { page_size: 100 }, signal)).data,
  });
  const jobs = useQuery({
    queryKey: [...QK.ops, "jobs", state, cursor.cursor],
    refetchInterval: REFRESH_MS,
    queryFn: async ({ signal }) => (await read("/admin/jobs", opsGuards.jobPage, { state, cursor: cursor.cursor, page_size: 25 }, signal)).data,
  });
  const defOf = new Map((defs.data?.items ?? []).map((d) => [d.job_type, d]));

  function cancelBlock(j: Job, d: JobDefinition | undefined): string | null {
    if (!d) return "تعریف این نوع Job دریافت نشد";
    if (d.protected) return "Job محافظت‌شده — لغو نمی‌شود";
    if (!d.cancellable) return "این نوع Job قابل لغو نیست";
    if (j.state !== "QUEUED" && j.state !== "RUNNING") return null;
    return "";
  }

  return (
    <>
      <section className="panel panel--wide" aria-labelledby="defs-title">
        <h2 id="defs-title">انواع Job</h2>
        <DataView query={defs} loading="در حال دریافت انواع Job…" errorTitle="انواع Job دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "نوع Jobی تعریف نشده است." }}>
          {(d) => (
            <table className="table table--cards" data-testid="job-definitions">
              <caption className="sr-only">انواع Job</caption>
              <thead><tr><th scope="col">نوع</th><th scope="col">نام</th><th scope="col">محافظت‌شده</th><th scope="col">قابل لغو امن</th></tr></thead>
              <tbody>
                {d.items.map((x) => (
                  <tr key={x.job_type}>
                    <td data-label="نوع"><code dir="ltr">{x.job_type}</code></td>
                    <td data-label="نام">{x.name_fa}</td>
                    <td data-label="محافظت‌شده">{x.protected ? <StatusChip tone="warning" label="بله — هرگز لغو نمی‌شود" /> : "خیر"}</td>
                    <td data-label="قابل لغو امن">{x.cancellable ? "بله" : "خیر"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </DataView>
      </section>
      <section className="panel panel--wide" aria-labelledby="jobs-title">
        <h2 id="jobs-title">اجراهای Job</h2>
        <div className="filters">
          <Field label="وضعیت">
            {(id) => (
              <select id={id} className="input" value={state} onChange={(e) => { cursor.reset(); setState(e.target.value); }} data-testid="job-state-filter">
                <option value="">همه</option>
                {Object.entries(JOB_STATE).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
            )}
          </Field>
        </div>
        {!cancel ? <ActionError error={action.error} /> : null}
        <DataView query={jobs} loading="در حال دریافت اجراها…" errorTitle="اجراهای Job دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "اجرایی با این شرط ثبت نشده است." }}>
          {(d) => (
            <>
              <table className="table table--cards" data-testid="jobs-table">
                <caption className="sr-only">اجراهای Job</caption>
                <thead><tr><th scope="col">شناسه</th><th scope="col">نوع</th><th scope="col">وضعیت</th><th scope="col">پیشرفت</th><th scope="col">در صف از</th><th scope="col">مدت</th><th scope="col"><span className="sr-only">اقدام</span></th></tr></thead>
                <tbody>
                  {d.items.map((j) => {
                    const st = toneLabel(JOB_STATE, j.state);
                    const def = defOf.get(j.job_type);
                    const block = cancelBlock(j, def);
                    return (
                      <tr key={j.job_id} data-testid={`job-${j.job_type}`}>
                        <td data-label="شناسه"><ShortId id={j.job_id} /></td>
                        <td data-label="نوع">{def?.name_fa ?? ""} <code dir="ltr">{j.job_type}</code></td>
                        <td data-label="وضعیت"><StatusChip tone={st.tone} label={st.label} />{j.cancel_reason ? <p className="field__hint">دلیل لغو: {j.cancel_reason}</p> : null}{j.error_code ? <p className="field__hint">کد خطا <code dir="ltr">{j.error_code}</code></p> : null}</td>
                        <td data-label="پیشرفت">{j.progress === null ? "—" : `${toFaDigits(j.progress)}٪`}</td>
                        <td data-label="در صف از">{formatJalaliDateTime(j.queued_at)}</td>
                        <td data-label="مدت">{duration(j)}</td>
                        <td data-label="اقدام">
                          {block === null ? null : block === "" && can(O.jobCancel) ? (
                            <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setCancel(j); }} data-testid="job-cancel">پایان امن</button>
                          ) : (
                            <span className="field__hint" data-testid="job-not-cancellable">{block || "مجوز لغو ندارید"}</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <Pager depth={cursor.depth} next={d.page.next_cursor} onNext={cursor.next} onPrev={cursor.prev} />
            </>
          )}
        </DataView>
      </section>
      {cancel ? (
        <ReasonDialog
          title="پایان امن Job"
          description="درخواست لغو ثبت می‌شود؛ Job در نقطه امن بعدی متوقف می‌شود (Job در صف فوراً لغو می‌شود). این اقدام با دلیل در ممیزی ثبت می‌شود."
          submitLabel="ثبت درخواست پایان امن"
          danger
          action={action}
          onClose={() => { setCancel(null); }}
          onSubmit={async (reason) =>
            (await action.run((key) => write(`/admin/jobs/${cancel.job_id}/request-cancel`, opsGuards.job, { reason }, key, cancel.row_version), [QK.ops])) !== undefined
          }
          testId="job-cancel-dialog"
        />
      ) : null}
    </>
  );
}
