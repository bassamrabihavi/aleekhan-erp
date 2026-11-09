// Page 39 «کارها و تأییدها» (MOCK_UI_BINDING §6.2): task inbox with start / complete / block / unblock, and the
// approval inbox with approve / reject (MFA step-up, maker != checker on the server), withdraw (reason) and the
// DEC-055 one-time bootstrap approval. No SLA clock, no invented counters.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { read, workGuards, write, type Approval, type Task } from "../api/phase01";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView } from "../components/DataView";
import { Field, ReasonDialog, ShortId, TabPanel, Tabs } from "../components/Form";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime } from "../lib/format";
import { APPROVAL_ACTION, APPROVAL_STATUS, TASK_STATUS, toneLabel } from "../lib/labels";
import { QK, useCursor } from "../lib/queries";
import { useAction } from "../lib/useAction";
import { Pager } from "./SecurityPage";

const P = {
  taskRead: "platform.workflow.task.read",
  taskWork: "platform.workflow.task.work",
  apprRead: "platform.workflow.approval.read",
  apprRequest: "platform.workflow.approval.request",
  decide: "platform.workflow.approval.decide",
  docApprove: "platform.document.approve",
  publish: "platform.config.parameter.publish",
  grant: "platform.identity.assignment.grant",
};

export function WorkPage() {
  const { can } = useAuth();
  const tabs = [
    ...(can(P.apprRead) ? [{ id: "approvals", label: "تأییدها" }] : []),
    ...(can(P.taskRead) ? [{ id: "tasks", label: "کارهای من" }] : []),
  ];
  const [tab, setTab] = useState(tabs[0]?.id ?? "tasks");
  return (
    <div className="page" data-testid="page-work">
      <div className="page__head">
        <div>
          <p className="eyebrow">صفحه ۳۹ · فاز ۱</p>
          <h1>کارها و تأییدها</h1>
          <p className="lead">
            هیچ‌کس درخواست خودش را تأیید نمی‌کند (DEC-032)؛ سرور این قاعده را بررسی می‌کند. مهلت هر درخواست تأیید ۳۰ روز
            است.
          </p>
        </div>
      </div>
      {tabs.length === 0 ? (
        <p className="state state--forbidden" data-testid="state-forbidden">به این بخش دسترسی ندارید.</p>
      ) : (
        <>
          <Tabs tabs={tabs} active={tab} onChange={setTab} label="کارها و تأییدها" />
          <TabPanel id={tab}>{tab === "approvals" ? <ApprovalsTab /> : <TasksTab />}</TabPanel>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------- approvals
function ApprovalsTab() {
  const [inbox, setInbox] = useState("to_decide");
  const [status, setStatus] = useState("PENDING");
  const cursor = useCursor();
  const [open, setOpen] = useState<Approval | null>(null);
  const list = useQuery({
    queryKey: [...QK.work, "approvals", inbox, status, cursor.cursor],
    queryFn: async ({ signal }) =>
      (await read("/workflow/approvals", workGuards.approvalPage, { inbox, status, cursor: cursor.cursor, page_size: 25 }, signal)).data,
  });
  return (
    <section className="panel panel--wide" aria-labelledby="approvals-title">
      <h2 id="approvals-title">درخواست‌های تأیید</h2>
      <div className="filters">
        <Field label="صندوق">
          {(id) => (
            <select id={id} className="input" value={inbox} onChange={(e) => { cursor.reset(); setInbox(e.target.value); }} data-testid="approval-inbox">
              <option value="to_decide">نیازمند تصمیم من</option>
              <option value="requested_by_me">درخواست‌های من</option>
              <option value="">همه درخواست‌های قابل مشاهده</option>
            </select>
          )}
        </Field>
        <Field label="وضعیت">
          {(id) => (
            <select id={id} className="input" value={status} onChange={(e) => { cursor.reset(); setStatus(e.target.value); }} data-testid="approval-status">
              <option value="">همه</option>
              {Object.entries(APPROVAL_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          )}
        </Field>
      </div>
      <DataView query={list} loading="در حال دریافت درخواست‌ها…" errorTitle="درخواست‌های تأیید دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "درخواستی در این صندوق نیست." }}>
        {(d) => (
          <>
            <ul className="cards" data-testid="approvals-list">
              {d.items.map((a) => <ApprovalCard key={a.approval_id} a={a} onOpen={() => { setOpen(a); }} />)}
            </ul>
            <Pager depth={cursor.depth} next={d.page.next_cursor} onNext={cursor.next} onPrev={cursor.prev} />
          </>
        )}
      </DataView>
      {open ? <ApprovalActions approval={open} onClose={() => { setOpen(null); }} /> : null}
    </section>
  );
}

function ApprovalCard({ a, onOpen }: { a: Approval; onOpen: () => void }) {
  const { me } = useAuth();
  const st = toneLabel(APPROVAL_STATUS, a.status);
  const mine = a.requested_by === me?.user.user_id;
  return (
    <li className="card" data-testid="approval-card">
      <div className="card__head">
        <strong>{APPROVAL_ACTION[a.action] ?? a.action}</strong>
        <StatusChip tone={st.tone} label={st.label} testId="approval-status-chip" />
        {a.bootstrap_self_approval ? <span className="chip chip--warning chip--inline">تأیید اولیه مالک (DEC-055)</span> : null}
      </div>
      <dl className="meta">
        <div><dt>منبع</dt><dd><code dir="ltr">{a.resource.entity_type}</code> <ShortId id={a.resource.entity_id} /></dd></div>
        <div><dt>درخواست‌کننده</dt><dd>{mine ? "شما" : <ShortId id={a.requested_by} />}</dd></div>
        <div><dt>زمان درخواست</dt><dd>{formatJalaliDateTime(a.requested_at)}</dd></div>
        {a.expires_at ? <div><dt>مهلت</dt><dd>{formatJalaliDateTime(a.expires_at)}</dd></div> : null}
        {a.decided_at ? <div><dt>تصمیم</dt><dd>{formatJalaliDateTime(a.decided_at)} {a.decision_note ? `— ${a.decision_note}` : ""}</dd></div> : null}
      </dl>
      {a.status === "PENDING" ? (
        <button type="button" className="btn btn--secondary" onClick={onOpen} data-testid="approval-open">
          اقدام روی این درخواست
        </button>
      ) : null}
    </li>
  );
}

type ApprovalOp = "approve" | "reject" | "withdraw" | "bootstrap";

function ApprovalActions({ approval, onClose }: { approval: Approval; onClose: () => void }) {
  const { can, me } = useAuth();
  const action = useAction();
  const [op, setOp] = useState<ApprovalOp | null>(null);
  const detail = useQuery({
    queryKey: [...QK.work, "approval", approval.approval_id],
    queryFn: async ({ signal }) => read(`/workflow/approvals/${approval.approval_id}`, workGuards.approval, undefined, signal),
  });
  const mine = approval.requested_by === me?.user.user_id;
  const decider = can(P.decide) || can(P.docApprove) || can(P.publish);

  return (
    <section className="detail" aria-labelledby="appr-actions-title" data-testid="approval-actions">
      <div className="panel__head">
        <h3 id="appr-actions-title">{APPROVAL_ACTION[approval.action] ?? approval.action}</h3>
        <button type="button" className="btn btn--secondary" onClick={onClose}>بستن</button>
      </div>
      <DataView query={detail} loading="در حال دریافت درخواست…" errorTitle="درخواست دریافت نشد">
        {(r) => {
          const a = r.data;
          if (a.status !== "PENDING") {
            const st = toneLabel(APPROVAL_STATUS, a.status);
            return <p>وضعیت کنونی: <StatusChip tone={st.tone} label={st.label} testId="approval-final-status" /></p>;
          }
          return (
            <>
              <div className="actions" role="group" aria-label="اقدام‌های درخواست">
                {!mine && decider ? (
                  <>
                    <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp("approve"); }} data-testid="approval-approve">تأیید</button>
                    <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setOp("reject"); }} data-testid="approval-reject">رد</button>
                  </>
                ) : null}
                {mine && can(P.apprRequest) ? (
                  <button type="button" className="btn btn--secondary" onClick={() => { action.reset(); setOp("withdraw"); }} data-testid="approval-withdraw">پس گرفتن درخواست</button>
                ) : null}
                {mine && a.action === P.grant && can(P.grant) ? (
                  <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp("bootstrap"); }} data-testid="approval-bootstrap">
                    تأیید اولیه نخستین دارنده (DEC-055)
                  </button>
                ) : null}
              </div>
              {mine ? (
                <p className="field__hint">
                  این درخواست را خودتان ثبت کرده‌اید؛ تأیید عادی آن با نفر دوم است (DEC-032). تأیید اولیه فقط برای نخستین
                  دارنده هر نقش تأییدی، یک بار، با دلیل و تأیید دومرحله‌ای تازه مجاز است و سرور شرایط را بررسی می‌کند.
                </p>
              ) : null}
              {!mine && !decider ? <p className="field__hint">برای تصمیم درباره این درخواست مجوز ندارید.</p> : null}
              {op ? (
                <ReasonDialog
                  title={{ approve: "تأیید درخواست", reject: "رد درخواست", withdraw: "پس گرفتن درخواست", bootstrap: "تأیید اولیه نخستین دارنده (DEC-055)" }[op]}
                  label={op === "approve" ? "یادداشت تصمیم (در ممیزی ثبت می‌شود)" : "دلیل (در ممیزی ثبت می‌شود)"}
                  minLength={op === "approve" ? 1 : 3}
                  description={op === "bootstrap" ? "این تأیید با علامت ویژه «تأیید اولیه مالک» در ممیزی ثبت می‌شود و برای هر نقش فقط یک بار ممکن است." : undefined}
                  submitLabel={{ approve: "تأیید", reject: "رد", withdraw: "پس گرفتن", bootstrap: "تأیید اولیه" }[op]}
                  danger={op === "reject"}
                  action={action}
                  onClose={() => { setOp(null); }}
                  onSubmit={async (text) => {
                    const base = `/workflow/approvals/${a.approval_id}`;
                    const body =
                      op === "approve" || op === "reject"
                        ? { resource_revision: a.resource.revision ?? 1, note: text }
                        : { reason: text };
                    const path = op === "bootstrap" ? `${base}/bootstrap-approve` : `${base}/${op}`;
                    const out = await action.run((key) => write(path, workGuards.approval, body, key, r.version), [QK.work, ["admin"]]);
                    if (out) onClose();
                    return out !== undefined;
                  }}
                />
              ) : null}
              {!op ? <ActionError error={action.error} /> : null}
            </>
          );
        }}
      </DataView>
    </section>
  );
}

// ----------------------------------------------------------------------------------------------- tasks
function TasksTab() {
  const { can } = useAuth();
  const [inbox, setInbox] = useState("mine");
  const [status, setStatus] = useState("");
  const cursor = useCursor();
  const action = useAction();
  const [blockTask, setBlockTask] = useState<Task | null>(null);
  const list = useQuery({
    queryKey: [...QK.work, "tasks", inbox, status, cursor.cursor],
    queryFn: async ({ signal }) =>
      (await read("/workflow/tasks", workGuards.taskPage, { inbox, status, cursor: cursor.cursor, page_size: 25 }, signal)).data,
  });
  const run = (t: Task, verb: "start" | "complete" | "unblock") =>
    void action.run((key) => write(`/workflow/tasks/${t.task_id}/${verb}`, workGuards.task, {}, key, t.row_version), [QK.work]);

  return (
    <section className="panel panel--wide" aria-labelledby="tasks-title">
      <h2 id="tasks-title">کارها</h2>
      <div className="filters">
        <Field label="صندوق">
          {(id) => (
            <select id={id} className="input" value={inbox} onChange={(e) => { cursor.reset(); setInbox(e.target.value); }} data-testid="task-inbox">
              <option value="mine">واگذارشده به من</option>
              <option value="my_units">واحدهای من</option>
              <option value="created_by_me">ساخته‌شده توسط من</option>
            </select>
          )}
        </Field>
        <Field label="وضعیت">
          {(id) => (
            <select id={id} className="input" value={status} onChange={(e) => { cursor.reset(); setStatus(e.target.value); }}>
              <option value="">همه</option>
              {Object.entries(TASK_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          )}
        </Field>
      </div>
      <ActionError error={blockTask ? null : action.error} />
      <DataView query={list} loading="در حال دریافت کارها…" errorTitle="کارها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "کاری در این صندوق نیست." }}>
        {(d) => (
          <>
            <table className="table table--cards" data-testid="tasks-table">
              <caption className="sr-only">فهرست کارها</caption>
              <thead>
                <tr>
                  <th scope="col">موضوع</th>
                  <th scope="col">وضعیت</th>
                  <th scope="col">سررسید</th>
                  <th scope="col">مرتبط با</th>
                  <th scope="col"><span className="sr-only">اقدام</span></th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((t) => {
                  const st = toneLabel(TASK_STATUS, t.status);
                  return (
                    <tr key={t.task_id}>
                      <td data-label="موضوع">{t.subject}{t.blocked_reason ? <p className="field__hint">علت توقف: {t.blocked_reason}</p> : null}</td>
                      <td data-label="وضعیت"><StatusChip tone={st.tone} label={st.label} /></td>
                      <td data-label="سررسید">{t.due_at ? formatJalaliDateTime(t.due_at) : "—"}</td>
                      <td data-label="مرتبط با">{t.related ? <><code dir="ltr">{t.related.entity_type}</code> <code dir="ltr">{t.related.entity_id}</code></> : "—"}</td>
                      <td data-label="اقدام">
                        {can(P.taskWork) ? (
                          <div className="actions">
                            {t.status === "OPEN" || t.status === "ASSIGNED" ? <button type="button" className="btn btn--secondary" disabled={action.pending} onClick={() => { run(t, "start"); }}>شروع</button> : null}
                            {t.status === "IN_PROGRESS" ? (
                              <>
                                <button type="button" className="btn btn--secondary" disabled={action.pending} onClick={() => { run(t, "complete"); }}>انجام شد</button>
                                <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setBlockTask(t); }}>توقف</button>
                              </>
                            ) : null}
                            {t.status === "BLOCKED" ? <button type="button" className="btn btn--secondary" disabled={action.pending} onClick={() => { run(t, "unblock"); }}>ادامه</button> : null}
                          </div>
                        ) : null}
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
      {blockTask ? (
        <ReasonDialog
          title="توقف کار"
          label="علت توقف"
          submitLabel="ثبت توقف"
          action={action}
          onClose={() => { setBlockTask(null); }}
          onSubmit={async (reason) =>
            (await action.run((key) => write(`/workflow/tasks/${blockTask.task_id}/block`, workGuards.task, { reason }, key, blockTask.row_version), [QK.work])) !== undefined
          }
        />
      ) : null}
    </section>
  );
}
