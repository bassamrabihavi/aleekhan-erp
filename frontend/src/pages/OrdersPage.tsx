// Page 29 «ثبت سفارش و کدگذاری» (MOCK_UI_BINDING §7.4): order list, a 4-step order wizard (header -> product /
// style / code -> quantity and dates -> server checks and send to planning), order detail with lines, validate
// (duplicate PO = acknowledged warning, DEC-058), confirm by planning (serials allocated in the same
// transaction, DEC-006 L-A; fresh MFA), release, cancel / reopen before confirmation, versions and external
// references. Every edit sends the order's If-Match; a 412 shows the "data changed" state. One Idempotency-Key per
// wizard submission, kept across retries of the same body (ID-04).
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { newIdempotencyKey } from "../api/http";
import { g, get, K2, PERM, send, type CustomerOrder, type OrderLine, type Style } from "../api/phase02";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView, ForbiddenState } from "../components/DataView";
import { Dialog } from "../components/Dialog";
import { Field, ReasonDialog } from "../components/Form";
import { Code14, CustomerName, DisabledAction, JalaliDateField, Kpi, Num, PageHead, PageInfoButtons, Representative } from "../components/Phase02";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import { formatJalaliDate, todayTehranIso } from "../lib/jalali";
import { toneLabel } from "../lib/labels";
import { ATTRIBUTE_LABEL, LINE_STATUS, ORDER_STATUS, ORDER_TYPES, REF_SYSTEMS, REF_TYPES, UOM, VERSION_REASON } from "../lib/labels02";
import { useCursor } from "../lib/queries";
import { hasReason, useCustomerNames } from "../lib/queries02";
import { navigate, segments, useRoute } from "../lib/router";
import { useAction } from "../lib/useAction";
import { Pager } from "./SecurityPage";

export function OrdersPage() {
  const { can } = useAuth();
  const route = useRoute();
  const [id] = segments(route, "/orders");
  if (!can(PERM.orderRead)) {
    return (
      <div className="page" data-testid="page-orders">
        <PageHead page="صفحه ۲۹ · فاز ۲" title="ثبت سفارش و کدگذاری" />
        <ForbiddenState />
      </div>
    );
  }
  const isNew = id === "new";
  return (
    <div className="page" data-testid="page-orders">
      <PageHead
        page="بازرگانی و ثبت سفارش · صفحه ۲۹ · فاز ۲"
        title={isNew ? "ثبت سفارش جدید و کدگذاری محصول" : "ثبت سفارش و کدگذاری"}
        lead="ثبت مرحله‌ای؛ شماره سفارش، کد ۱۴رقمی و سریال را فقط سرور می‌دهد."
        actions={
          <>
            <PageInfoButtons help={ORDERS_HELP} owner="بازرگانی و ثبت سفارش (ایجاد سریال با تأیید برنامه‌ریزی)" sources={ORDERS_SOURCES} />
            {isNew ? (
              <DisabledAction
                primary
                label="بررسی و ارسال به برنامه‌ریزی"
                reason="ابتدا پیش‌نویس سفارش را در مرحله ۱ ثبت کنید؛ بررسی و ارسال در مرحله ۴ روی صفحه همان سفارش انجام می‌شود."
                testId="order-send-disabled"
              />
            ) : null}
          </>
        }
      />
      <nav className="pagetabs" aria-label="بخش‌های ثبت سفارش">
        <a href="#/orders" className="pagetabs__item" aria-current={!id ? "page" : undefined}>فهرست سفارش‌ها</a>
        {can(PERM.orderManage) ? (
          <a href="#/orders/new" className="pagetabs__item" aria-current={isNew ? "page" : undefined} data-testid="pagetab-order-new">سفارش جدید</a>
        ) : null}
        {id && !isNew ? <span className="pagetabs__item" aria-current="page">جزئیات سفارش</span> : null}
        <a href="#/code-rules" className="pagetabs__item">قاعده کد ۱۴رقمی</a>
        <a href="#/changes" className="pagetabs__item">تغییرات سفارش</a>
      </nav>
      {isNew ? <NewOrder /> : id ? <OrderDetail id={id} /> : <OrderList />}
    </div>
  );
}

const ORDERS_HELP = (
  <>
    <p>شماره سفارش (SO-سال شمسی-شماره) و سریال‌ها را سرور می‌دهد. سریال فقط هنگام تأیید سفارش توسط برنامه‌ریزی تخصیص می‌یابد.</p>
    <p>مراحل: ۱) سربرگ سفارش و ثبت پیش‌نویس؛ ۲) محصول، استایل و کد ۱۴رقمی؛ ۳) تعداد و تاریخ؛ ۴) بررسی سرور و ارسال به برنامه‌ریزی.</p>
    <p>سفارش تأییدشده مستقیم ویرایش نمی‌شود؛ هر تغییر با «درخواست تغییر» در صفحه ۳۳ انجام می‌شود. PO تکراری فقط هشدار است و باید آگاهانه تأیید شود.</p>
  </>
);

const ORDERS_SOURCES = [
  { label: "سفارش و ردیف‌ها", detail: "سرور سامانه: /commercial/customer-orders (نسخه‌دار؛ هر ویرایش با If-Match)" },
  { label: "مشتری و برند", detail: "ثبت مشتریان سامانه (صفحه مشتریان و برندها)" },
  { label: "محصول، استایل، کد ۱۴رقمی", detail: "ثبت محصول سامانه؛ کد فقط زیر قاعده فعال DEC-005 صادر می‌شود" },
  { label: "راهکاران", detail: "فقط خواندنی؛ سامانه چیزی در راهکاران نمی‌نویسد" },
];

// ---------------------------------------------------------------------------------------------- list
function OrderList() {
  const { can } = useAuth();
  const names = useCustomerNames();
  const cursor = useCursor();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const list = useQuery({
    queryKey: [...K2.orders, "list", status, search, cursor.cursor],
    queryFn: async ({ signal }) =>
      (await get("/commercial/customer-orders", g.orderPage, { status: status || undefined, q: search || undefined, cursor: cursor.cursor, page_size: 25 }, signal)).data,
  });
  return (
    <section className="panel panel--wide" aria-labelledby="orders-title">
      <div className="panel__head">
        <h2 id="orders-title">سفارش‌ها</h2>
        {can(PERM.orderManage) ? (
          <a className="btn btn--primary" href="#/orders/new" data-testid="order-new">سفارش جدید</a>
        ) : null}
      </div>
      <form className="filters" role="search" onSubmit={(e) => { e.preventDefault(); cursor.reset(); setSearch(q.trim()); }}>
        <Field label="جستجوی شماره سفارش یا PO">
          {(id) => <input id={id} className="input" dir="ltr" maxLength={100} value={q} onChange={(e) => { setQ(e.target.value); }} data-testid="order-search" />}
        </Field>
        <Field label="وضعیت">
          {(id) => (
            <select id={id} className="input" value={status} onChange={(e) => { cursor.reset(); setStatus(e.target.value); }} data-testid="order-status-filter">
              <option value="">همه</option>
              {Object.entries(ORDER_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          )}
        </Field>
        <button type="submit" className="btn btn--secondary">جستجو</button>
      </form>
      <DataView query={list} loading="در حال دریافت سفارش‌ها…" errorTitle="سفارش‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "سفارشی پیدا نشد." }}>
        {(d) => (
          <>
            <table className="table table--cards" data-testid="orders-table">
              <caption className="sr-only">فهرست سفارش‌ها</caption>
              <thead>
                <tr>
                  <th scope="col">شماره</th>
                  <th scope="col">مشتری</th>
                  <th scope="col">PO مشتری</th>
                  <th scope="col">نوع</th>
                  <th scope="col">تاریخ سفارش</th>
                  <th scope="col">ردیف‌ها</th>
                  <th scope="col">وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((o) => (
                  <tr key={o.order_id}>
                    <td data-label="شماره"><a href={`#/orders/${o.order_id}`} data-testid="order-open"><Num value={o.order_no} /></a></td>
                    <td data-label="مشتری"><CustomerName id={o.customer_id} names={names} /></td>
                    <td data-label="PO مشتری"><Num value={o.external_po_number} /></td>
                    <td data-label="نوع">{ORDER_TYPES[o.order_type] ?? o.order_type}</td>
                    <td data-label="تاریخ سفارش">{formatJalaliDate(o.order_date)}</td>
                    <td data-label="ردیف‌ها">{toFaDigits(o.line_count)}</td>
                    <td data-label="وضعیت"><StatusChip {...toneLabel(ORDER_STATUS, o.status)} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager depth={cursor.depth} next={d.page.next_cursor} onNext={cursor.next} onPrev={cursor.prev} />
          </>
        )}
      </DataView>
    </section>
  );
}

function Steps({ current }: { current: number }) {
  const labels = ["سربرگ سفارش", "محصول، استایل و کد", "تعداد و تاریخ", "بررسی و ارسال"];
  return (
    <ol className="steps" aria-label={`مرحله ${toFaDigits(current)} از ۴`} data-testid="wizard-steps" data-fid="wizard-steps">
      {labels.map((l, i) => (
        <li key={l} className={i + 1 === current ? "steps__item steps__item--current" : i + 1 < current ? "steps__item steps__item--done" : "steps__item"} aria-current={i + 1 === current ? "step" : undefined}>
          <span className="steps__no">{toFaDigits(i + 1)}</span> {l}
        </li>
      ))}
    </ol>
  );
}

// ------------------------------------------------------------------------------------- wizard step 1
function NewOrder() {
  const { can } = useAuth();
  const action = useAction();
  const key = useRef(newIdempotencyKey());
  const [cq, setCq] = useState("");
  const [customer, setCustomer] = useState("");
  const [brand, setBrand] = useState("");
  const [type, setType] = useState("series_production");
  const [po, setPo] = useState("");
  const [program, setProgram] = useState("");
  const [rep, setRep] = useState("");
  const [quality, setQuality] = useState("");
  const [orderDate, setOrderDate] = useState<string | null>(todayTehranIso());
  const [due, setDue] = useState<string | null>(null);
  const customers = useQuery({
    queryKey: [...K2.customers, "pick", cq],
    queryFn: async ({ signal }) => (await get("/identity/customers", g.customerPage, { q: cq || undefined, status: "ACTIVE", page_size: 50 }, signal)).data,
  });
  const brands = useQuery({
    queryKey: [...K2.customers, "brands", customer],
    enabled: customer !== "",
    queryFn: async ({ signal }) => (await get(`/identity/customers/${customer}/brands`, g.brandPage, { page_size: 100 }, signal)).data,
  });
  const touch = <T,>(set: (v: T) => void) => (v: T) => {
    key.current = newIdempotencyKey(); // a different body is a different submission
    set(v);
  };
  if (!can(PERM.orderManage)) return <ForbiddenState />;
  // «آمادگی فرم»: the required fields of step 1 that are filled (computed from this form only)
  const required = [customer !== "", orderDate !== null];
  const filled = required.filter(Boolean).length;
  return (
    <>
      <ul className="kpis" data-fid="kpis" aria-label="وضعیت فرم سفارش جدید">
        <Kpi label="مرحله ثبت سفارش" value={`${toFaDigits(1)} از ${toFaDigits(4)}`} note="سربرگ سفارش" />
        <Kpi label="کد ۱۴رقمی نمونه" value="—" note="پس از انتخاب استایل (مرحله ۲)" />
        <Kpi label="استایل‌های مشابه" value="—" note="پس از انتخاب محصول (مرحله ۲)" />
        <Kpi
          label="آمادگی فرم"
          value={`${toFaDigits(filled)} از ${toFaDigits(required.length)}`}
          note="فیلدهای اجباری مرحله ۱"
          tone={filled === required.length ? "good" : undefined}
          testId="form-readiness"
        />
      </ul>
      <div className="grid-main">
        <section className="panel" aria-labelledby="new-order-title" data-testid="order-wizard" data-fid="order-wizard">
          <div className="panel__head">
            <h2 id="new-order-title">فرم مرحله‌ای ثبت سفارش</h2>
          </div>
          <Steps current={1} />
          <form
            className="form wizard-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!orderDate) return;
              void action
                .run(
                  () =>
                    send("/commercial/customer-orders", g.order, {
                      customer_id: customer,
                      brand_id: brand || null,
                      order_type: type,
                      external_po_number: po.trim() || null,
                      program_ref: program.trim() || null,
                      order_date: orderDate,
                      requested_due_date: due,
                      required_quality_requirement: quality.trim() || null,
                      customer_representative_name: rep.trim() || null,
                    }, key.current),
                  [K2.orders],
                )
                .then((r) => {
                  if (r) navigate(`/orders/${r.data.order_id}`);
                });
            }}
          >
            <div className="formgrid">
              <Field label="جستجوی مشتری">
                {(id) => <input id={id} className="input" maxLength={100} value={cq} onChange={(e) => { setCq(e.target.value); }} data-testid="wiz-customer-search" />}
              </Field>
              <Field label="مشتری *">
                {(id) => (
                  <select id={id} className="input" required value={customer} onChange={(e) => { touch(setCustomer)(e.target.value); setBrand(""); }} data-testid="wiz-customer">
                    <option value="">انتخاب کنید</option>
                    {(customers.data?.items ?? []).map((c) => <option key={c.customer_id} value={c.customer_id}>{c.display_name_fa} ({c.customer_no})</option>)}
                  </select>
                )}
              </Field>
              <Field label="برند مشتری (اختیاری)">
                {(id) => (
                  <select id={id} className="input" value={brand} disabled={!customer} onChange={(e) => { touch(setBrand)(e.target.value); }} data-testid="wiz-brand">
                    <option value="">بدون برند</option>
                    {(brands.data?.items ?? []).filter((b) => b.status === "ACTIVE").map((b) => <option key={b.brand_id} value={b.brand_id}>{b.brand_name_fa}</option>)}
                  </select>
                )}
              </Field>
              <Field label="نوع سفارش *">
                {(id) => (
                  <select id={id} className="input" required value={type} onChange={(e) => { touch(setType)(e.target.value); }} data-testid="wiz-type">
                    {Object.entries(ORDER_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                )}
              </Field>
              <Field label="شماره سفارش مشتری (PO)" hint="تکراری بودن فقط هشدار است.">
                {(id, hintId) => <input id={id} className="input" dir="ltr" maxLength={64} aria-describedby={hintId} value={po} onChange={(e) => { touch(setPo)(e.target.value); }} data-testid="wiz-po" />}
              </Field>
              <Field label="برنامه / دوره مشتری">
                {(id) => <input id={id} className="input" maxLength={64} value={program} onChange={(e) => { touch(setProgram)(e.target.value); }} />}
              </Field>
              <Field label="نام نماینده مشتری" hint="فقط نام (داده شخصی، ممیزی می‌شود).">
                {(id, hintId) => <input id={id} className="input" maxLength={200} autoComplete="off" aria-describedby={hintId} value={rep} onChange={(e) => { touch(setRep)(e.target.value); }} data-testid="wiz-rep" />}
              </Field>
              <Field label="گرید موردنیاز (متن آزاد تا DEC-019)">
                {(id) => <input id={id} className="input" maxLength={64} value={quality} onChange={(e) => { touch(setQuality)(e.target.value); }} />}
              </Field>
              <JalaliDateField label="تاریخ سفارش" required value={orderDate} onChange={touch(setOrderDate)} testId="wiz-order-date" />
              <JalaliDateField label="تاریخ تحویل درخواستی" value={due} onChange={touch(setDue)} testId="wiz-due" />
            </div>
            <ActionError error={action.error} />
            <div className="rowbuttons">
              <span className="field__hint">مشتری و برند از ثبت مشتریان سامانه انتخاب می‌شوند.</span>
              <div className="actions">
                <a className="btn btn--outline btn--compact" href="#/orders">انصراف</a>
                <DisabledAction label="مرحله قبل" reason="این مرحله اول است." testId="wiz-prev" />
                <button type="submit" className="btn btn--primary btn--compact" disabled={action.pending || !customer || !orderDate} data-testid="wiz-create">
                  {action.pending ? "در حال ثبت…" : "ثبت پیش‌نویس و مرحله بعد"}
                </button>
              </div>
            </div>
          </form>
        </section>
        <CodingPanel />
      </div>
      <div className="grid-half">
        <section className="panel" aria-labelledby="similar-title" data-fid="similar-styles">
          <div className="panel__head">
            <h2 id="similar-title">بررسی استایل‌های موجود</h2>
          </div>
          <table className="table table--plain">
            <caption className="sr-only">استایل‌های موجود محصول انتخاب‌شده</caption>
            <thead>
              <tr>
                <th scope="col">استایل</th>
                <th scope="col">ویژگی</th>
                <th scope="col">نتیجه</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={3} className="table__empty">
                  محصول هنوز انتخاب نشده است. در مرحله ۲، استایل‌های موجود همان محصول و پیشنهادهای مشابه (فقط پیشنهاد؛ ادغام انجام نمی‌شود) این‌جا می‌آیند.
                </td>
              </tr>
            </tbody>
          </table>
        </section>
        <section className="panel" aria-labelledby="checks-title" data-fid="pre-checks">
          <div className="panel__head">
            <h2 id="checks-title">کنترل‌های داده پیش از ثبت</h2>
          </div>
          <ul className="bullets">
            <li className="bullet">
              <strong>هویت محصول</strong>
              <p>فقط محصول و استایل «فعال» با نسخه فعال قابل انتخاب است؛ سرور دوباره بررسی می‌کند.</p>
            </li>
            <li className="bullet">
              <strong>استایل جدید</strong>
              <p>استایل جدید در صفحه محصولات ساخته می‌شود؛ شماره آن را سرور می‌دهد (۰۰۰۰ هرگز).</p>
            </li>
            <li className="bullet">
              <strong>ثبت نهایی</strong>
              <p>سریال فقط هنگام تأیید برنامه‌ریزی در یک تراکنش ساخته می‌شود؛ کلیک دوباره سفارش تکراری نمی‌سازد.</p>
            </li>
          </ul>
        </section>
      </div>
    </>
  );
}

/** DEC-005 (APPROVED): code = «02» + product type (2) + category (2) + product number (4) + style number (4). */
function CodingPanel() {
  const rows = [
    { part: "ماهیت", value: "02", source: "ثابت قاعده DEC-005 (محصول)" },
    { part: "نوع محصول", value: null, source: "طبقه‌بندی محصول (برگه Sorce)" },
    { part: "دسته‌بندی", value: null, source: "طبقه‌بندی استایل (برگه Sorce)" },
    { part: "شماره محصول", value: null, source: "سرور: بزرگ‌ترین شماره همان نوع + ۱" },
    { part: "شماره استایل", value: null, source: "سرور: شمارش استایل‌ها + ۱ (۰۰۰۰ هرگز)" },
  ];
  return (
    <section className="panel" aria-labelledby="coding-title" data-fid="coding-validation">
      <div className="panel__head">
        <h2 id="coding-title">کدگذاری راهکاران و اعتبارسنجی</h2>
      </div>
      <p className="ruleline">
        ساختار کد ۱۴رقمی (DEC-005): <b>ماهیت ۲ رقم + نوع ۲ + دسته ۲ + محصول ۴ + استایل ۴</b>
      </p>
      <table className="table table--plain">
        <caption className="sr-only">بخش‌های کد ۱۴رقمی این سفارش</caption>
        <thead>
          <tr>
            <th scope="col">بخش</th>
            <th scope="col">مقدار نمونه (این سفارش)</th>
            <th scope="col">منبع</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.part}>
              <td>{r.part}</td>
              <td>{r.value ? <Code14 code={r.value} /> : <span className="field__hint">مرحله ۲</span>}</td>
              <td>{r.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ruleline ruleline--warning">کد کالا ≠ شماره سریال داخلی. شماره سفارش مشتری (PO) و کد پروژه راهکاران فیلدهای جداگانه‌اند.</p>
    </section>
  );
}

// -------------------------------------------------------------------------------------------- detail
function OrderDetail({ id }: { id: string }) {
  const q = useQuery({
    queryKey: [...K2.orders, "one", id],
    queryFn: async ({ signal }) => get(`/commercial/customer-orders/${id}`, g.order, undefined, signal),
  });
  return (
    <DataView query={q} loading="در حال دریافت سفارش…" errorTitle="سفارش دریافت نشد">
      {(r) => <OrderView o={r.data} version={r.version ?? r.data.row_version} />}
    </DataView>
  );
}

function wizardStep(o: CustomerOrder): number {
  const live = o.lines.filter((l) => l.status !== "REMOVED");
  if (o.status === "DRAFT") return live.length === 0 ? 2 : 3;
  return 4;
}

type OrderOp = "validate" | "reopen" | "cancel" | "confirm" | "release";

function OrderView({ o, version }: { o: CustomerOrder; version: number }) {
  const { can } = useAuth();
  const names = useCustomerNames();
  const action = useAction();
  const [op, setOp] = useState<OrderOp | null>(null);
  const [ackDup, setAckDup] = useState(false);
  const [editing, setEditing] = useState(false);
  const dupPo = hasReason(action.error, "DUPLICATE_PO_NUMBER");
  const live = o.lines.filter((l) => l.status !== "REMOVED");
  const run = (path: string, body: unknown) =>
    action.run((key) => send(`/commercial/customer-orders/${o.order_id}/${path}`, g.order, body, key, version), [K2.orders, K2.inbox, K2.serials]);
  return (
    <>
      <section className="panel panel--wide" aria-labelledby="order-title" data-testid="order-detail">
        <div className="panel__head">
          <h2 id="order-title">
            سفارش <Num value={o.order_no} testId="order-no" />
          </h2>
          <StatusChip {...toneLabel(ORDER_STATUS, o.status)} testId="order-status" />
        </div>
        {o.status === "DRAFT" || o.status === "VALIDATED" ? <Steps current={wizardStep(o)} /> : null}
        <dl className="meta meta--rows">
          <div><dt>مشتری</dt><dd><CustomerName id={o.customer_id} names={names} /></dd></div>
          <div><dt>PO مشتری</dt><dd><Num value={o.external_po_number} /></dd></div>
          <div><dt>نوع سفارش</dt><dd>{ORDER_TYPES[o.order_type] ?? o.order_type}</dd></div>
          <div><dt>برنامه مشتری</dt><dd>{o.program_ref ?? "—"}</dd></div>
          <div><dt>تاریخ سفارش</dt><dd>{formatJalaliDate(o.order_date)}</dd></div>
          <div><dt>تاریخ تحویل درخواستی</dt><dd data-testid="order-due">{formatJalaliDate(o.requested_due_date)}</dd></div>
          <div><dt>گرید موردنیاز (متن)</dt><dd>{o.required_quality_requirement ?? "—"}</dd></div>
          <div><dt>نماینده مشتری</dt><dd><Representative value={o.customer_representative_name} /></dd></div>
          <div><dt>نسخه جاری</dt><dd data-testid="order-version">{o.current_version ? toFaDigits(o.current_version) : "— (پیش از تأیید)"}</dd></div>
          {o.hold_reason ? <div><dt>علت توقف</dt><dd>{o.hold_reason}</dd></div> : null}
          {o.cancel_reason ? <div><dt>علت لغو</dt><dd>{o.cancel_reason}</dd></div> : null}
        </dl>
        <div className="actions" role="group" aria-label="اقدام‌های سفارش">
          {o.status === "DRAFT" && can(PERM.orderManage) ? (
            <>
              <button type="button" className="btn btn--secondary" onClick={() => { action.reset(); setEditing(true); }} data-testid="order-edit">ویرایش سربرگ</button>
              <button type="button" className="btn btn--primary" disabled={action.pending || live.length === 0} onClick={() => { setAckDup(false); action.reset(); setOp("validate"); }} data-testid="order-validate">بررسی سفارش (مرحله ۴)</button>
            </>
          ) : null}
          {o.status === "VALIDATED" && can(PERM.orderManage) ? (
            <button type="button" className="btn btn--secondary" onClick={() => { action.reset(); setOp("reopen"); }} data-testid="order-reopen">بازگشت به پیش‌نویس</button>
          ) : null}
          {o.status === "VALIDATED" && can(PERM.orderConfirm) ? (
            <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp("confirm"); }} data-testid="order-confirm">تأیید سفارش و تخصیص سریال</button>
          ) : null}
          {(o.status === "DRAFT" || o.status === "VALIDATED") && can(PERM.orderManage) ? (
            <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setOp("cancel"); }} data-testid="order-cancel">لغو سفارش</button>
          ) : null}
          {o.status === "CONFIRMED" && can(PERM.orderRelease) ? (
            <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp("release"); }} data-testid="order-release">ارسال به برنامه‌ریزی</button>
          ) : null}
          {["CONFIRMED", "RELEASED_TO_PLAN", "ON_HOLD"].includes(o.status) && can(PERM.changeRequest) ? (
            <a className="btn btn--secondary" href={`#/changes/new/${o.order_id}`} data-testid="order-request-change">درخواست تغییر</a>
          ) : null}
        </div>
        {o.status === "VALIDATED" && !can(PERM.orderConfirm) ? (
          <p className="field__hint">سفارش آماده تأیید است؛ تأیید و تخصیص سریال با برنامه‌ریزی است (سازنده سفارش آن را تأیید نمی‌کند).</p>
        ) : null}
        {op === "validate" ? (
          <Dialog title="بررسی سفارش پیش از ارسال" onClose={() => { setOp(null); }} testId="validate-dialog">
            <div className="form">
              <p className="lead">سرور مشتری، برند، نوع سفارش و همه ردیف‌ها (استایل و نسخه فعال، کد) را بررسی می‌کند.</p>
              {dupPo ? (
                <label className="check notice notice--warning" data-testid="po-dup-warning">
                  <input type="checkbox" checked={ackDup} onChange={(e) => { setAckDup(e.target.checked); }} data-testid="po-dup-ack" />
                  این شماره PO برای همین مشتری قبلاً ثبت شده است. می‌دانم و تأیید می‌کنم که سفارش جداگانه است.
                </label>
              ) : (
                <ActionError error={action.error} />
              )}
              <div className="form__actions">
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={action.pending || (dupPo && !ackDup)}
                  onClick={() => {
                    void run("validate", ackDup ? { acknowledge_possible_duplicate: true } : {}).then((r) => {
                      if (r) setOp(null);
                    });
                  }}
                  data-testid="validate-submit"
                >
                  {action.pending ? "در حال بررسی…" : "بررسی و آماده ارسال"}
                </button>
                <button type="button" className="btn btn--secondary" onClick={() => { setOp(null); }}>انصراف</button>
              </div>
            </div>
          </Dialog>
        ) : null}
        {op === "confirm" || op === "release" ? (
          <Dialog title={op === "confirm" ? "تأیید سفارش و تخصیص سریال" : "ارسال به برنامه‌ریزی"} onClose={() => { setOp(null); }} testId="confirm-dialog">
            <div className="form">
              <p className="lead">
                {op === "confirm"
                  ? `برای هر ردیف یک سریال در همان تراکنش تخصیص می‌یابد (${toFaDigits(live.length)} ردیف). این اقدام تأیید دومرحله‌ای تازه لازم دارد و سازنده سفارش نمی‌تواند آن را انجام دهد.`
                  : "پس از ارسال، فقط تغییر تاریخ تحویل و توقف/ادامه با درخواست تغییر ممکن است."}
              </p>
              <ActionError error={action.error} />
              <div className="form__actions">
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={action.pending}
                  onClick={() => {
                    void run(op === "confirm" ? "confirm" : "release-to-plan", {}).then((r) => {
                      if (r) setOp(null);
                    });
                  }}
                  data-testid="confirm-submit"
                >
                  {action.pending ? "در حال انجام…" : op === "confirm" ? "تأیید و تخصیص سریال" : "ارسال"}
                </button>
                <button type="button" className="btn btn--secondary" onClick={() => { setOp(null); }}>انصراف</button>
              </div>
            </div>
          </Dialog>
        ) : null}
        {op === "reopen" || op === "cancel" ? (
          <ReasonDialog
            title={op === "reopen" ? "بازگشت به پیش‌نویس" : "لغو سفارش (پیش از تأیید)"}
            submitLabel={op === "reopen" ? "بازگشت" : "لغو سفارش"}
            danger={op === "cancel"}
            action={action}
            onClose={() => { setOp(null); }}
            onSubmit={async (reason) => (await run(op, { reason })) !== undefined}
          />
        ) : null}
        {!op ? <ActionError error={action.error} /> : null}
        {editing ? <EditHeader o={o} version={version} onClose={() => { setEditing(false); }} /> : null}
      </section>
      <Lines o={o} version={version} />
      <Versions o={o} />
      <ExternalRefs targetType="customer_order" targetId={o.order_id} />
    </>
  );
}

function EditHeader({ o, version, onClose }: { o: CustomerOrder; version: number; onClose: () => void }) {
  const action = useAction();
  const [po, setPo] = useState(o.external_po_number ?? "");
  const [program, setProgram] = useState(o.program_ref ?? "");
  const [due, setDue] = useState<string | null>(o.requested_due_date);
  const [quality, setQuality] = useState(o.required_quality_requirement ?? "");
  return (
    <Dialog title="ویرایش سربرگ سفارش (پیش‌نویس)" onClose={onClose} testId="order-edit-dialog">
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          void action
            .run(
              (key) =>
                send(`/commercial/customer-orders/${o.order_id}`, g.order, {
                  external_po_number: po.trim() || null,
                  program_ref: program.trim() || null,
                  requested_due_date: due,
                  required_quality_requirement: quality.trim() || null,
                }, key, version, "PATCH"),
              [K2.orders],
            )
            .then((r) => {
              if (r) onClose();
            });
        }}
      >
        <Field label="شماره سفارش مشتری (PO)">
          {(id) => <input id={id} className="input" dir="ltr" maxLength={64} value={po} onChange={(e) => { setPo(e.target.value); }} data-testid="edit-po" />}
        </Field>
        <Field label="برنامه / دوره مشتری">
          {(id) => <input id={id} className="input" maxLength={64} value={program} onChange={(e) => { setProgram(e.target.value); }} />}
        </Field>
        <JalaliDateField label="تاریخ تحویل درخواستی" value={due} onChange={setDue} />
        <Field label="گرید موردنیاز (متن)">
          {(id) => <input id={id} className="input" maxLength={64} value={quality} onChange={(e) => { setQuality(e.target.value); }} />}
        </Field>
        <ActionError error={action.error} />
        <div className="form__actions">
          <button type="submit" className="btn btn--primary" disabled={action.pending} data-testid="edit-submit">ذخیره</button>
          <button type="button" className="btn btn--secondary" onClick={onClose}>انصراف</button>
        </div>
      </form>
    </Dialog>
  );
}

// --------------------------------------------------------------------------------------------- lines
function Lines({ o, version }: { o: CustomerOrder; version: number }) {
  const { can } = useAuth();
  const action = useAction();
  const [remove, setRemove] = useState<OrderLine | null>(null);
  const editable = o.status === "DRAFT" && can(PERM.orderManage);
  const live = o.lines.filter((l) => l.status !== "REMOVED");
  return (
    <section className="panel panel--wide" aria-labelledby="lines-title">
      <h2 id="lines-title">ردیف‌های سفارش</h2>
      {live.length === 0 ? (
        <p className="state state--empty" data-testid="state-empty">هنوز ردیفی ندارد. محصول و استایل را انتخاب کنید (مرحله ۲).</p>
      ) : (
        <table className="table table--cards" data-testid="lines-table">
          <caption className="sr-only">ردیف‌های سفارش</caption>
          <thead>
            <tr>
              <th scope="col">ردیف</th>
              <th scope="col">کد ۱۴رقمی</th>
              <th scope="col">تعداد</th>
              <th scope="col">تحویل</th>
              <th scope="col">وضعیت</th>
              <th scope="col">سریال</th>
              <th scope="col"><span className="sr-only">اقدام</span></th>
            </tr>
          </thead>
          <tbody>
            {o.lines.map((ln) => (
              <tr key={ln.line_id}>
                <td data-label="ردیف">{toFaDigits(ln.line_no)}</td>
                <td data-label="کد ۱۴رقمی"><Code14 code={ln.product_code} /></td>
                <td data-label="تعداد">{toFaDigits(ln.quantity)} {UOM[ln.uom] ?? ln.uom}</td>
                <td data-label="تحویل">{formatJalaliDate(ln.requested_due_date)}</td>
                <td data-label="وضعیت"><StatusChip {...toneLabel(LINE_STATUS, ln.status)} /></td>
                <td data-label="سریال">
                  {ln.serial_id ? <a href={`#/serials/${ln.serial_id}`} data-testid="line-serial"><Num value={ln.serial_number} /></a> : "—"}
                </td>
                <td data-label="اقدام">
                  {editable && ln.status === "OPEN" ? (
                    <button type="button" className="btn btn--danger-outline btn--small" onClick={() => { action.reset(); setRemove(ln); }}>حذف ردیف</button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editable ? <AddLine o={o} version={version} /> : null}
      {remove ? (
        <ReasonDialog
          title={`حذف ردیف ${toFaDigits(remove.line_no)}`}
          submitLabel="حذف"
          danger
          action={action}
          onClose={() => { setRemove(null); }}
          onSubmit={async (reason) =>
            (await action.run((key) => send(`/commercial/customer-orders/${o.order_id}/lines/${remove.line_id}/remove`, g.order, { reason }, key, version), [K2.orders])) !== undefined
          }
        />
      ) : null}
    </section>
  );
}

function AddLine({ o, version }: { o: CustomerOrder; version: number }) {
  const action = useAction();
  const [pq, setPq] = useState("");
  const [productId, setProductId] = useState("");
  const [styleId, setStyleId] = useState("");
  const [codeId, setCodeId] = useState("");
  const [qty, setQty] = useState("");
  const [due, setDue] = useState<string | null>(o.requested_due_date);
  const products = useQuery({
    queryKey: [...K2.products, "pick", pq],
    queryFn: async ({ signal }) => (await get("/identity/products", g.productPage, { q: pq || undefined, status: "ACTIVE", page_size: 50 }, signal)).data,
  });
  const styles = useQuery({
    queryKey: [...K2.styles, "of", productId],
    enabled: productId !== "",
    queryFn: async ({ signal }) => (await get(`/identity/products/${productId}/styles`, g.stylePage, { page_size: 100 }, signal)).data,
  });
  const style: Style | undefined = styles.data?.items.find((s) => s.style_id === styleId);
  const revisions = useQuery({
    queryKey: [...K2.styles, "revisions", styleId],
    enabled: styleId !== "",
    queryFn: async ({ signal }) => (await get(`/identity/styles/${styleId}/revisions`, g.revisionPage, { page_size: 100 }, signal)).data,
  });
  const codes = useQuery({
    queryKey: [...K2.codes, "of", styleId],
    enabled: styleId !== "",
    queryFn: async ({ signal }) => (await get("/identity/product-codes", g.codePage, { style_id: styleId, page_size: 25 }, signal)).data,
  });
  const active = revisions.data?.items.find((r) => r.status === "ACTIVE");
  const n = Number(qty);
  const ok = style !== undefined && active !== undefined && Number.isInteger(n) && n >= 1;
  return (
    <form
      className="form form--grid subsection"
      aria-labelledby="add-line-title"
      onSubmit={(e) => {
        e.preventDefault();
        if (!ok) return;
        void action
          .run(
            (key) =>
              send(`/commercial/customer-orders/${o.order_id}/lines`, g.order, {
                style_id: styleId,
                style_revision_id: active.style_revision_id,
                product_code_id: codeId || null,
                quantity: n,
                requested_due_date: due,
              }, key, version),
            [K2.orders],
          )
          .then((r) => {
            if (r) {
              setQty("");
              setStyleId("");
              setCodeId("");
            }
          });
      }}
      data-testid="add-line"
    >
      <h3 id="add-line-title">افزودن ردیف (مرحله ۲ و ۳)</h3>
      <Field label="جستجوی محصول">
        {(id) => <input id={id} className="input" maxLength={100} value={pq} onChange={(e) => { setPq(e.target.value); }} data-testid="line-product-search" />}
      </Field>
      <Field label="محصول (فعال) *">
        {(id) => (
          <select id={id} className="input" required value={productId} onChange={(e) => { setProductId(e.target.value); setStyleId(""); setCodeId(""); }} data-testid="line-product">
            <option value="">انتخاب کنید</option>
            {(products.data?.items ?? []).map((p) => <option key={p.product_id} value={p.product_id}>{p.name_fa} ({p.product_no})</option>)}
          </select>
        )}
      </Field>
      <Field label="استایل (فعال) *">
        {(id) => (
          <select id={id} className="input" required value={styleId} disabled={!productId} onChange={(e) => { setStyleId(e.target.value); setCodeId(""); }} data-testid="line-style">
            <option value="">انتخاب کنید</option>
            {(styles.data?.items ?? []).filter((s) => s.status === "ACTIVE").map((s) => <option key={s.style_id} value={s.style_id}>{s.style_no} — {s.name_fa}</option>)}
          </select>
        )}
      </Field>
      {styleId ? (
        <div className="field" data-testid="line-revision">
          <span className="field__label">نسخه فعال استایل (رنگ و جنس)</span>
          {active ? (
            <span>
              R{toFaDigits(active.revision_no)} ·{" "}
              {Object.entries(active.attributes).filter(([, v]) => v).map(([k, v]) => `${ATTRIBUTE_LABEL[k] ?? k}: ${String(v)}`).join(" · ") || "بدون ویژگی"}
            </span>
          ) : (
            <span className="field__error">این استایل نسخه فعال ندارد؛ ابتدا در صفحه محصولات نسخه را فعال کنید.</span>
          )}
        </div>
      ) : null}
      <Field label="کد ۱۴رقمی (اختیاری)">
        {(id) => (
          <select id={id} className="input" dir="ltr" value={codeId} disabled={!styleId} onChange={(e) => { setCodeId(e.target.value); }} data-testid="line-code">
            <option value="">بدون کد</option>
            {(codes.data?.items ?? []).filter((c) => c.status === "RESERVED" || c.status === "ACTIVE").map((c) => <option key={c.product_code_id} value={c.product_code_id}>{c.code}</option>)}
          </select>
        )}
      </Field>
      <Field label="تعداد *">
        {(id) => <input id={id} className="input" dir="ltr" inputMode="numeric" required value={qty} onChange={(e) => { setQty(e.target.value.replace(/[^0-9]/g, "")); }} data-testid="line-qty" />}
      </Field>
      <JalaliDateField label="تاریخ تحویل ردیف" value={due} onChange={setDue} testId="line-due" />
      <ActionError error={action.error} />
      <div className="form__actions">
        <button type="submit" className="btn btn--primary" disabled={action.pending || !ok} data-testid="line-add">افزودن ردیف</button>
      </div>
    </form>
  );
}

// ------------------------------------------------------------------------------------------ versions
function Versions({ o }: { o: CustomerOrder }) {
  const list = useQuery({
    queryKey: [...K2.orders, "versions", o.order_id, o.current_version],
    queryFn: async ({ signal }) => (await get(`/commercial/customer-orders/${o.order_id}/versions`, g.versionPage, { page_size: 100 }, signal)).data,
  });
  return (
    <section className="panel panel--wide" aria-labelledby="versions-title">
      <h2 id="versions-title">نسخه‌های سفارش</h2>
      <DataView query={list} loading="در حال دریافت نسخه‌ها…" errorTitle="نسخه‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "نسخه ۱ هنگام تأیید سفارش ساخته می‌شود." }}>
        {(d) => (
          <ol className="timeline" data-testid="versions-list">
            {d.items.map((v) => (
              <li key={v.version}>
                <strong>نسخه {toFaDigits(v.version)}</strong> — {VERSION_REASON[v.reason] ?? v.reason} · {formatJalaliDateTime(v.created_at)}
                {v.change_request_id ? <> · <a href={`#/changes/${v.change_request_id}`}>درخواست تغییر</a></> : null}
              </li>
            ))}
          </ol>
        )}
      </DataView>
    </section>
  );
}

// ---------------------------------------------------------------------------------- external refs
// REV-0252: the title names the target, so two panels on one page (serial + order, page 2) are distinct
const REFS_TITLE: Record<string, string> = {
  serial: "ارجاع‌های بیرونی سریال",
  customer_order: "ارجاع‌های بیرونی سفارش",
};
export function ExternalRefs({ targetType, targetId }: { targetType: string; targetId: string }) {
  const { can } = useAuth();
  const action = useAction();
  const [ns, setNs] = useState("rahkaran_project_code");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [system, setSystem] = useState("RAHKARAN");
  const list = useQuery({
    queryKey: [...K2.refs, targetType, targetId],
    enabled: can(PERM.refRead),
    queryFn: async ({ signal }) => (await get("/identity/external-refs", g.extRefPage, { target_type: targetType, target_id: targetId, page_size: 50 }, signal)).data,
  });
  if (!can(PERM.refRead)) return null;
  return (
    <section className="panel panel--wide" aria-labelledby={`refs-${targetId}`}>
      <h2 id={`refs-${targetId}`}>{REFS_TITLE[targetType] ?? "ارجاع‌های بیرونی"}</h2>
      <DataView query={list} loading="در حال دریافت ارجاع‌ها…" errorTitle="ارجاع‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "ارجاع بیرونی ثبت نشده است." }}>
        {(d) => (
          <ul className="list" data-testid="refs-list">
            {d.items.map((r) => (
              <li key={r.external_ref_id}>
                {REF_TYPES[r.namespace] ?? r.namespace} ({REF_SYSTEMS[r.system] ?? r.system}): <Num value={r.value} />
                {r.valid_to ? " · پایان‌یافته" : ""}
              </li>
            ))}
          </ul>
        )}
      </DataView>
      {can(PERM.refManage) ? (
        <form
          className="form form--grid"
          onSubmit={(e) => {
            e.preventDefault();
            void action
              .run((key) => send("/identity/external-refs", g.extRef, { target_type: targetType, target_id: targetId, system, namespace: ns, value: value.trim(), reason: reason.trim() }, key), [K2.refs])
              .then((r) => {
                if (r) {
                  setValue("");
                  setReason("");
                }
              });
          }}
        >
          <Field label="نوع ارجاع">
            {(id) => (
              <select id={id} className="input" value={ns} onChange={(e) => { setNs(e.target.value); }}>
                {Object.entries(REF_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            )}
          </Field>
          <Field label="سامانه مبدأ">
            {(id) => (
              <select id={id} className="input" value={system} onChange={(e) => { setSystem(e.target.value); }}>
                {Object.entries(REF_SYSTEMS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            )}
          </Field>
          <Field label="مقدار (همان‌طور که هست)">
            {(id) => <input id={id} className="input" dir="ltr" maxLength={64} value={value} onChange={(e) => { setValue(e.target.value); }} data-testid="ref-value" />}
          </Field>
          <Field label="دلیل">
            {(id) => <input id={id} className="input" maxLength={500} value={reason} onChange={(e) => { setReason(e.target.value); }} data-testid="ref-reason" />}
          </Field>
          <ActionError error={action.error} />
          <div className="form__actions">
            <button type="submit" className="btn btn--secondary" disabled={action.pending || !value.trim() || reason.trim().length < 3} data-testid="ref-add">ثبت ارجاع</button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
