// Pages 1 and 2 «مرکز کنترل سریال» (DEC-027 P-A, employer decision 2026-11-15; MOCK_UI_BINDING §7.1/§7.2), built
// from the mobile images with PHASE_02 data ONLY:
//   page 1 (tab «خلاصه») - serial header (number, product, code, customer / brand, status, quantity, required
//     grade text, program), change requests of the serial; the production stages, active problems, progress,
//     materials, location and quality sections are later phases and show the placeholder WITHOUT numbers.
//   page 2 (tab «سفارش») - order header, lines, the serial's snapshots, order versions, external references and
//     the audited timeline.
// No sample number of the images is ever shown (rule 1/2).
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { g, get, K2, PERM, type CustomerOrder, type Serial, type SerialTracking } from "../api/phase02";
import { useAuth } from "../auth/context";
import { DataView, ForbiddenState } from "../components/DataView";
import { Field, ShortId, TabPanel, Tabs } from "../components/Form";
import { Code14, CustomerName, LATER_TEXT, LaterSection, Num, PageHead, Representative } from "../components/Phase02";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import { formatJalaliDate } from "../lib/jalali";
import { toneLabel } from "../lib/labels";
import { ATTRIBUTE_LABEL, CHANGE_KIND, CHANGE_STATUS, LINE_STATUS, ORDER_STATUS, ORDER_TYPES, SERIAL_STATUS, TRACKING_EVENT, UOM, VERSION_REASON } from "../lib/labels02";
import { useCursor } from "../lib/queries";
import { useCustomerNames } from "../lib/queries02";
import { segments, useRoute } from "../lib/router";
import { ExternalRefs } from "./OrdersPage";
import { Pager } from "./SecurityPage";

export function SerialCenterPage() {
  const { can } = useAuth();
  const route = useRoute();
  const [id] = segments(route, "/serials");
  if (!can(PERM.serialRead)) {
    return (
      <div className="page" data-testid="page-serials">
        <PageHead page="صفحه ۱ و ۲ · فاز ۲" title="مرکز کنترل سریال" />
        <ForbiddenState />
      </div>
    );
  }
  return <div className="page" data-testid="page-serials">{id ? <SerialView id={id} /> : <SerialSearch />}</div>;
}

function SerialSearch() {
  const names = useCustomerNames();
  const cursor = useCursor();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const digits = /^[0-9]{0,32}$/.test(q);
  const list = useQuery({
    queryKey: [...K2.serials, "list", search, status, cursor.cursor],
    queryFn: async ({ signal }) =>
      (await get("/identity/serials", g.serialPage, { q: search || undefined, status: status || undefined, cursor: cursor.cursor, page_size: 25 }, signal)).data,
  });
  return (
    <>
      <PageHead page="صفحه ۱ و ۲ · فاز ۲" title="مرکز کنترل سریال" lead="سریال‌ها فقط هنگام تأیید سفارش ساخته می‌شوند. شماره سریال دقیقاً همان‌طور که سرور می‌دهد نمایش داده می‌شود." />
      <section className="panel panel--wide" aria-labelledby="serials-title">
        <h2 id="serials-title">جستجوی سریال</h2>
        <form className="filters" role="search" onSubmit={(e) => { e.preventDefault(); if (digits) { cursor.reset(); setSearch(q); } }}>
          <Field label="شماره سریال (ابتدای شماره)" hint="فقط رقم لاتین؛ رقم فارسی تبدیل نمی‌شود.">
            {(id, hintId) => <input id={id} className="input" dir="ltr" inputMode="numeric" maxLength={32} aria-describedby={hintId} aria-invalid={!digits} value={q} onChange={(e) => { setQ(e.target.value); }} data-testid="serial-search" />}
          </Field>
          <Field label="وضعیت">
            {(id) => (
              <select id={id} className="input" value={status} onChange={(e) => { cursor.reset(); setStatus(e.target.value); }}>
                <option value="">همه</option>
                <option value="ALLOCATED">تخصیص‌یافته</option>
                <option value="CANCELLED">لغوشده</option>
              </select>
            )}
          </Field>
          <button type="submit" className="btn btn--secondary" disabled={!digits} data-testid="serial-search-submit">جستجو</button>
        </form>
        <DataView query={list} loading="در حال دریافت سریال‌ها…" errorTitle="سریال‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: search ? "سریالی با این شماره پیدا نشد." : "هنوز سریالی تخصیص نیافته است.", hint: "سریال پس از تأیید سفارش توسط برنامه‌ریزی ساخته می‌شود." }}>
          {(d) => (
            <>
              <ul className="cards" data-testid="serials-list">
                {d.items.map((s) => (
                  <li key={s.serial_id} className="card">
                    <a href={`#/serials/${s.serial_id}`} className="card__link" data-testid="serial-open">
                      سریال <Num value={s.serial_number} />
                    </a>
                    <span><CustomerName id={s.customer_id} names={names} /> · <Code14 code={s.product_code} /></span>
                    <StatusChip {...toneLabel(SERIAL_STATUS, s.status)} />
                  </li>
                ))}
              </ul>
              <Pager depth={cursor.depth} next={d.page.next_cursor} onNext={cursor.next} onPrev={cursor.prev} />
            </>
          )}
        </DataView>
      </section>
    </>
  );
}

/** The 13 sections of the serial control center (concept pages 1/2). Only «خلاصه», «سفارش» and «تاریخچه» carry
 * PHASE_02 data; every other tab is a later phase and shows the placeholder without numbers (DEC-027). */
const SERIAL_TABS: { id: string; label: string; phase?: string }[] = [
  { id: "summary", label: "خلاصه" },
  { id: "order", label: "سفارش" },
  { id: "planning", label: "برنامه‌ریزی", phase: "PHASE_05" },
  { id: "engineering", label: "مهندسی", phase: "PHASE_03 / PHASE_04" },
  { id: "materials", label: "مواد و انبار", phase: "PHASE_06" },
  { id: "cutting", label: "برش", phase: "PHASE_07" },
  { id: "production", label: "تولید", phase: "PHASE_07" },
  { id: "quality", label: "کیفیت", phase: "PHASE_08" },
  { id: "dispatch", label: "محصول و ارسال", phase: "PHASE_09" },
  { id: "cost", label: "بهای تمام‌شده", phase: "PHASE_10" },
  { id: "tasks", label: "تسک‌ها", phase: "PHASE_05" },
  { id: "documents", label: "اسناد", phase: "PHASE_03 / PHASE_04" },
  { id: "history", label: "تاریخچه" },
];

function SerialView({ id }: { id: string }) {
  const { can } = useAuth();
  const [tab, setTab] = useState("summary");
  const tracking = useQuery({
    queryKey: [...K2.serials, "tracking", id],
    queryFn: async ({ signal }) => (await get(`/identity/serials/${id}/tracking`, g.serialTracking, undefined, signal)).data,
  });
  const orderId = tracking.data?.serial.order_id ?? null;
  const order = useQuery({
    queryKey: [...K2.orders, "one", orderId],
    enabled: orderId !== null && can(PERM.orderRead),
    // cache holds the ApiResponse (same key as the order page); this view projects .data
    queryFn: ({ signal }) => get(`/commercial/customer-orders/${String(orderId)}`, g.order, undefined, signal),
    select: (r) => r.data,
  });
  const current = SERIAL_TABS.find((t) => t.id === tab) ?? SERIAL_TABS[0];
  return (
    <DataView query={tracking} loading="در حال دریافت سریال…" errorTitle="سریال دریافت نشد">
      {(t) => (
        <div className="serial-center">
          <div className="serial-top">
            <div className="serial-actions" role="group" aria-label="اقدام‌های برنامه‌ریزی سریال" data-fid="header-actions">
              {["تصمیم برنامه‌ریزی", "تغییر اولویت", "Fast Track", "سناریو", "بیشتر"].map((l) => (
                <button key={l} type="button" className="btn btn--outline btn--compact" disabled title="در دست ساخت — فاز ۵ (برنامه‌ریزی)" aria-describedby="serial-actions-later">
                  {l}
                </button>
              ))}
              <span id="serial-actions-later" className="serial-actions__note">
                {LATER_TEXT} · <bdi dir="ltr">PHASE_05</bdi>
              </span>
            </div>
            <ul className="date-cards" aria-label="تاریخ‌های تعهد و پیش‌بینی" data-fid="date-cards">
              {["تعهد", "Forecast", "اختلاف"].map((l) => (
                <li key={l} className="date-card" data-fid-item title="فاز مالک: PHASE_05">
                  <span className="date-card__label">{l}</span>
                  <span className="date-card__value">در دست ساخت</span>
                </li>
              ))}
            </ul>
          </div>
          <SerialHeader s={t.serial} order={order.data} />
          <LaterSection title="مراحل تولید سریال" detail="مواد و انبار ← مهندسی ← تأمین ← برش ← دوخت ← کنترل کیفیت ← آماده محصول" phase="PHASE_03 … PHASE_09" fid="stage-flow" className="later--inline" />
          <Tabs tabs={SERIAL_TABS.map(({ id: tid, label }) => ({ id: tid, label }))} active={tab} onChange={setTab} label="بخش‌های مرکز کنترل سریال" fid="tabs" />
          <TabPanel id={tab}>
            {tab === "summary" ? (
              <SummaryTab t={t} />
            ) : tab === "order" ? (
              <OrderTab t={t} order={order.data} orderLoading={order.isPending && order.fetchStatus !== "idle"} />
            ) : tab === "history" ? (
              <section className="panel" aria-labelledby="hist-title" data-testid="serial-history">
                <h2 id="hist-title">تاریخچه رویدادها</h2>
                <EventList t={t} />
              </section>
            ) : current?.phase ? (
              <LaterSection title={`بخش ${current.label} سریال`} phase={current.phase} />
            ) : null}
          </TabPanel>
        </div>
      )}
    </DataView>
  );
}

function SerialHeader({ s, order }: { s: Serial; order: CustomerOrder | undefined }) {
  const names = useCustomerNames();
  const { can } = useAuth();
  const style = useQuery({
    queryKey: [...K2.styles, "one", s.style_id],
    enabled: can(PERM.productRead),
    queryFn: ({ signal }) => get(`/identity/styles/${s.style_id}`, g.style, undefined, signal),
    select: (r) => r.data,
  });
  const product = useQuery({
    queryKey: [...K2.products, "one", style.data?.product_id],
    enabled: !!style.data,
    queryFn: ({ signal }) => get(`/identity/products/${String(style.data?.product_id)}`, g.product, undefined, signal),
    select: (r) => r.data,
  });
  const brands = useQuery({
    queryKey: [...K2.customers, "brands", s.customer_id],
    enabled: !!order?.brand_id && can(PERM.customerRead),
    queryFn: async ({ signal }) => (await get(`/identity/customers/${s.customer_id}/brands`, g.brandPage, { page_size: 100 }, signal)).data,
  });
  // colour / material of the serial's own style revision (fixed when the serial was committed), never the
  // style's current revision
  const revisions = useQuery({
    queryKey: [...K2.styles, "revisions", s.style_id],
    enabled: can(PERM.productRead),
    queryFn: async ({ signal }) => (await get(`/identity/styles/${s.style_id}/revisions`, g.revisionPage, { page_size: 100 }, signal)).data,
  });
  const rev = revisions.data?.items.find((r) => r.style_revision_id === s.style_revision_id);
  const attr = (k: "colour_fa" | "main_material_fa") => rev?.attributes[k] ?? (revisions.isPending && can(PERM.productRead) ? "…" : "—");
  const line = order?.lines.find((l) => l.serial_id === s.serial_id);
  const brand = brands.data?.items.find((b) => b.brand_id === order?.brand_id);
  return (
    <section className="serial-head panel" aria-labelledby="serial-title" data-testid="serial-header" data-fid="serial-header">
      <div className="serial-head__main">
        <p className="eyebrow">صفحه ۱ و ۲ · مرکز کنترل سریال · فاز ۲</p>
        <div className="serial-head__title">
          <h1 id="serial-title">
            سریال <Num value={s.serial_number} testId="serial-number" />
          </h1>
          <StatusChip {...toneLabel(SERIAL_STATUS, s.status)} testId="serial-status" />
        </div>
        <p className="serial-head__product">
          {product.data?.name_fa ?? "—"}
          {style.data ? <> · {style.data.name_fa}</> : null}
        </p>
      </div>
      <div className="serial-head__chips">
        <span className="chip chip--neutral chip--inline"><CustomerName id={s.customer_id} names={names} /></span>
        {brand ? <span className="chip chip--info chip--inline">{brand.brand_name_fa}</span> : null}
        {order?.required_quality_requirement ? <span className="chip chip--warning chip--inline" title="متن گرید موردنیاز (مقایسه با گرید تا DEC-019 نیست)">گرید: {order.required_quality_requirement}</span> : null}
      </div>
      <dl className="serial-head__facts">
        <div><dt>کد محصول</dt><dd><Code14 code={s.product_code} copy testId="serial-code" /></dd></div>
        <div><dt>استایل</dt><dd><Num value={style.data?.style_no} /></dd></div>
        <div><dt>تعداد سفارش</dt><dd data-testid="serial-qty">{line ? `${toFaDigits(line.quantity)} ${UOM[line.uom] ?? line.uom}` : "—"}</dd></div>
        <div><dt>رنگ</dt><dd title={attr("colour_fa")}>{attr("colour_fa")}</dd></div>
        <div><dt>جنس</dt><dd title={attr("main_material_fa")}>{attr("main_material_fa")}</dd></div>
        <div><dt>برنامه مشتری</dt><dd>{order?.program_ref ?? "—"}</dd></div>
        <div className="fact--wide"><dt>تحویل درخواستی</dt><dd>{formatJalaliDate(line?.requested_due_date ?? order?.requested_due_date ?? null)}</dd></div>
        <div className="fact--wide"><dt>تخصیص</dt><dd>{formatJalaliDateTime(s.allocated_at)}</dd></div>
      </dl>
    </section>
  );
}

/** «تصمیم‌ها و پیگیری‌ها»: the serial's change requests (PHASE_02), tasks and risks (later phases). */
function SidePanel({ serialId }: { serialId: string }) {
  const { can } = useAuth();
  const changes = useQuery({
    queryKey: [...K2.changes, "serial", serialId],
    enabled: can(PERM.changeRead),
    queryFn: async ({ signal }) => (await get("/commercial/change-requests", g.crPage, { serial_id: serialId, page_size: 25 }, signal)).data,
  });
  return (
    <aside className="panel serial-side" aria-labelledby="side-title" data-fid="side-panel">
      <div className="panel__head">
        <h2 id="side-title">تصمیم‌ها و پیگیری‌ها</h2>
        {can(PERM.changeRead) ? <a href="#/changes" className="btn btn--link">مشاهده همه</a> : null}
      </div>
      <p className="serial-side__sub">درخواست‌های تغییر این سریال</p>
      {!can(PERM.changeRead) ? (
        <p className="field__hint">برای دیدن درخواست‌های تغییر مجوز ندارید.</p>
      ) : (
        <DataView query={changes} loading="در حال دریافت درخواست‌ها…" errorTitle="درخواست‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "درخواست تغییری برای این سریال ثبت نشده است." }}>
          {(d) => (
            <ul className="cards serial-side__list" data-testid="serial-changes">
              {d.items.map((c) => (
                <li key={c.change_request_id} className="card">
                  <a href={`#/changes/${c.change_request_id}`} className="card__link">
                    <Num value={c.request_no} /> · {CHANGE_KIND[c.kind] ?? c.kind}
                  </a>
                  <StatusChip {...toneLabel(CHANGE_STATUS, c.status)} />
                </li>
              ))}
            </ul>
          )}
        </DataView>
      )}
      <div className="serial-side__laters">
      <div className="serial-side__later">
        <h3>تسک‌های نزدیک موعد</h3>
        <p>
          در دست ساخت · <bdi dir="ltr">PHASE_05</bdi>
        </p>
      </div>
      <div className="serial-side__later">
        <h3>ریسک‌ها</h3>
        <p>
          در دست ساخت · <bdi dir="ltr">PHASE_05</bdi>
        </p>
      </div>
      </div>
    </aside>
  );
}

function EventList({ t }: { t: SerialTracking }) {
  if (t.events.length === 0) return <p className="state state--empty" data-testid="state-empty">رویدادی ثبت نشده است.</p>;
  return (
    <ol className="timeline" data-testid="serial-timeline">
      {t.events.map((e) => (
        <li key={e.audit_event_id}>
          {TRACKING_EVENT[e.kind] ?? e.kind} · <time dateTime={e.occurred_at}>{formatJalaliDateTime(e.occurred_at)}</time>
          {e.ref.entity_type === "change_request" ? <> · <a href={`#/changes/${e.ref.entity_id}`}>درخواست تغییر</a></> : null}
        </li>
      ))}
    </ol>
  );
}

// ------------------------------------------------------------------------------------------ page 1
function SummaryTab({ t }: { t: SerialTracking }) {
  return (
    <div className="serial-grid serial-grid--summary" data-testid="serial-summary">
      <SidePanel serialId={t.serial.serial_id} />
      <LaterSection title="مشکلات فعال" phase="PHASE_06 / PHASE_07" fid="active-problems" className="serial-problems" />
      <div className="later-grid serial-cards" data-fid="summary-cards">
        <LaterSection title="پیشرفت کلی" phase="PHASE_07 / PHASE_09" />
        <LaterSection title="آمادگی مواد" phase="PHASE_06" />
        <LaterSection title="این کجاست (موقعیت فعلی)" phase="PHASE_07" />
        <LaterSection title="کیفیت و گرید" phase="PHASE_08" />
      </div>
      <section className="panel serial-events" aria-labelledby="ev-title" data-fid="events">
        <div className="panel__head">
          <h2 id="ev-title">تاریخچه رویدادها</h2>
        </div>
        <EventList t={t} />
      </section>
    </div>
  );
}

/** A collapsible part of the order tab (native disclosure, keyboard accessible); the title shows what is inside.
 * `lazy`: the content (and its requests) is mounted only once the part is opened. */
function Fold({ title, children, testId, lazy = false }: { title: string; children: ReactNode; testId?: string; lazy?: boolean }) {
  const [opened, setOpened] = useState(false);
  return (
    <details
      className="fold"
      data-testid={testId}
      onToggle={(e) => {
        if (e.currentTarget.open) setOpened(true);
      }}
    >
      <summary className="fold__title">{title}</summary>
      <div className="fold__body">{!lazy || opened ? children : null}</div>
    </details>
  );
}

// ------------------------------------------------------------------------------------------ page 2
function OrderTab({ t, order, orderLoading }: { t: SerialTracking; order: CustomerOrder | undefined; orderLoading: boolean }) {
  const { can } = useAuth();
  const s = t.serial;
  const snaps = useQuery({
    queryKey: [...K2.serials, "snapshots", s.serial_id, s.current_snapshot_version],
    queryFn: async ({ signal }) => (await get(`/identity/serials/${s.serial_id}/snapshots`, g.snapshotPage, { page_size: 100 }, signal)).data,
  });
  const withheld = t.withheld_sections ?? [];
  return (
    <div className="serial-grid serial-grid--order" data-testid="serial-order" data-fid="order-tab">
      <section className="panel serial-order-head" aria-labelledby="o-title">
        <h2 id="o-title">سفارش و ردیف‌های آن</h2>
        {!can(PERM.orderRead) || withheld.includes("order_versions") ? (
          <p className="notice notice--info" data-testid="withheld">برای دیدن سفارش مجوز ندارید.</p>
        ) : orderLoading ? (
          <p className="state state--loading" data-testid="state-loading">در حال دریافت سفارش…</p>
        ) : order ? (
          <>
            <dl className="facts facts--order">
              <div><dt>شماره سفارش</dt><dd><a href={`#/orders/${order.order_id}`}><Num value={order.order_no} testId="serial-order-no" /></a></dd></div>
              <div><dt>PO مشتری</dt><dd><Num value={order.external_po_number} /></dd></div>
              <div><dt>نوع</dt><dd>{ORDER_TYPES[order.order_type] ?? order.order_type}</dd></div>
              <div><dt>وضعیت</dt><dd><StatusChip {...toneLabel(ORDER_STATUS, order.status)} /></dd></div>
              <div><dt>تاریخ سفارش</dt><dd>{formatJalaliDate(order.order_date)}</dd></div>
              <div><dt>تحویل درخواستی</dt><dd>{formatJalaliDate(order.requested_due_date)}</dd></div>
              <div><dt>نسخه جاری</dt><dd>{order.current_version ? toFaDigits(order.current_version) : "—"}</dd></div>
              <div><dt>نماینده مشتری</dt><dd><Representative value={order.customer_representative_name} /></dd></div>
            </dl>
            <table className="table table--cards table--grid" data-testid="serial-order-lines">
              <caption>ردیف‌های سفارش</caption>
              <thead>
                <tr><th scope="col">ردیف</th><th scope="col">کد</th><th scope="col">تعداد</th><th scope="col">تحویل</th><th scope="col">وضعیت</th><th scope="col">سریال</th></tr>
              </thead>
              <tbody>
                {order.lines.filter((l) => l.status !== "REMOVED").map((l) => (
                  <tr key={l.line_id} className={l.serial_id === s.serial_id ? "row--current" : undefined}>
                    <td data-label="ردیف">{toFaDigits(l.line_no)}</td>
                    <td data-label="کد"><Code14 code={l.product_code} /></td>
                    <td data-label="تعداد">{toFaDigits(l.quantity)} {UOM[l.uom] ?? l.uom}</td>
                    <td data-label="تحویل">{formatJalaliDate(l.requested_due_date)}</td>
                    <td data-label="وضعیت"><StatusChip {...toneLabel(LINE_STATUS, l.status)} /></td>
                    <td data-label="سریال">{l.serial_id ? <a href={`#/serials/${l.serial_id}`}><Num value={l.serial_number} /></a> : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <p className="field__hint">این سریال به سفارشی وصل نیست.</p>
        )}
      </section>
      <SidePanel serialId={s.serial_id} />
      <div className="serial-order-folds">
        <Fold title={`Snapshot سریال (آنچه هنگام تعهد ثبت شد)${snaps.data ? ` · ${toFaDigits(snaps.data.items.length)} نسخه` : ""}`}>
          <DataView query={snaps} loading="در حال دریافت Snapshotها…" errorTitle="Snapshotها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "Snapshotی نیست." }}>
            {(d) => (
              <ol className="timeline" data-testid="serial-snapshots">
                {d.items.map((x) => (
                  <li key={x.version}>
                    <strong>نسخه {toFaDigits(x.version)}</strong> — {VERSION_REASON[x.reason] ?? x.reason} · {formatJalaliDateTime(x.created_at)}
                    <SnapshotFacts snap={x.snapshot} />
                  </li>
                ))}
              </ol>
            )}
          </DataView>
        </Fold>
        <Fold title={`نسخه‌های سفارش · ${toFaDigits(t.order_versions.length)}`}>
          {t.order_versions.length === 0 ? (
            <p className="field__hint">{withheld.includes("order_versions") ? "بدون مجوز خواندن سفارش." : "نسخه‌ای نیست."}</p>
          ) : (
            <ol className="timeline" data-testid="serial-versions">
              {t.order_versions.map((v) => (
                <li key={v.version}>نسخه {toFaDigits(v.version)} — {VERSION_REASON[v.reason] ?? v.reason} · {formatJalaliDateTime(v.created_at)}</li>
              ))}
            </ol>
          )}
        </Fold>
        <Fold title="مرجع‌های خارجی (ارجاع‌های بیرونی سریال و سفارش)" testId="fold-refs" lazy>
          <ExternalRefs targetType="serial" targetId={s.serial_id} />
          {order ? <ExternalRefs targetType="customer_order" targetId={order.order_id} /> : null}
        </Fold>
        <Fold title={`تاریخچه رویدادها · ${toFaDigits(t.events.length)}`}>
          <EventList t={t} />
        </Fold>
      </div>
    </div>
  );
}

function SnapshotFacts({ snap }: { snap: Record<string, unknown> }) {
  const str = (k: string): string | null => { const v = snap[k]; return typeof v === "string" ? v : null; };
  const num = (k: string): number | null => { const v = snap[k]; return typeof v === "number" ? v : null; };
  const qty = num("quantity");
  const attrs = typeof snap.attributes === "object" && snap.attributes !== null ? (snap.attributes as Record<string, unknown>) : null;
  return (
    <dl className="meta meta--inline">
      {str("order_no") ? <div><dt>سفارش</dt><dd><Num value={str("order_no")} /></dd></div> : null}
      {num("order_version") !== null ? <div><dt>نسخه سفارش</dt><dd>{toFaDigits(num("order_version") ?? 0)}</dd></div> : null}
      {num("line_no") !== null ? <div><dt>ردیف</dt><dd>{toFaDigits(num("line_no") ?? 0)}</dd></div> : null}
      {str("product_code") ? <div><dt>کد</dt><dd><Code14 code={str("product_code")} /></dd></div> : null}
      {qty !== null ? <div><dt>تعداد</dt><dd>{toFaDigits(qty)} {UOM[str("uom") ?? ""] ?? ""}</dd></div> : null}
      {str("requested_due_date") ? <div><dt>تحویل</dt><dd>{formatJalaliDate(str("requested_due_date"))}</dd></div> : null}
      {str("style_revision_id") ? <div><dt>نسخه استایل</dt><dd><ShortId id={str("style_revision_id")} /></dd></div> : null}
      {attrs
        ? Object.entries(attrs).filter(([, v]) => typeof v === "string" && v).map(([k, v]) => (
            <div key={k}><dt>{ATTRIBUTE_LABEL[k] ?? k}</dt><dd>{String(v)}</dd></div>
          ))
        : null}
    </dl>
  );
}
