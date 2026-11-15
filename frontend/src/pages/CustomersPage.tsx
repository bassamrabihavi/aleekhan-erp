// Customers and brands (page 29 step 1 master data, MOCK_UI_BINDING §7.4; DEC-058): server-side search, create
// with the duplicate-name warning that must be acknowledged, brands per customer (B-A). CU- numbers come from
// the server (Jalali year, Asia/Tehran). No contact details are ever stored (DEC-028).
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { g, get, K2, PERM, send, type Customer } from "../api/phase02";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView, ForbiddenState } from "../components/DataView";
import { Dialog } from "../components/Dialog";
import { Field } from "../components/Form";
import { Num, PageHead } from "../components/Phase02";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime } from "../lib/format";
import { toneLabel } from "../lib/labels";
import { PARTY_STATUS } from "../lib/labels02";
import { useCursor } from "../lib/queries";
import { hasReason } from "../lib/queries02";
import { navigate, segments, useRoute } from "../lib/router";
import { useAction } from "../lib/useAction";
import { Pager } from "./SecurityPage";

export function CustomersPage() {
  const { can } = useAuth();
  const route = useRoute();
  const [id] = segments(route, "/customers");
  if (!can(PERM.customerRead)) {
    return (
      <div className="page" data-testid="page-customers">
        <PageHead page="صفحه ۲۹ · فاز ۲" title="مشتریان و برندها" />
        <ForbiddenState />
      </div>
    );
  }
  return (
    <div className="page" data-testid="page-customers">
      <PageHead
        page="صفحه ۲۹ · فاز ۲ · داده پایه"
        title="مشتریان و برندها"
        lead="شماره مشتری (CU-سال شمسی-شماره) را سرور می‌دهد. نام تکراری فقط هشدار است و با تأیید شما ثبت می‌شود؛ هیچ ادغام خودکاری انجام نمی‌شود. اطلاعات تماس ثبت نمی‌شود."
      />
      <div className="split">
        <CustomerList selected={id} />
        {id ? <CustomerDetail id={id} /> : null}
      </div>
    </div>
  );
}

function CustomerList({ selected }: { selected: string | undefined }) {
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const cursor = useCursor();
  const [creating, setCreating] = useState(false);
  const list = useQuery({
    queryKey: [...K2.customers, "list", search, cursor.cursor],
    queryFn: async ({ signal }) =>
      (await get("/identity/customers", g.customerPage, { q: search || undefined, cursor: cursor.cursor, page_size: 25 }, signal)).data,
  });
  return (
    <section className="panel" aria-labelledby="customers-title">
      <div className="panel__head">
        <h2 id="customers-title">مشتریان</h2>
        {can(PERM.customerManage) ? (
          <button type="button" className="btn btn--primary" onClick={() => { setCreating(true); }} data-testid="customer-create-open">
            مشتری جدید
          </button>
        ) : null}
      </div>
      <form
        className="filters"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          cursor.reset();
          setSearch(q.trim());
        }}
      >
        <Field label="جستجوی نام یا شماره مشتری">
          {(fid) => <input id={fid} className="input" value={q} maxLength={100} onChange={(e) => { setQ(e.target.value); }} data-testid="customer-search" />}
        </Field>
        <button type="submit" className="btn btn--secondary">جستجو</button>
      </form>
      <DataView query={list} loading="در حال دریافت مشتریان…" errorTitle="مشتریان دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: search ? "مشتری‌ای با این جستجو پیدا نشد." : "هنوز مشتری‌ای ثبت نشده است." }}>
        {(d) => (
          <>
            <ul className="cards" data-testid="customers-list">
              {d.items.map((c) => (
                <li key={c.customer_id} className={c.customer_id === selected ? "card card--selected" : "card"}>
                  <a href={`#/customers/${c.customer_id}`} className="card__link" data-testid="customer-open" aria-current={c.customer_id === selected ? "true" : undefined}>
                    <strong>{c.display_name_fa}</strong> <Num value={c.customer_no} />
                  </a>
                  <StatusChip {...toneLabel(PARTY_STATUS, c.status)} />
                </li>
              ))}
            </ul>
            <Pager depth={cursor.depth} next={d.page.next_cursor} onNext={cursor.next} onPrev={cursor.prev} />
          </>
        )}
      </DataView>
      {creating ? <CreateCustomerDialog onClose={() => { setCreating(false); }} /> : null}
    </section>
  );
}

function CreateCustomerDialog({ onClose }: { onClose: () => void }) {
  const action = useAction();
  const [name, setName] = useState("");
  const [legal, setLegal] = useState("");
  const [quality, setQuality] = useState("");
  const [ack, setAck] = useState(false);
  const duplicate = hasReason(action.error, "DUPLICATE_CUSTOMER_NAME");
  return (
    <Dialog title="مشتری جدید" onClose={onClose} testId="customer-dialog">
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          void action
            .run(
              (key) =>
                send("/identity/customers", g.customer, {
                  display_name_fa: name.trim(),
                  legal_name_fa: legal.trim() || null,
                  default_required_quality_ref: quality.trim() || null,
                  ...(ack ? { acknowledge_possible_duplicate: true } : {}),
                }, key),
              [K2.customers],
            )
            .then((r) => {
              if (r) {
                onClose();
                navigate(`/customers/${r.data.customer_id}`);
              }
            });
        }}
      >
        <Field label="نام نمایشی *">
          {(id) => <input id={id} className="input" required maxLength={200} value={name} onChange={(e) => { setName(e.target.value); setAck(false); }} data-testid="customer-name" />}
        </Field>
        <Field label="نام حقوقی">
          {(id) => <input id={id} className="input" maxLength={300} value={legal} onChange={(e) => { setLegal(e.target.value); }} />}
        </Field>
        <Field label="گرید پیش‌فرض موردنیاز (متن آزاد تا DEC-019)">
          {(id) => <input id={id} className="input" maxLength={64} value={quality} onChange={(e) => { setQuality(e.target.value); }} />}
        </Field>
        {duplicate ? (
          <label className="check notice notice--warning" data-testid="customer-dup-warning">
            <input type="checkbox" checked={ack} onChange={(e) => { setAck(e.target.checked); }} data-testid="customer-dup-ack" />
            مشتری دیگری با همین نام وجود دارد. می‌دانم و می‌خواهم مشتری جدید جداگانه ثبت شود (ادغام نمی‌شود).
          </label>
        ) : (
          <ActionError error={action.error} />
        )}
        <div className="form__actions">
          <button type="submit" className="btn btn--primary" disabled={action.pending || !name.trim() || (duplicate && !ack)} data-testid="customer-submit">
            {action.pending ? "در حال ثبت…" : "ثبت مشتری"}
          </button>
          <button type="button" className="btn btn--secondary" onClick={onClose}>انصراف</button>
        </div>
      </form>
    </Dialog>
  );
}

function CustomerDetail({ id }: { id: string }) {
  const q = useQuery({
    queryKey: [...K2.customers, "one", id],
    queryFn: async ({ signal }) => get(`/identity/customers/${id}`, g.customer, undefined, signal),
  });
  return (
    <section className="panel" aria-labelledby="customer-detail-title" data-testid="customer-detail">
      <DataView query={q} loading="در حال دریافت مشتری…" errorTitle="مشتری دریافت نشد">
        {(r) => (
          <>
            <h2 id="customer-detail-title">{r.data.display_name_fa}</h2>
            <CustomerMeta c={r.data} />
            <Brands customer={r.data} />
          </>
        )}
      </DataView>
    </section>
  );
}

function CustomerMeta({ c }: { c: Customer }) {
  return (
    <dl className="meta meta--rows">
      <div><dt>شماره مشتری</dt><dd><Num value={c.customer_no} testId="customer-no" /></dd></div>
      <div><dt>نام حقوقی</dt><dd>{c.legal_name_fa ?? "—"}</dd></div>
      <div><dt>وضعیت</dt><dd><StatusChip {...toneLabel(PARTY_STATUS, c.status)} /></dd></div>
      <div><dt>گرید پیش‌فرض (متن)</dt><dd>{c.default_required_quality_ref ?? "—"}</dd></div>
      <div><dt>ثبت</dt><dd>{formatJalaliDateTime(c.created_at)}</dd></div>
    </dl>
  );
}

function Brands({ customer }: { customer: Customer }) {
  const { can } = useAuth();
  const action = useAction();
  const [name, setName] = useState("");
  const list = useQuery({
    queryKey: [...K2.customers, "brands", customer.customer_id],
    queryFn: async ({ signal }) =>
      (await get(`/identity/customers/${customer.customer_id}/brands`, g.brandPage, { page_size: 100 }, signal)).data,
  });
  return (
    <section aria-labelledby="brands-title">
      <h3 id="brands-title">برندها</h3>
      <DataView query={list} loading="در حال دریافت برندها…" errorTitle="برندها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "برندی ثبت نشده است (برند روی سفارش اختیاری است)." }}>
        {(d) => (
          <ul className="list" data-testid="brands-list">
            {d.items.map((b) => (
              <li key={b.brand_id}>
                {b.brand_name_fa} <StatusChip {...toneLabel(PARTY_STATUS, b.status)} />
              </li>
            ))}
          </ul>
        )}
      </DataView>
      {can(PERM.customerManage) ? (
        <form
          className="form form--inline"
          onSubmit={(e) => {
            e.preventDefault();
            void action
              .run((key) => send(`/identity/customers/${customer.customer_id}/brands`, g.brand, { brand_name_fa: name.trim() }, key), [K2.customers])
              .then((r) => {
                if (r) setName("");
              });
          }}
        >
          <Field label="برند جدید">
            {(fid) => <input id={fid} className="input" maxLength={200} value={name} onChange={(e) => { setName(e.target.value); }} data-testid="brand-name" />}
          </Field>
          <button type="submit" className="btn btn--secondary" disabled={action.pending || !name.trim()} data-testid="brand-submit">افزودن برند</button>
          <ActionError error={action.error} />
        </form>
      ) : null}
    </section>
  );
}
