// Page 42 «پارامترها» (MOCK_UI_BINDING §6.4, PHASE_01 part): parameter catalogue, value history, propose and
// publish by classification. OWNER_POLICY: the owner alone, one step (Q-0103). TECHNICAL: proposed, then
// published by a config approver. BUSINESS_RULE: maker-checker AND blocked until its decision is approved - the
// server answers 409 RULE_NOT_APPROVED, which is shown as is (never computed client-side). Layout designer:
// PHASE_11 (C-33).
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { paramGuards, read, write, type Parameter, type ParameterValue } from "../api/phase01";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView } from "../components/DataView";
import { Dialog } from "../components/Dialog";
import { Field, ReasonDialog } from "../components/Form";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime } from "../lib/format";
import { CLASSIFICATION, toneLabel, VALUE_STATUS } from "../lib/labels";
import { localInputToUtc, nowUtc, QK } from "../lib/queries";
import { useAction } from "../lib/useAction";

const C = { propose: "platform.config.parameter.propose", publish: "platform.config.parameter.publish" };

function show(v: ParameterValue["value"] | undefined): string {
  if (!v) return "—";
  if (v.value === null) return "(خالی)";
  if (typeof v.value === "boolean") return v.value ? "بله" : "خیر";
  if (v.datatype === "BOOLEAN") return v.value === "true" ? "بله" : v.value === "false" ? "خیر" : v.value;
  return v.value;
}

const CLASS_HINT: Record<Parameter["classification"], string> = {
  OWNER_POLICY: "سیاست مالک: فقط مالک سامانه، در یک گام، با دلیل و تأیید دومرحله‌ای (Q-0103).",
  TECHNICAL: "فنی: پیشنهاد می‌شود و تأییدکننده پارامترها منتشر می‌کند.",
  BUSINESS_RULE: "قاعده کسب‌وکار: نفر دوم منتشر می‌کند و تا تصویب تصمیم مربوط، سرور ثبت/انتشار را مسدود می‌کند.",
};

export function ParametersPage() {
  const list = useQuery({
    queryKey: [...QK.parameters, "list"],
    queryFn: async ({ signal }) => (await read("/admin/parameters", paramGuards.paramPage, { page_size: 100 }, signal)).data,
  });
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="page" data-testid="page-parameters">
      <div className="page__head">
        <div>
          <p className="eyebrow">صفحه ۴۲ · فاز ۱</p>
          <h1>پارامترها</h1>
          <p className="lead">مقادیر نسخه‌دار با تاریخ اثر و تصمیم مبنا. طراحی چیدمان فرم‌ها در فاز ۱۱ است.</p>
        </div>
      </div>
      <DataView query={list} loading="در حال دریافت پارامترها…" errorTitle="پارامترها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "پارامتری تعریف نشده است." }}>
        {(d) => (
          <table className="table table--cards" data-testid="parameters-table">
            <caption className="sr-only">فهرست پارامترها</caption>
            <thead>
              <tr>
                <th scope="col">کلید</th>
                <th scope="col">عنوان</th>
                <th scope="col">دسته</th>
                <th scope="col">تصمیم مبنا</th>
                <th scope="col">مقدار فعال</th>
                <th scope="col">از</th>
                <th scope="col"><span className="sr-only">اقدام</span></th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((p) => {
                const c = toneLabel(CLASSIFICATION, p.classification);
                return (
                  <tr key={p.parameter_key}>
                    <td data-label="کلید"><code dir="ltr">{p.parameter_key}</code></td>
                    <td data-label="عنوان">{p.label_fa}</td>
                    <td data-label="دسته"><StatusChip tone={c.tone} label={c.label} /></td>
                    <td data-label="تصمیم مبنا"><bdi dir="ltr">{p.decision_id ?? "—"}</bdi></td>
                    <td data-label="مقدار فعال"><bdi dir="ltr">{show(p.active_value?.value)}</bdi></td>
                    <td data-label="از">{p.active_value ? formatJalaliDateTime(p.active_value.effective_from) : "—"}</td>
                    <td data-label="اقدام"><button type="button" className="btn btn--secondary" onClick={() => { setOpen(p.parameter_key); }} data-testid={`param-open-${p.parameter_key}`}>تاریخچه و تغییر</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </DataView>
      {open ? <ParameterDetail paramKey={open} onClose={() => { setOpen(null); }} /> : null}
    </div>
  );
}

// DEC-056 v1.2 (server: params.service): the owner's publish grant counts for BUSINESS_RULE values only. For a
// TECHNICAL value the button is shown only if publish is held through another role (e.g. config_approver).
const OWNER_ROLE = "owner_admin";

function ParameterDetail({ paramKey, onClose }: { paramKey: string; onClose: () => void }) {
  const { can, rolesFor } = useAuth();
  const canPublish = (classification: Parameter["classification"]): boolean =>
    classification === "TECHNICAL" ? [...rolesFor(C.publish)].some((r) => r !== OWNER_ROLE) : can(C.publish);
  const action = useAction();
  const [proposing, setProposing] = useState(false);
  const [publish, setPublish] = useState<ParameterValue | null>(null);
  const param = useQuery({
    queryKey: [...QK.parameters, "detail", paramKey],
    queryFn: async ({ signal }) => (await read(`/admin/parameters/${paramKey}`, paramGuards.param, undefined, signal)).data,
  });
  const values = useQuery({
    queryKey: [...QK.parameters, "values", paramKey],
    queryFn: async ({ signal }) => (await read(`/admin/parameters/${paramKey}/values`, paramGuards.valuePage, { page_size: 50 }, signal)).data,
  });
  return (
    <Dialog title={`پارامتر ${paramKey}`} onClose={onClose} testId="parameter-detail">
      <DataView query={param} loading="در حال دریافت پارامتر…" errorTitle="پارامتر دریافت نشد">
        {(p) => (
          <>
            <p className="lead">{p.label_fa}</p>
            <p className={p.classification === "BUSINESS_RULE" ? "notice notice--warning" : "notice notice--info"} data-testid="param-class-hint">
              {CLASS_HINT[p.classification]}
              {p.decision_id ? <> تصمیم مبنا: <bdi dir="ltr">{p.decision_id}</bdi>.</> : null}
            </p>
            {can(C.propose) ? <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setProposing(true); }} data-testid="param-propose-open">{p.classification === "OWNER_POLICY" ? "ثبت و انتشار مقدار تازه" : "پیشنهاد مقدار تازه"}</button> : null}
            {proposing ? <ProposeForm param={p} onDone={() => { setProposing(false); }} /> : null}
          </>
        )}
      </DataView>
      <h3>تاریخچه مقدارها</h3>
      <DataView query={values} loading="در حال دریافت تاریخچه…" errorTitle="تاریخچه دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "مقداری ثبت نشده است." }}>
        {(d) => (
          <ul className="list" data-testid="param-values">
            {d.items.map((v) => {
              const st = toneLabel(VALUE_STATUS, v.status);
              return (
                <li key={v.value_revision_id}>
                  <StatusChip tone={st.tone} label={st.label} /> <bdi dir="ltr">{show(v.value)}</bdi> · از {formatJalaliDateTime(v.effective_from)}
                  {v.published_at ? ` · انتشار ${formatJalaliDateTime(v.published_at)}` : ""}
                  {v.status === "PENDING_APPROVAL" && param.data !== undefined && canPublish(param.data.classification) ? (
                    <button type="button" className="btn btn--secondary btn--small" onClick={() => { action.reset(); setPublish(v); }} data-testid="param-publish">انتشار</button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </DataView>
      {!publish ? <ActionError error={action.error} /> : null}
      {publish ? (
        <ReasonDialog
          title="انتشار مقدار"
          label="یادداشت انتشار (در ممیزی ثبت می‌شود)"
          minLength={1}
          submitLabel="انتشار"
          action={action}
          onClose={() => { setPublish(null); }}
          onSubmit={async (note) =>
            (await action.run((key) => write(`/admin/parameters/${paramKey}/values/${publish.value_revision_id}/publish`, paramGuards.value, { note }, key, publish.row_version ?? null), [QK.parameters])) !== undefined
          }
        />
      ) : null}
      <div className="form__actions">
        <button type="button" className="btn btn--secondary" onClick={onClose}>بستن</button>
      </div>
    </Dialog>
  );
}

function ProposeForm({ param, onDone }: { param: Parameter; onDone: () => void }) {
  const action = useAction();
  const [value, setValue] = useState(param.datatype === "BOOLEAN" ? "true" : "");
  const [from, setFrom] = useState("");
  const [reason, setReason] = useState("");
  return (
    <form
      className="form"
      onSubmit={(e) => {
        e.preventDefault();
        const body = { value: { datatype: param.datatype, value }, effective_from: localInputToUtc(from) ?? nowUtc(), reason: reason.trim() };
        void action.run((key) => write(`/admin/parameters/${param.parameter_key}/values`, paramGuards.value, body, key), [QK.parameters]).then((r) => { if (r) onDone(); });
      }}
      data-testid="param-propose-form"
    >
      <Field label={`مقدار (${param.datatype})`}>
        {(id) =>
          param.datatype === "BOOLEAN" ? (
            <select id={id} className="input" value={value} onChange={(e) => { setValue(e.target.value); }} data-testid="param-value">
              <option value="true">بله</option>
              <option value="false">خیر</option>
            </select>
          ) : (
            <input id={id} className="input" dir="ltr" required value={value} onChange={(e) => { setValue(e.target.value); }} data-testid="param-value" />
          )
        }
      </Field>
      <Field label="تاریخ اثر (خالی = همین لحظه)">{(id) => <input id={id} className="input" type="datetime-local" value={from} onChange={(e) => { setFrom(e.target.value); }} />}</Field>
      <Field label="دلیل (در ممیزی ثبت می‌شود)">{(id) => <textarea id={id} className="input" rows={2} required minLength={3} maxLength={500} value={reason} onChange={(e) => { setReason(e.target.value); }} data-testid="param-reason" />}</Field>
      <ActionError error={action.error} />
      <div className="form__actions">
        <button type="submit" className="btn btn--primary" disabled={action.pending} data-testid="param-propose-submit">{action.pending ? "در حال ثبت…" : "ثبت"}</button>
        <button type="button" className="btn btn--secondary" onClick={onDone}>انصراف</button>
      </div>
    </form>
  );
}
