// Pages 1 and 2 «مرکز کنترل سریال» (DEC-027 P-A, employer decision 2026-11-15; MOCK_UI_BINDING §7.1/§7.2), built
// from the mobile images with PHASE_02 data ONLY:
//   page 1 (tab «خلاصه») - serial header (number, product, code, customer / brand, status, quantity, required
//     grade text, program), change requests of the serial; the production stages, active problems, progress,
//     materials, location and quality sections are later phases and show the placeholder WITHOUT numbers.
//   page 2 (tab «سفارش») - order header, lines, the serial's snapshots, order versions, external references and
//     the audited timeline.
// No sample number of the images is ever shown (rule 1/2).
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";

import { g, get, K2, PERM, type CustomerOrder, type Serial, type SerialTracking } from "../api/phase02";
import { useAuth } from "../auth/context";
import { DataView, ForbiddenState } from "../components/DataView";
import { Field, ShortId, TabPanel, Tabs } from "../components/Form";
import { Icon, type IconName } from "../components/Icon";
import { Code14, CustomerName, LATER_TEXT, LaterSection, Num, PageHead, Representative } from "../components/Phase02";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import { useMediaQuery } from "../lib/hooks";
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

/** Tablet / phone layout (one column): the side panel and the problems card move into the tab body (concept). */
const NARROW = "(max-width: 900px)";

function useNarrow(): boolean {
  return useMediaQuery(NARROW);
}

function SerialView({ id }: { id: string }) {
  const { can } = useAuth();
  const narrow = useNarrow();
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
            <HeaderActions />
            <DateCards />
          </div>
          <SerialHeader s={t.serial} order={order.data} />
          <div className="serial-body">
            <div className="serial-main">
              <StageFlow />
              <Tabs tabs={SERIAL_TABS.map(({ id: tid, label }) => ({ id: tid, label }))} active={tab} onChange={setTab} label="بخش‌های مرکز کنترل سریال" fid="tabs" />
              <TabPanel id={tab}>
                {tab === "summary" ? (
                  <SummaryTab t={t} narrow={narrow} onAllEvents={() => { setTab("history"); }} />
                ) : tab === "order" ? (
                  <OrderTab t={t} order={order.data} orderLoading={order.isPending && order.fetchStatus !== "idle"} narrow={narrow} />
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
            {narrow ? null : <SidePanel serialId={t.serial.serial_id} />}
          </div>
        </div>
      )}
    </DataView>
  );
}

/** Planning actions of the concept (PHASE_05): real buttons in the concept's group, visibly disabled with the reason. */
function HeaderActions() {
  const actions: { label: string; icon: IconName; tone: string; caret?: boolean }[] = [
    { label: "تصمیم برنامه‌ریزی", icon: "chevronDown", tone: "btn--primary", caret: true },
    { label: "تغییر اولویت", icon: "priority", tone: "btn--outline" },
    { label: "Fast Track", icon: "bolt", tone: "btn--tint" },
    { label: "سناریو", icon: "layers", tone: "btn--outline" },
    { label: "بیشتر", icon: "chevronDown", tone: "btn--outline" },
  ];
  return (
    <div className="serial-actions" role="group" aria-label="اقدام‌های برنامه‌ریزی سریال" data-fid="header-actions">
      {actions.map((a) => (
        <button key={a.label} type="button" className={`btn ${a.tone} serial-actions__btn`} disabled title="در دست ساخت — فاز ۵ (برنامه‌ریزی)" aria-describedby="serial-actions-later">
          {a.label}
          <Icon name={a.icon} size={16} />
        </button>
      ))}
      <span id="serial-actions-later" className="serial-actions__note">
        در دست ساخت · <bdi dir="ltr">PHASE_05</bdi>
      </span>
    </div>
  );
}

/** Commitment / forecast / gap (PHASE_05): the concept's dated cards with the value «—» until planning exists. */
function DateCards() {
  const cards: { label: string; icon: IconName; tone?: string }[] = [
    { label: "تعهد", icon: "calendar" },
    { label: "Forecast", icon: "calendar" },
    { label: "اختلاف", icon: "alertCircle", tone: "date-card--gap" },
  ];
  return (
    <ul className="date-cards" aria-label="تاریخ‌های تعهد و پیش‌بینی" data-fid="date-cards">
      {cards.map((c) => (
        <li key={c.label} className={c.tone ? `date-card ${c.tone}` : "date-card"} data-fid-item title="فاز مالک: PHASE_05">
          <span className="date-card__head">
            <span className="date-card__label">{c.label}</span>
            <Icon name={c.icon} size={18} />
          </span>
          <span className="date-card__value">—<span className="sr-only"> (بدون داده)</span></span>
          <span className="date-card__meta">
            در دست ساخت · <bdi dir="ltr">PHASE_05</bdi>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** The concept's stage tracker: every production stage as a circle with its icon, in the neutral «not connected»
 * state (PHASE_03 … PHASE_09 own the stages); no stage is marked done and no WIP number is shown. */
const STAGES: { label: string; icon: IconName; desktopOnly?: boolean }[] = [
  { label: "بازرگانی", icon: "order", desktopOnly: true },
  { label: "مواد و انبار", icon: "cube" },
  { label: "مهندسی", icon: "gear" },
  { label: "تأمین", icon: "truck" },
  { label: "برش", icon: "scissors" },
  { label: "دوخت", icon: "needle" },
  { label: "کنترل کیفیت", icon: "search" },
  { label: "آماده محصول", icon: "check" },
];

function StageFlow() {
  return (
    <section className="later stage-flow" data-testid="later-section" aria-label="مراحل تولید سریال" data-fid="stage-flow">
      <ol className="stage-flow__steps">
        {STAGES.map((s, i) => (
          <li key={s.label} className={s.desktopOnly ? "stage stage--desktop" : "stage"}>
            <span className="stage__circle" aria-hidden="true">
              <Icon name={s.icon} size={18} />
            </span>
            <span className="stage__label">{s.label}</span>
            {i < STAGES.length - 1 ? <Icon name="arrowLeft" size={16} className="stage__arrow" /> : null}
          </li>
        ))}
      </ol>
      <div className="stage-flow__note">
        <h3 className="later__title">مراحل تولید سریال</h3>
        <p className="later__text">{LATER_TEXT}</p>
        <p className="later__meta">
          فاز مالک: <bdi dir="ltr">PHASE_03 … PHASE_09</bdi>
        </p>
      </div>
    </section>
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
      {/* no product image exists in PHASE_02 data: an honest placeholder in the concept's image slot */}
      <div className="serial-head__image" role="img" aria-label="تصویر محصول ثبت نشده">
        <Icon name="image" size={26} />
        <span aria-hidden="true">تصویر محصول ثبت نشده</span>
      </div>
      <div className="serial-head__main">
        <p className="eyebrow">صفحه ۱ و ۲ · مرکز کنترل سریال · فاز ۲</p>
        <div className="serial-head__title">
          <h1 id="serial-title">
            سریال <Num value={s.serial_number} testId="serial-number" />
          </h1>
        </div>
        <p className="serial-head__product">
          {product.data?.name_fa ?? "—"}
          {style.data ? <> · {style.data.name_fa}</> : null}
        </p>
      </div>
      <div className="serial-head__chips">
        <StatusChip {...toneLabel(SERIAL_STATUS, s.status)} testId="serial-status" />
        {order ? <span className="chip chip--info chip--inline">{ORDER_TYPES[order.order_type] ?? order.order_type}</span> : null}
        <span className="chip chip--neutral chip--inline chip--clip" title={names.get(s.customer_id)?.display_name_fa}>
          <CustomerName id={s.customer_id} names={names} />
        </span>
        {brand ? <span className="chip chip--gold chip--inline">{brand.brand_name_fa}</span> : null}
        {order?.required_quality_requirement ? <span className="chip chip--warning chip--inline" title="متن گرید موردنیاز (مقایسه با گرید تا DEC-019 نیست)">گرید: {order.required_quality_requirement}</span> : null}
      </div>
      <dl className="serial-head__facts">
        <div><dt>کد محصول</dt><dd><Code14 code={s.product_code} copy testId="serial-code" /></dd></div>
        <div className="fact--minor"><dt>استایل</dt><dd><Num value={style.data?.style_no} /></dd></div>
        <div className="fact--icon"><Icon name="cube" size={16} /><dt>تعداد سفارش</dt><dd data-testid="serial-qty">{line ? `${toFaDigits(line.quantity)} ${UOM[line.uom] ?? line.uom}` : "—"}</dd></div>
        <div><dt>رنگ</dt><dd title={attr("colour_fa")}>{attr("colour_fa")}</dd></div>
        <div><dt>جنس</dt><dd title={attr("main_material_fa")}>{attr("main_material_fa")}</dd></div>
        <div className="fact--icon fact--minor"><Icon name="calendar" size={16} /><dt>برنامه مشتری</dt><dd>{order?.program_ref ?? "—"}</dd></div>
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
        <h2 id="side-title">
          <Icon name="clipboard" size={18} />
          تصمیم‌ها و پیگیری‌ها
        </h2>
        {can(PERM.changeRead) ? <a href="#/changes" className="btn btn--link">مشاهده همه</a> : null}
      </div>
      <div className="side-card side-card--decision">
        <div className="side-card__head">
          <span className="side-card__icon side-card__icon--warning" aria-hidden="true"><Icon name="alertCircle" size={20} /></span>
          <div>
            <h3>تصمیم لازم</h3>
            <p className="serial-side__sub">درخواست‌های تغییر این سریال</p>
          </div>
        </div>
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
        {can(PERM.changeRead) ? (
          <a href="#/changes" className="btn btn--outline btn--block side-card__action">مشاهده و تصمیم‌گیری</a>
        ) : null}
      </div>
      <SideLater title="تسک‌های نزدیک موعد" icon="check" tone="info" action="مشاهده تسک‌ها" detail="تسک‌های این سریال با موعد نزدیک، پس از ساخت برنامه‌ریزی اینجا دیده می‌شوند." />
      <SideLater title="ریسک‌ها" icon="alert" tone="danger" action="جزئیات ریسک‌ها" detail="ریسک تأخیر، کسری مواد و خرابی دستگاه، پس از ساخت برنامه‌ریزی اینجا دیده می‌شود." />
    </aside>
  );
}

function SideLater({ title, icon, tone, action, detail }: { title: string; icon: IconName; tone: "info" | "danger"; action: string; detail: string }) {
  const id = useId();
  return (
    <div className={`side-card side-card--${tone}`}>
      <div className="side-card__head">
        <span className={`side-card__icon side-card__icon--${tone}`} aria-hidden="true"><Icon name={icon} size={20} /></span>
        <div>
          <h3>{title}</h3>
          <p className="serial-side__later-text">
            در دست ساخت · <bdi dir="ltr">PHASE_05</bdi>
          </p>
          <p className="serial-side__sub">{detail}</p>
        </div>
      </div>
      <button type="button" className="btn btn--outline btn--block side-card__action" disabled title="در دست ساخت — فاز ۵ (برنامه‌ریزی)" aria-describedby={id}>
        {action}
      </button>
      <span id={id} className="sr-only">در دست ساخت — فاز ۵ (برنامه‌ریزی)</span>
    </div>
  );
}

const EVENT_ICON: Record<string, IconName> = {
  ORDER_DRAFTED: "orderNew",
  ORDER_VALIDATED: "check",
  ORDER_CONFIRMED: "check",
  SERIAL_ALLOCATED: "serial",
  ORDER_RELEASED_TO_PLAN: "calendar",
  CHANGE_REQUESTED: "change",
  CHANGE_DECIDED: "check",
  CHANGE_APPLIED: "change",
  ORDER_CANCELLED: "alert",
  SERIAL_CANCELLED: "alert",
};

function EventList({ t }: { t: SerialTracking }) {
  if (t.events.length === 0) return <p className="state state--empty" data-testid="state-empty">رویدادی ثبت نشده است.</p>;
  return (
    <ol className="timeline timeline--icons" data-testid="serial-timeline">
      {t.events.map((e) => (
        <li key={e.audit_event_id}>
          <Icon name={EVENT_ICON[e.kind] ?? "history"} size={16} className="timeline__icon" />
          <span className="timeline__text">
            {TRACKING_EVENT[e.kind] ?? e.kind}
            {e.ref.entity_type === "change_request" ? <> · <a href={`#/changes/${e.ref.entity_id}`}>درخواست تغییر</a></> : null}
          </span>
          <time dateTime={e.occurred_at}>{formatJalaliDateTime(e.occurred_at)}</time>
        </li>
      ))}
    </ol>
  );
}

// ------------------------------------------------------------------------------------------ page 1
/** A later-phase summary card in the concept's form: icon header, the main value «—», the metric rows with their
 * labels and «—» values, the placeholder text and the owning phase. Never a sample number (DEC-027). */
function LaterCard({ title, icon, phase, main, bar = false, box, rows, className }: { title: string; icon: IconName; phase: string; main?: string; bar?: boolean; box?: string; rows: string[]; className?: string }) {
  return (
    <section className={className ? `later later-card ${className}` : "later later-card"} data-testid="later-section" aria-label={title}>
      <div className="later-card__head">
        <Icon name={icon} size={20} className="later-card__icon" />
        <h3 className="later__title">{title}</h3>
      </div>
      {main ? (
        <p className="later-card__main">
          <span>{main}</span>
          <strong>—<span className="sr-only"> (بدون داده)</span></strong>
        </p>
      ) : null}
      {box ? (
        <div className="later-card__box">
          <span>{box}</span>
          <strong>—<span className="sr-only"> (بدون داده)</span></strong>
        </div>
      ) : null}
      {bar ? <span className="later-card__bar" aria-hidden="true" /> : null}
      <ul className="later-card__rows">
        {rows.map((r) => (
          <li key={r}>
            <span className="later-card__dot" aria-hidden="true" />
            <span>{r}</span>
            <span>—<span className="sr-only"> (بدون داده)</span></span>
          </li>
        ))}
      </ul>
      <p className="later__text">{LATER_TEXT}</p>
      <p className="later__meta">
        فاز مالک: <bdi dir="ltr">{phase}</bdi>
      </p>
    </section>
  );
}

function ProblemsCard({ fid }: { fid?: string }) {
  return (
    <section className="later later-card later-card--problems" data-testid="later-section" aria-label="مشکلات فعال" data-fid={fid}>
      <div className="later-card__head">
        <Icon name="alert" size={20} className="later-card__icon" />
        <h3 className="later__title">مشکلات فعال</h3>
        <span className="later-card__count">— مورد<span className="sr-only"> (تعداد: بدون داده)</span></span>
      </div>
      <div className="later-card__box later-card__box--problems">
        <span>کسری، توقف دستگاه و تأخیر هر مرحله</span>
        <strong>—<span className="sr-only"> (بدون داده)</span></strong>
      </div>
      <p className="later__text">{LATER_TEXT}</p>
      <p className="later__meta">
        فاز مالک: <bdi dir="ltr">PHASE_06 / PHASE_07</bdi>
      </p>
    </section>
  );
}

/** Event filter of the summary (concept chips): by what the audited event is about. */
const EVENT_GROUPS: { id: string; label: string; kinds: readonly string[] | null }[] = [
  { id: "all", label: "همه", kinds: null },
  { id: "order", label: "سفارش", kinds: ["ORDER_DRAFTED", "ORDER_VALIDATED", "ORDER_CONFIRMED", "ORDER_RELEASED_TO_PLAN", "ORDER_CANCELLED"] },
  { id: "serial", label: "سریال", kinds: ["SERIAL_ALLOCATED", "SERIAL_CANCELLED"] },
  { id: "change", label: "تغییرات", kinds: ["CHANGE_REQUESTED", "CHANGE_DECIDED", "CHANGE_APPLIED"] },
];

function SummaryTab({ t, narrow, onAllEvents }: { t: SerialTracking; narrow: boolean; onAllEvents: () => void }) {
  const [group, setGroup] = useState("all");
  const kinds = EVENT_GROUPS.find((x) => x.id === group)?.kinds ?? null;
  const shown: SerialTracking = kinds ? { ...t, events: t.events.filter((e) => kinds.includes(e.kind)) } : t;
  return (
    <div className="serial-grid serial-grid--summary" data-testid="serial-summary">
      {narrow ? <ProblemsCard fid="active-problems" /> : null}
      {narrow ? <SidePanel serialId={t.serial.serial_id} /> : null}
      <div className="serial-cards" data-fid="summary-cards">
        <LaterCard title="پیشرفت کلی" icon="chart" phase="PHASE_07 / PHASE_09" main="پیشرفت واقعی" bar rows={["تولیدشده", "در فرایند", "محصول نهایی", "ارسال نشده"]} className="later-card--progress" />
        <LaterCard title="این کجاست (موقعیت فعلی)" icon="location" phase="PHASE_07" box="خط و مرحله فعلی" bar rows={["قطعه‌سازی", "دوخت", "QC"]} className="later-card--where" />
        {narrow ? null : <ProblemsCard />}
        <LaterCard title="آمادگی مواد" icon="cube" phase="PHASE_06" main="آمادگی مواد" rows={["کامل", "کسری", "Hold کیفی", "در انتظار دریافت"]} className="later-card--materials" />
        <LaterCard title="کیفیت و گرید" icon="quality" phase="PHASE_08" box="استاندارد محصول" rows={["A+", "A", "B", "Rework"]} className="later-card--quality" />
      </div>
      <section className="panel serial-events" aria-labelledby="ev-title" data-fid="events">
        <div className="panel__head">
          <h2 id="ev-title">
            <Icon name="clock" size={18} />
            تاریخچه رویدادها
          </h2>
          <div className="serial-events__filter" role="group" aria-label="فیلتر رویدادها">
            {EVENT_GROUPS.map((x) => (
              <button key={x.id} type="button" className={x.id === group ? "btn chipbtn chipbtn--on" : "btn chipbtn"} aria-pressed={x.id === group} onClick={() => { setGroup(x.id); }}>
                {x.label}
              </button>
            ))}
          </div>
        </div>
        <EventList t={shown} />
        <button type="button" className="btn btn--outline btn--compact serial-events__all" onClick={onAllEvents}>
          <Icon name="tasks" size={16} />
          مشاهده همه رویدادها
        </button>
      </section>
    </div>
  );
}

/** A collapsible part of the order tab (native disclosure, keyboard accessible); the title shows what is inside.
 * `lazy`: the content (and its requests) is mounted only once the part is opened. */
function Fold({ title, icon, children, testId, lazy = false }: { title: string; icon: IconName; children: ReactNode; testId?: string; lazy?: boolean }) {
  const [opened, setOpened] = useState(false);
  return (
    <details
      className="fold"
      data-testid={testId}
      onToggle={(e) => {
        if (e.currentTarget.open) setOpened(true);
      }}
    >
      <summary className="fold__title">
        <Icon name={icon} size={18} className="fold__icon" />
        {title}
      </summary>
      <div className="fold__body">{!lazy || opened ? children : null}</div>
    </details>
  );
}

// ------------------------------------------------------------------------------------------ page 2
function OrderTab({ t, order, orderLoading, narrow }: { t: SerialTracking; order: CustomerOrder | undefined; orderLoading: boolean; narrow: boolean }) {
  const { can } = useAuth();
  const s = t.serial;
  const snaps = useQuery({
    queryKey: [...K2.serials, "snapshots", s.serial_id, s.current_snapshot_version],
    queryFn: async ({ signal }) => (await get(`/identity/serials/${s.serial_id}/snapshots`, g.snapshotPage, { page_size: 100 }, signal)).data,
  });
  const withheld = t.withheld_sections ?? [];
  // the order lines: inside the order card on the desktop; on tablet / phone after the side panel (concept order)
  const lines = order ? (
    <div className="subcard">
        <h3 className="subcard__title">
          <Icon name="tasks" size={16} />
          ردیف‌های سفارش
        </h3>
        <table className="table table--cards table--grid" data-testid="serial-order-lines">
          <caption className="sr-only">ردیف‌های سفارش</caption>
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
      </div>
  ) : null;
  return (
    <div className="serial-grid serial-grid--order" data-testid="serial-order" data-fid="order-tab">
      <section className="panel serial-order-head" aria-labelledby="o-title">
        <h2 id="o-title">
          <Icon name="order" size={18} />
          سفارش و ردیف‌های آن
        </h2>
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
            {narrow ? null : lines}
          </>
        ) : (
          <p className="field__hint">این سریال به سفارشی وصل نیست.</p>
        )}
      </section>
      {narrow ? <SidePanel serialId={s.serial_id} /> : null}
      {narrow && lines && can(PERM.orderRead) && !withheld.includes("order_versions") ? <section className="panel serial-order-lines" aria-label="ردیف‌های سفارش">{lines}</section> : null}
      <div className="serial-order-folds">
        <Fold icon="documents" title={`Snapshot سریال (آنچه هنگام تعهد ثبت شد)${snaps.data ? ` · ${toFaDigits(snaps.data.items.length)} نسخه` : ""}`}>
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
        <Fold icon="layers" title={`نسخه‌های سفارش · ${toFaDigits(t.order_versions.length)}`}>
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
        <Fold icon="source" title="مرجع‌های خارجی (ارجاع‌های بیرونی سریال و سفارش)" testId="fold-refs" lazy>
          <ExternalRefs targetType="serial" targetId={s.serial_id} />
          {order ? <ExternalRefs targetType="customer_order" targetId={order.order_id} /> : null}
        </Fold>
        <Fold icon="clock" title={`تاریخچه رویدادها · ${toFaDigits(t.events.length)}`}>
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
