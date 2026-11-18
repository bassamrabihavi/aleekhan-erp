// Page 33 «تغییرات سفارش و مهندسی», PHASE_02 part only (C-61, DEC-059; MOCK_UI_BINDING §7.5): change request
// list, new request on a confirmed order (kinds allowed by the order state), before / after, impact on lines /
// serials / snapshots / version (materials, WIP, capacity and cost are later phases), the commercial decision
// (commercial_manager or owner, fresh MFA, never the requester), the planning decision of a due-date change
// (approve OR reject with a reason; neither the requester nor the deciding manager) and the apply step
// (new order version + new serial snapshots). ECR/ECO is PHASE_03/04. No sample KPI numbers.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { g, get, K2, PERM, send, type ChangeItem, type ChangeKind, type ChangeRequest, type CustomerOrder } from "../api/phase02";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView, ForbiddenState } from "../components/DataView";
import { Dialog } from "../components/Dialog";
import { Field, Requester, ShortId } from "../components/Form";
import { DisabledAction, JalaliDateField, Kpi, LATER_TEXT, LaterKpi, LaterSections, Num, PageHead, PageInfoButtons } from "../components/Phase02";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import { formatJalaliDate } from "../lib/jalali";
import { toneLabel } from "../lib/labels";
import { CHANGE_KIND, CHANGE_STATUS, ORDER_STATUS, UOM } from "../lib/labels02";
import { useCursor } from "../lib/queries";
import { navigate, segments, useRoute } from "../lib/router";
import { useAction } from "../lib/useAction";
import { Pager } from "./SecurityPage";

export function ChangesPage() {
  const { can } = useAuth();
  const route = useRoute();
  const [first, second] = segments(route, "/changes");
  if (!can(PERM.changeRead)) {
    return (
      <div className="page" data-testid="page-changes">
        <PageHead page="صفحه ۳۳ · فاز ۲" title="تغییرات سفارش" />
        <ForbiddenState />
      </div>
    );
  }
  if (!first) {
    return (
      <div className="page" data-testid="page-changes">
        <ChangeList />
      </div>
    );
  }
  return (
    <div className="page" data-testid="page-changes">
      <PageHead
        page="صفحه ۳۳ · فاز ۲ (بخش سفارش)"
        title="تغییرات سفارش"
        lead="سفارش تأییدشده مستقیم ویرایش نمی‌شود. هر تغییر یک درخواست است: تصمیم مدیر بازرگانی، برای تغییر تاریخ تحویل تأیید برنامه‌ریزی هم، و سپس اعمال که نسخه جدید سفارش و Snapshot جدید سریال می‌سازد. تغییرات مهندسی (ECR/ECO) در فازهای ۳ و ۴ می‌آیند."
      />
      {first === "new" && second ? <NewChange orderId={second} /> : <ChangeDetail id={first} />}
    </div>
  );
}

function ChangeList() {
  const cursor = useCursor();
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const list = useQuery({
    queryKey: [...K2.changes, "list", status, kind, cursor.cursor],
    queryFn: async ({ signal }) =>
      (await get("/commercial/change-requests", g.crPage, { status: status || undefined, kind: kind || undefined, cursor: cursor.cursor, page_size: 25 }, signal)).data,
  });
  const counts = useQuery({
    queryKey: [...K2.changes, "counts"],
    queryFn: async ({ signal }) => (await get("/commercial/change-requests/counts", g.changeCounts, undefined, signal)).data,
  });
  const items = list.data?.items ?? [];
  const selected = items.find((c) => c.change_request_id === picked) ?? items[0] ?? null;
  const n = (v: number | undefined) => (v === undefined ? "…" : toFaDigits(v));
  return (
    <>
      <ChangeHead selected={selected} />
      <nav className="pagetabs" aria-label="بخش‌های مرتبط با تغییرات سفارش">
        <span className="pagetabs__item" aria-current="page">فهرست درخواست‌ها</span>
        <a href="#/orders" className="pagetabs__item">سفارش‌ها (درخواست جدید از صفحه سفارش)</a>
        <a href="#/work" className="pagetabs__item">کارها و تأییدها</a>
      </nav>
      <ul className="kpis" data-fid="kpis" aria-label="شمارش درخواست‌های تغییر">
        <Kpi label="درخواست‌های باز" value={counts.isError ? "—" : n(counts.data?.open)} note={counts.data ? `در انتظار تصمیم: ${toFaDigits(counts.data.awaiting_decision)}` : "پیش‌نویس، ارسال‌شده یا تأییدشده"} testId="kpi-open" />
        <LaterKpi label="نیازمند تحلیل اثر" phase="PHASE_06 / PHASE_07" />
        <Kpi label="تغییرات اجراشده" value={counts.isError ? "—" : n(counts.data?.applied)} note="با نسخه جدید سفارش" tone="good" testId="kpi-applied" />
        <Kpi label="درخواست لغو" value={counts.isError ? "—" : n(counts.data?.cancel_open)} note="لغو سفارش یا ردیف، هنوز باز" tone="critical" testId="kpi-cancel" />
      </ul>
      {counts.isError ? <p className="field__hint" role="status">شمارش‌ها دریافت نشد؛ فهرست زیر معتبر است.</p> : null}
      <div className="grid-main grid-main--changes">
        <section className="panel" aria-labelledby="changes-title" data-fid="change-list">
          <div className="panel__head panel__head--wrap">
            <h2 id="changes-title">فهرست درخواست‌ها</h2>
          <div className="filters filters--compact">
            <Field label="وضعیت">
              {(id) => (
                <select id={id} className="input" value={status} onChange={(e) => { cursor.reset(); setStatus(e.target.value); }} data-testid="change-status-filter">
                  <option value="">همه</option>
                  {Object.entries(CHANGE_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
              )}
            </Field>
            <Field label="نوع">
              {(id) => (
                <select id={id} className="input" value={kind} onChange={(e) => { cursor.reset(); setKind(e.target.value); }}>
                  <option value="">همه</option>
                  {Object.entries(CHANGE_KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              )}
            </Field>
          </div>
          </div>
          <DataView query={list} loading="در حال دریافت درخواست‌ها…" errorTitle="درخواست‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "درخواست تغییری با این فیلتر نیست." }}>
            {(d) => (
              <>
                <table className="table table--cards table--grid" data-testid="changes-table">
                  <caption className="sr-only">درخواست‌های تغییر سفارش؛ ردیف انتخاب‌شده در «مقایسه قبل و بعد» دیده می‌شود</caption>
                  <thead>
                    <tr>
                      <th scope="col">شماره</th>
                      <th scope="col">نوع</th>
                      <th scope="col">دلیل</th>
                      <th scope="col">ثبت</th>
                      <th scope="col">وضعیت</th>
                      <th scope="col"><span className="sr-only">مقایسه</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((c) => {
                      const on = selected?.change_request_id === c.change_request_id;
                      return (
                        <tr key={c.change_request_id} className={on ? "row--current" : undefined}>
                          <td data-label="شماره"><a href={`#/changes/${c.change_request_id}`} data-testid="change-open"><Num value={c.request_no} /></a></td>
                          <td data-label="نوع">{CHANGE_KIND[c.kind] ?? c.kind}</td>
                          <td data-label="دلیل" className="cell--wide">{c.reason}</td>
                          <td data-label="ثبت">{formatJalaliDateTime(c.created_at)}</td>
                          <td data-label="وضعیت"><StatusChip {...toneLabel(CHANGE_STATUS, c.status)} /></td>
                          <td data-label="مقایسه">
                            <button type="button" className="btn btn--outline btn--compact" aria-pressed={on} onClick={() => { setPicked(c.change_request_id); }} data-testid="change-compare-pick">
                              {on ? "در مقایسه" : "مقایسه"}
                            </button>
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
        <section className="panel compare-panel" aria-labelledby="compare-title" data-fid="change-compare" data-testid="change-compare">
          <div className="panel__head">
            <h2 id="compare-title">مقایسه قبل و بعد</h2>
            {selected ? <Num value={selected.request_no} /> : null}
          </div>
          {selected ? (
            <CompareBody cr={selected} />
          ) : (
            <>
              <p className="field__hint" data-testid="compare-empty">درخواستی برای مقایسه انتخاب نشده است.</p>
              <div className="parttitle">وضعیت قبل · وضعیت درخواستی</div>
              <div className="parttitle">تحلیل اثر موردنیاز</div>
              <div className="parttitle">گیت‌های تأیید</div>
              <Gates cr={null} />
            </>
          )}
        </section>
      </div>
      <section className="panel later-panel" aria-labelledby="effectivity-title" data-fid="revision-effectivity">
        <div className="panel__head">
          <h2 id="effectivity-title">قاعده اثرپذیری Revision بر مقدار</h2>
        </div>
        <p className="later__text">{LATER_TEXT}</p>
        <p className="later__meta">
          فاز مالک: <bdi dir="ltr">PHASE_04 / PHASE_05</bdi> — تغییر Revision مهندسی (ECR/ECO) و اثر آن بر مقدار سفارش، Batch و BOM در فازهای ۴ و ۵ ساخته می‌شود؛ در فاز ۲ تغییر سفارش فقط نسخه جدید سفارش و Snapshot جدید سریال می‌سازد.
        </p>
      </section>
    </>
  );
}

/** Page head of the list: the decision action opens the selected request, where the decision is recorded. */
function ChangeHead({ selected }: { selected: ChangeRequest | null }) {
  const { can, me } = useAuth();
  const mayAct = can(PERM.changeDecide) || can(PERM.changePlanning) || can(PERM.changeApply);
  const open = selected !== null && (selected.status === "SUBMITTED" || selected.status === "APPROVED");
  const reason = !mayAct
    ? "برای ثبت تصمیم نقش مدیر بازرگانی یا برنامه‌ریزی لازم است."
    : !selected
      ? "ابتدا یک درخواست را از فهرست انتخاب کنید."
      : !open
        ? "درخواست انتخاب‌شده باز نیست و تصمیمی نمی‌خواهد."
        : selected.requested_by === me?.user.user_id
          ? "این درخواست را خودتان ثبت کرده‌اید؛ تصمیم با فرد دیگری است."
          : null;
  return (
    <PageHead
      page="برنامه‌ریزی و کنترل · صفحه ۳۳ · فاز ۲ (بخش سفارش)"
      title="کنترل تغییرات سفارش"
      lead="مقایسه قبل و بعد، تصمیم، تأیید برنامه‌ریزی و اعمال با نسخه جدید سفارش."
      actions={
        <>
          <PageInfoButtons help={CHANGES_HELP} owner="برنامه‌ریزی و کنترل · گردش کار بین بازرگانی و برنامه‌ریزی" sources={CHANGES_SOURCES} />
          {reason || !selected ? (
            <DisabledAction primary label="ثبت تصمیم روی درخواست" reason={reason ?? "ابتدا یک درخواست را انتخاب کنید."} testId="change-decide-disabled" />
          ) : (
            <a className="btn btn--primary btn--compact" href={`#/changes/${selected.change_request_id}`} data-testid="change-decide-open">
              ثبت تصمیم روی درخواست
            </a>
          )}
        </>
      }
    />
  );
}

const CHANGES_HELP = (
  <>
    <p>سفارش تأییدشده مستقیم ویرایش نمی‌شود. هر تغییر یک درخواست است: تصمیم مدیر بازرگانی، برای تغییر تاریخ تحویل تأیید برنامه‌ریزی هم، و سپس اعمال که نسخه جدید سفارش و Snapshot جدید سریال می‌سازد.</p>
    <p>درخواست‌کننده هرگز تصمیم‌گیرنده نیست. درخواست باز پس از ۳۰ روز بی‌پاسخ منقضی می‌شود. تغییرات مهندسی (ECR/ECO) در فازهای ۳ و ۴ می‌آیند.</p>
  </>
);

const CHANGES_SOURCES = [
  { label: "درخواست‌های تغییر", detail: "سرور سامانه: /commercial/change-requests (نسخه‌دار؛ تصمیم با If-Match و MFA تازه)" },
  { label: "شمارش‌ها", detail: "سرور سامانه: /commercial/change-requests/counts (همان دامنه دسترسی فهرست)" },
  { label: "اثر تغییر", detail: "ردیف‌ها، سریال‌ها و Snapshotها از فاز ۲؛ مواد، WIP، ظرفیت و هزینه در فازهای بعد" },
];

/** Before / after of the selected request (from the request items and the current order), impact and gates. */
function CompareBody({ cr }: { cr: ChangeRequest }) {
  const order = useQuery({
    queryKey: [...K2.orders, "one", cr.order_id],
    queryFn: ({ signal }) => get(`/commercial/customer-orders/${cr.order_id}`, g.order, undefined, signal),
    select: (r) => r.data,
  });
  const impact = useQuery({
    queryKey: [...K2.changes, "impact", cr.change_request_id, cr.row_version],
    queryFn: async ({ signal }) => (await get(`/commercial/change-requests/${cr.change_request_id}/impact`, g.impact, undefined, signal)).data,
  });
  const ba = beforeAfter(cr, order.data);
  return (
    <>
      <div className="comparison">
        <div className="tile tile--compare">
          <h3>وضعیت قبل</h3>
          <b data-testid="compare-before">{order.isPending ? "…" : ba.before}</b>
        </div>
        <div className="tile tile--compare">
          <h3>وضعیت درخواستی</h3>
          <b data-testid="compare-after">{ba.after}</b>
        </div>
      </div>
      <dl className="meta meta--compact">
        <div><dt>دلیل</dt><dd>{cr.reason}</dd></div>
        <div><dt>درخواست‌کننده</dt><dd><Requester id={cr.requested_by} name={cr.requested_by_name} /></dd></div>
      </dl>
      <div className="parttitle">تحلیل اثر موردنیاز</div>
      {impact.isPending ? (
        <p className="field__hint">در حال محاسبه اثر…</p>
      ) : impact.isError ? (
        <p className="field__hint">اثر دریافت نشد.</p>
      ) : (
        <p className="alert" data-testid="compare-impact">
          ردیف {toFaDigits(impact.data.lines_affected.length)} · سریال {toFaDigits(impact.data.serials_affected.length)} · Snapshot جدید {toFaDigits(impact.data.snapshots_to_write)}؛ مواد، WIP و هزینه: فازهای بعد.
        </p>
      )}
      <div className="parttitle">گیت‌های تأیید</div>
      <Gates cr={cr} />
    </>
  );
}

function beforeAfter(cr: ChangeRequest, order: CustomerOrder | undefined): { before: string; after: string } {
  const first = cr.items[0];
  const more = cr.items.length > 1 ? ` (+${toFaDigits(cr.items.length - 1)})` : "";
  const ln = first?.line_id ? order?.lines.find((l) => l.line_id === first.line_id) : undefined;
  const orderState = order ? (ORDER_STATUS[order.status]?.label ?? order.status) : "—";
  switch (cr.kind) {
    case "QTY_CHANGE":
      return { before: ln ? `${toFaDigits(ln.quantity)} ${UOM[ln.uom] ?? ln.uom}` : "—", after: first?.quantity !== undefined ? `${toFaDigits(first.quantity)}${more}` : "—" };
    case "DUE_DATE_CHANGE":
      return { before: formatJalaliDate(ln ? ln.requested_due_date : (order?.requested_due_date ?? null)), after: `${formatJalaliDate(first?.requested_due_date ?? null)}${more}` };
    case "CANCEL_LINE":
      return { before: "ردیف فعال", after: `لغو ردیف${more}` };
    case "CANCEL_ORDER":
      return { before: orderState, after: "لغو سفارش" };
    case "HOLD":
      return { before: orderState, after: "توقف (Hold)" };
    case "RESUME":
      return { before: orderState, after: "ادامه از وضعیت پیش از توقف" };
    case "ADD_LINE":
      return { before: order ? `${toFaDigits(order.lines.filter((l) => l.status !== "REMOVED").length)} ردیف` : "—", after: `ردیف جدید${more}` };
    default:
      return { before: "—", after: "—" };
  }
}

/** The approval gates: the real PHASE_02 gates of the request and the later-phase gates without numbers. */
function Gates({ cr }: { cr: ChangeRequest | null }) {
  const planning = !cr
    ? "—"
    : !cr.planning_required
      ? "برای این نوع لازم نیست · QA: فاز ۸"
      : cr.planning_approved_at
        ? `تأیید · ${formatJalaliDateTime(cr.planning_approved_at)} · QA: فاز ۸`
        : cr.planning_rejected_at
          ? `رد · ${formatJalaliDateTime(cr.planning_rejected_at)}`
          : "در انتظار برنامه‌ریزی · QA: فاز ۸";
  const commercial = !cr ? "—" : cr.decided_at ? `تصمیم · ${formatJalaliDateTime(cr.decided_at)}` : cr.status === "DRAFT" ? "هنوز ارسال نشده" : "در انتظار مدیر بازرگانی";
  return (
    <ul className="bullets bullets--grid" data-testid="compare-gates">
      <li className="bullet">
        <strong>بازرگانی</strong>
        <p>{commercial}</p>
      </li>
      <li className="bullet">
        <strong>برنامه‌ریزی و QA</strong>
        <p>{planning}</p>
      </li>
      <li className="bullet">
        <strong>مهندسی</strong>
        <p>در دست ساخت · <bdi dir="ltr">PHASE_03/04</bdi></p>
      </li>
      <li className="bullet">
        <strong>انبار/تأمین</strong>
        <p>در دست ساخت · <bdi dir="ltr">PHASE_06</bdi></p>
      </li>
    </ul>
  );
}

// ---------------------------------------------------------------------------------------------- new
/** Kinds the order state allows (DEC-059 + amendments); the server re-checks every rule. */
function allowedKinds(o: CustomerOrder): ChangeKind[] {
  if (o.status === "CONFIRMED") return ["QTY_CHANGE", "DUE_DATE_CHANGE", "ADD_LINE", "CANCEL_LINE", "CANCEL_ORDER", "HOLD"];
  if (o.status === "RELEASED_TO_PLAN") return ["DUE_DATE_CHANGE", "HOLD"];
  if (o.status === "ON_HOLD") return o.status_before_hold === "CONFIRMED" ? ["RESUME", "CANCEL_LINE", "CANCEL_ORDER"] : ["RESUME"];
  return [];
}

function NewChange({ orderId }: { orderId: string }) {
  const { can } = useAuth();
  const q = useQuery({
    queryKey: [...K2.orders, "one", orderId],
    queryFn: async ({ signal }) => get(`/commercial/customer-orders/${orderId}`, g.order, undefined, signal),
  });
  if (!can(PERM.changeRequest)) return <ForbiddenState />;
  return (
    <section className="panel panel--wide" aria-labelledby="new-change-title" data-testid="change-new">
      <DataView query={q} loading="در حال دریافت سفارش…" errorTitle="سفارش دریافت نشد">
        {(r) => <NewChangeForm o={r.data} version={r.version ?? r.data.row_version} />}
      </DataView>
    </section>
  );
}

function NewChangeForm({ o, version }: { o: CustomerOrder; version: number }) {
  const action = useAction();
  const kinds = allowedKinds(o);
  const [kind, setKind] = useState<ChangeKind | "">(kinds[0] ?? "");
  const [lineId, setLineId] = useState<string>("");
  const [qty, setQty] = useState("");
  const [due, setDue] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const live = o.lines.filter((l) => l.status === "CONFIRMED");
  function items(): ChangeItem[] | null {
    switch (kind) {
      case "QTY_CHANGE": {
        const n = Number(qty);
        return lineId && Number.isInteger(n) && n >= 1 ? [{ line_id: lineId, quantity: n }] : null;
      }
      case "DUE_DATE_CHANGE":
        return due ? [{ line_id: lineId || null, requested_due_date: due }] : null;
      case "CANCEL_LINE":
        return lineId ? [{ line_id: lineId }] : null;
      case "ADD_LINE":
        return null; // a new line needs style / revision choice: entered on the order page in a later step
      default:
        return [];
    }
  }
  const its = items();
  const ready = kind !== "" && its !== null && reason.trim().length >= 3;
  return (
    <>
      <h2 id="new-change-title">
        درخواست تغییر برای سفارش <Num value={o.order_no} />
      </h2>
      {kinds.length === 0 ? (
        <p className="state state--empty" data-testid="state-empty">در وضعیت کنونی سفارش درخواست تغییری مجاز نیست.</p>
      ) : (
        <form
          className="form form--grid"
          onSubmit={(e) => {
            e.preventDefault();
            if (!ready) return;
            void action
              .run(
                (key) =>
                  send("/commercial/change-requests", g.cr, {
                    order_id: o.order_id,
                    order_row_version: version,
                    kind,
                    ...(its.length ? { items: its } : {}),
                    reason: reason.trim(),
                    submit: true,
                  }, key),
                [K2.changes, K2.inbox],
              )
              .then((r) => {
                if (r) navigate(`/changes/${r.data.change_request_id}`);
              });
          }}
        >
          <Field label="نوع تغییر *">
            {(id) => (
              <select id={id} className="input" value={kind} onChange={(e) => { setKind(e.target.value as ChangeKind); setLineId(""); }} data-testid="change-kind">
                {kinds.map((k) => <option key={k} value={k}>{CHANGE_KIND[k]}</option>)}
              </select>
            )}
          </Field>
          {kind === "QTY_CHANGE" || kind === "CANCEL_LINE" || kind === "DUE_DATE_CHANGE" ? (
            <Field label={kind === "DUE_DATE_CHANGE" ? "ردیف (خالی = تاریخ سربرگ سفارش)" : "ردیف *"}>
              {(id) => (
                <select id={id} className="input" value={lineId} onChange={(e) => { setLineId(e.target.value); }} data-testid="change-line">
                  <option value="">{kind === "DUE_DATE_CHANGE" ? "سربرگ سفارش" : "انتخاب کنید"}</option>
                  {live.map((l) => (
                    <option key={l.line_id} value={l.line_id}>
                      ردیف {l.line_no} · سریال {l.serial_number ?? "—"} · {l.quantity} {UOM[l.uom] ?? l.uom}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          ) : null}
          {kind === "QTY_CHANGE" ? (
            <Field label="تعداد جدید *" hint="سریال ردیف همان می‌ماند؛ فقط نسخه جدید سفارش ساخته می‌شود.">
              {(id, hintId) => <input id={id} className="input" dir="ltr" inputMode="numeric" aria-describedby={hintId} value={qty} onChange={(e) => { setQty(e.target.value.replace(/[^0-9]/g, "")); }} data-testid="change-qty" />}
            </Field>
          ) : null}
          {kind === "DUE_DATE_CHANGE" ? <JalaliDateField label="تاریخ تحویل جدید" required value={due} onChange={setDue} testId="change-due" hint="تغییر تاریخ تحویل تأیید برنامه‌ریزی هم لازم دارد." /> : null}
          {kind === "ADD_LINE" ? <p className="notice notice--info">افزودن ردیف به سفارش تأییدشده در این نسخه رابط کاربری هنوز فرم ندارد (API آماده است).</p> : null}
          {kind === "CANCEL_ORDER" || kind === "CANCEL_LINE" ? (
            <p className="notice notice--warning">سریال ردیف لغوشده «لغوشده» می‌شود و شماره آن هرگز دوباره استفاده نمی‌شود. لغو پس از ارسال به برنامه‌ریزی تا فاز ۵ مسدود است.</p>
          ) : null}
          <Field label="دلیل (در ممیزی ثبت می‌شود) *">
            {(id) => <textarea id={id} className="input" rows={3} minLength={3} maxLength={500} value={reason} onChange={(e) => { setReason(e.target.value); }} data-testid="change-reason" />}
          </Field>
          <ActionError error={action.error} />
          <div className="form__actions">
            <button type="submit" className="btn btn--primary" disabled={action.pending || !ready} data-testid="change-submit">
              {action.pending ? "در حال ثبت…" : "ثبت و ارسال برای تصمیم"}
            </button>
            <a className="btn btn--secondary" href={`#/orders/${o.order_id}`}>انصراف</a>
          </div>
        </form>
      )}
    </>
  );
}

// ------------------------------------------------------------------------------------------- detail
function ChangeDetail({ id }: { id: string }) {
  const q = useQuery({
    queryKey: [...K2.changes, "one", id],
    queryFn: async ({ signal }) => get(`/commercial/change-requests/${id}`, g.cr, undefined, signal),
  });
  return (
    <DataView query={q} loading="در حال دریافت درخواست…" errorTitle="درخواست دریافت نشد">
      {(r) => <ChangeView cr={r.data} version={r.version ?? r.data.row_version} />}
    </DataView>
  );
}

type Op = "approve" | "reject" | "plan-approve" | "plan-reject" | "apply" | "withdraw";

function ChangeView({ cr, version }: { cr: ChangeRequest; version: number }) {
  const { can, me } = useAuth();
  const action = useAction();
  const [op, setOp] = useState<Op | null>(null);
  const mine = cr.requested_by === me?.user.user_id;
  const order = useQuery({
    queryKey: [...K2.orders, "one", cr.order_id],
    // cache holds the ApiResponse (same key as the order page); this view projects .data
    queryFn: ({ signal }) => get(`/commercial/customer-orders/${cr.order_id}`, g.order, undefined, signal),
    select: (r) => r.data,
  });
  const impact = useQuery({
    queryKey: [...K2.changes, "impact", cr.change_request_id, cr.row_version],
    queryFn: async ({ signal }) => (await get(`/commercial/change-requests/${cr.change_request_id}/impact`, g.impact, undefined, signal)).data,
  });
  const planningOpen = cr.planning_required && !cr.planning_approved_by && !cr.planning_rejected_by;
  const canDecide = cr.status === "SUBMITTED" && can(PERM.changeDecide) && !mine && cr.planning_approved_by !== me?.user.user_id;
  const canPlan = planningOpen && (cr.status === "SUBMITTED" || cr.status === "APPROVED") && can(PERM.changePlanning) && !mine && cr.decided_by !== me?.user.user_id;
  const canApply = cr.status === "APPROVED" && can(PERM.changeApply) && (!cr.planning_required || !!cr.planning_approved_by);
  const canWithdraw = (cr.status === "DRAFT" || cr.status === "SUBMITTED") && mine && can(PERM.changeRequest);
  return (
    <>
      <section className="panel panel--wide" aria-labelledby="cr-title" data-testid="change-detail">
        <div className="panel__head">
          <h2 id="cr-title">
            درخواست <Num value={cr.request_no} testId="cr-no" /> · {CHANGE_KIND[cr.kind] ?? cr.kind}
          </h2>
          <StatusChip {...toneLabel(CHANGE_STATUS, cr.status)} testId="cr-status" />
        </div>
        <dl className="meta meta--rows">
          <div><dt>سفارش</dt><dd><a href={`#/orders/${cr.order_id}`}>{order.data ? <Num value={order.data.order_no} /> : <ShortId id={cr.order_id} />}</a></dd></div>
          <div><dt>بر پایه نسخه</dt><dd>{toFaDigits(cr.base_order_version)}</dd></div>
          <div><dt>دلیل</dt><dd>{cr.reason}</dd></div>
          <div><dt>درخواست‌کننده</dt><dd>{mine ? "شما" : <Requester id={cr.requested_by} name={cr.requested_by_name} />} · {cr.submitted_at ? formatJalaliDateTime(cr.submitted_at) : "ارسال نشده"}</dd></div>
          {cr.expires_at && (cr.status === "SUBMITTED" || cr.status === "APPROVED") ? <div><dt>مهلت پاسخ</dt><dd data-testid="cr-expires-at">{formatJalaliDateTime(cr.expires_at)}</dd></div> : null}
          {cr.applied_version ? <div><dt>نسخه اعمال‌شده</dt><dd data-testid="cr-applied-version">{toFaDigits(cr.applied_version)}</dd></div> : null}
        </dl>
        <BeforeAfter cr={cr} order={order.data} />
        <ol className="gates" aria-label="مراحل تأیید" data-testid="cr-gates">
          <li className={cr.decided_at ? "gates__item gates__item--done" : "gates__item"}>
            تصمیم بازرگانی: {cr.decided_at ? <>{cr.status === "REJECTED" && !cr.planning_rejected_by ? "رد" : "تأیید"} · {formatJalaliDateTime(cr.decided_at)}</> : "در انتظار"}
          </li>
          {cr.planning_required ? (
            <li className={cr.planning_approved_at || cr.planning_rejected_at ? "gates__item gates__item--done" : "gates__item"} data-testid="cr-planning-gate">
              تأیید برنامه‌ریزی (تاریخ تحویل):{" "}
              {cr.planning_approved_at ? `تأیید · ${formatJalaliDateTime(cr.planning_approved_at)}` : cr.planning_rejected_at ? `رد · ${formatJalaliDateTime(cr.planning_rejected_at)}` : "در انتظار"}
            </li>
          ) : null}
          <li className={cr.status === "APPLIED" ? "gates__item gates__item--done" : "gates__item"}>اعمال (نسخه جدید سفارش): {cr.status === "APPLIED" ? "انجام شد" : "در انتظار"}</li>
        </ol>
        <div className="actions" role="group" aria-label="اقدام‌های درخواست تغییر">
          {canDecide ? (
            <>
              <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp("approve"); }} data-testid="cr-approve">تأیید بازرگانی</button>
              <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setOp("reject"); }} data-testid="cr-reject">رد</button>
            </>
          ) : null}
          {canPlan ? (
            <>
              <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp("plan-approve"); }} data-testid="cr-plan-approve">تأیید برنامه‌ریزی</button>
              <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setOp("plan-reject"); }} data-testid="cr-plan-reject">رد برنامه‌ریزی</button>
            </>
          ) : null}
          {canApply ? <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp("apply"); }} data-testid="cr-apply">اعمال تغییر</button> : null}
          {canWithdraw ? <button type="button" className="btn btn--secondary" onClick={() => { action.reset(); setOp("withdraw"); }} data-testid="cr-withdraw">پس گرفتن</button> : null}
        </div>
        {mine && cr.status === "SUBMITTED" ? <p className="field__hint" data-testid="cr-own">این درخواست را خودتان ثبت کرده‌اید؛ تصمیم با فرد دیگری است.</p> : null}
        {!op ? <ActionError error={action.error} /> : null}
        {op ? <DecisionDialog cr={cr} version={version} op={op} action={action} onClose={() => { setOp(null); }} /> : null}
      </section>
      <section className="panel panel--wide" aria-labelledby="impact-title">
        <h2 id="impact-title">تحلیل اثر</h2>
        <DataView query={impact} loading="در حال محاسبه اثر…" errorTitle="اثر دریافت نشد">
          {(d) => (
            <>
              <ul className="counters" data-testid="cr-impact">
                <li className="counter"><span className="counter__label">ردیف‌های متأثر</span><span className="counter__value">{toFaDigits(d.lines_affected.length)}</span></li>
                <li className="counter"><span className="counter__label">سریال‌های متأثر</span><span className="counter__value">{toFaDigits(d.serials_affected.length)}</span></li>
                <li className="counter"><span className="counter__label">ردیف جدید</span><span className="counter__value">{toFaDigits(d.new_lines)}</span></li>
                <li className="counter"><span className="counter__label">Snapshot جدید سریال</span><span className="counter__value">{toFaDigits(d.snapshots_to_write)}</span></li>
              </ul>
              <LaterSections sections={d.unavailable_sections} only={["materials", "wip", "capacity", "cost"]} />
            </>
          )}
        </DataView>
      </section>
    </>
  );
}

function BeforeAfter({ cr, order }: { cr: ChangeRequest; order: CustomerOrder | undefined }) {
  if (cr.items.length === 0) return <p className="field__hint">این نوع تغییر ردیف ندارد ({CHANGE_KIND[cr.kind]}).</p>;
  const lines = new Map((order?.lines ?? []).map((l) => [l.line_id, l]));
  return (
    <table className="table table--cards" data-testid="cr-before-after">
      <caption>پیش و پس از تغییر{order && order.current_version !== cr.base_order_version ? " (سفارش از نسخه پایه جلو رفته است؛ «پیش» مقدار جاری را نشان می‌دهد)" : ""}</caption>
      <thead>
        <tr>
          <th scope="col">ردیف</th>
          <th scope="col">پیش</th>
          <th scope="col">پس</th>
        </tr>
      </thead>
      <tbody>
        {cr.items.map((it, i) => {
          const ln = it.line_id ? lines.get(it.line_id) : undefined;
          let before = "—";
          let after = "—";
          if (it.quantity !== undefined) {
            before = ln ? toFaDigits(ln.quantity) : "—";
            after = toFaDigits(it.quantity);
          } else if (it.requested_due_date !== undefined) {
            before = formatJalaliDate(ln ? ln.requested_due_date : (order?.requested_due_date ?? null));
            after = formatJalaliDate(it.requested_due_date);
          } else if (cr.kind === "CANCEL_LINE") {
            before = "فعال";
            after = "لغو";
          }
          return (
            <tr key={`${it.line_id ?? "header"}-${String(i)}`}>
              <td data-label="ردیف">{ln ? `ردیف ${toFaDigits(ln.line_no)}` : it.line_id ? <ShortId id={it.line_id} /> : "سربرگ سفارش"}</td>
              <td data-label="پیش">{before}</td>
              <td data-label="پس">{after}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function DecisionDialog({ cr, version, op, action, onClose }: { cr: ChangeRequest; version: number; op: Op; action: ReturnType<typeof useAction>; onClose: () => void }) {
  const [note, setNote] = useState("");
  const needsText = op === "reject" || op === "plan-reject" || op === "withdraw";
  const title = {
    approve: "تأیید بازرگانی درخواست",
    reject: "رد درخواست",
    "plan-approve": "تأیید برنامه‌ریزی تغییر تاریخ",
    "plan-reject": "رد برنامه‌ریزی (تاریخ قبلی می‌ماند)",
    apply: "اعمال تغییر",
    withdraw: "پس گرفتن درخواست",
  }[op];
  return (
    <Dialog title={title} onClose={onClose} testId="cr-decision-dialog">
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          const base = `/commercial/change-requests/${cr.change_request_id}`;
          const [path, body] =
            op === "approve" || op === "reject"
              ? [`${base}/decide`, { decision: op === "approve" ? "APPROVE" : "REJECT", ...(note.trim() ? { note: note.trim() } : {}) }]
              : op === "plan-approve" || op === "plan-reject"
                ? [`${base}/planning-decision`, { decision: op === "plan-approve" ? "APPROVE" : "REJECT", ...(note.trim() ? { note: note.trim() } : {}) }]
                : op === "apply"
                  ? [`${base}/apply`, note.trim() ? { note: note.trim() } : {}]
                  : [`${base}/withdraw`, { reason: note.trim() }];
          void action.run((key) => send(path, g.cr, body, key, version), [K2.changes, K2.orders, K2.serials, K2.inbox]).then((r) => {
            if (r) onClose();
          });
        }}
      >
        {op === "apply" ? <p className="lead">نسخه جدید سفارش و Snapshot جدید سریال‌های متأثر ساخته می‌شود؛ نسخه‌های قبلی تغییر نمی‌کنند.</p> : null}
        <Field label={needsText ? "دلیل (الزامی، در ممیزی ثبت می‌شود)" : "یادداشت (اختیاری)"}>
          {(id) => <textarea id={id} className="input" rows={3} maxLength={500} value={note} onChange={(e) => { setNote(e.target.value); }} data-testid="cr-note" />}
        </Field>
        <ActionError error={action.error} />
        <div className="form__actions">
          <button type="submit" className={op.includes("reject") ? "btn btn--danger" : "btn btn--primary"} disabled={action.pending || (needsText && note.trim().length < 3)} data-testid="cr-decision-submit">
            {action.pending ? "در حال ارسال…" : "ثبت"}
          </button>
          <button type="button" className="btn btn--secondary" onClick={onClose}>انصراف</button>
        </div>
      </form>
    </Dialog>
  );
}
