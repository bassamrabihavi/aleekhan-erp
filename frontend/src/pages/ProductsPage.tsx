// Page 4 «ردیابی محصولات و استایل‌ها» / Product 360, PHASE_02 part (MOCK_UI_BINDING §7.3): product profile and
// codes, style list, style revisions (colour / material per revision), the style's serials with THEIR snapshot
// attributes, server-computed counts, similar-style suggestions (never a merge, C-71), code preview / issue
// (DEC-005 B1: RESERVED / ERP_PENDING; fresh MFA) and a 14-digit code check. WIP and risk are later phases.
// Product numbers, style numbers and codes are built by the server only; style 0000 is never offered.
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";

import { g, get, K2, PERM, probe, send, type Product, type ProductClass, type Style, type StyleAttributes, type StyleRevision, type StyleTracking } from "../api/phase02";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView, ForbiddenState } from "../components/DataView";
import { Dialog } from "../components/Dialog";
import { Field, ReasonDialog } from "../components/Form";
import { Icon } from "../components/Icon";
import { Code14, CustomerName, DisabledAction, Kpi, LaterKpi, LaterSection, Num, PageHead } from "../components/Phase02";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import { isoToJalaliInput, jalaliInputToIso } from "../lib/jalali";
import { toneLabel } from "../lib/labels";
import { ATTRIBUTE_LABEL, CODE_CHECK_REASONS, CODE_STATUS, ERP_STATUS, MASTER_STATUS, SERIAL_STATUS, UOM } from "../lib/labels02";
import { useCursor } from "../lib/queries";
import { useCustomerNames } from "../lib/queries02";
import { navigate, segments, useRoute } from "../lib/router";
import { useMediaQuery } from "../lib/hooks";
import { useAction } from "../lib/useAction";
import { Pager } from "./SecurityPage";

const BELT = "BELT_BUCKLE_WIDTH";

function useClasses(level: "product_type" | "category", parent?: string) {
  return useQuery({
    queryKey: [...K2.classes, level, parent ?? ""],
    queryFn: async ({ signal }) =>
      (await get("/identity/product-classes", g.classPage, { level_key: level, parent_class_id: parent, page_size: 100 }, signal)).data,
    staleTime: 60_000,
  });
}

export function ProductsPage() {
  const { can } = useAuth();
  const route = useRoute();
  const [productId, styleId] = segments(route, "/products");
  if (!can(PERM.productRead)) {
    return (
      <div className="page" data-testid="page-products">
        <PageHead page="صفحه ۴ · فاز ۲" title="ردیابی محصولات و استایل‌ها" />
        <ForbiddenState />
      </div>
    );
  }
  if (productId && styleId) {
    return (
      <div className="page" data-testid="page-products">
        <Style360 productId={productId} styleId={styleId} />
      </div>
    );
  }
  return (
    <div className="page" data-testid="page-products">
      <PageHead
        page="صفحه ۴ · فاز ۲"
        title="ردیابی محصولات و استایل‌ها"
        lead="شماره محصول، شماره استایل و کد ۱۴رقمی را فقط سرور طبق قاعده مصوب (DEC-005) می‌سازد. رنگ و جنس هر سریال از Snapshot همان سریال خوانده می‌شود."
      />
      <div className="split">
        <ProductList selected={productId} />
        <div className="stack">
          {productId ? <ProductDetail id={productId} styleId={styleId} /> : <CodeCheck />}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- list
function ProductList({ selected }: { selected: string | undefined }) {
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const cursor = useCursor();
  const list = useQuery({
    queryKey: [...K2.products, "list", search, cursor.cursor],
    queryFn: async ({ signal }) =>
      (await get("/identity/products", g.productPage, { q: search || undefined, cursor: cursor.cursor, page_size: 25 }, signal)).data,
  });
  return (
    <section className="panel" aria-labelledby="products-title">
      <div className="panel__head">
        <h2 id="products-title">محصولات</h2>
        {can(PERM.productManage) ? (
          <button type="button" className="btn btn--primary" onClick={() => { setCreating(true); }} data-testid="product-create-open">
            محصول جدید
          </button>
        ) : null}
      </div>
      <form className="filters" role="search" onSubmit={(e) => { e.preventDefault(); cursor.reset(); setSearch(q.trim()); }}>
        <Field label="جستجوی نام یا شماره محصول">
          {(id) => <input id={id} className="input" maxLength={100} value={q} onChange={(e) => { setQ(e.target.value); }} data-testid="product-search" />}
        </Field>
        <button type="submit" className="btn btn--secondary">جستجو</button>
      </form>
      <DataView query={list} loading="در حال دریافت محصولات…" errorTitle="محصولات دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "محصولی پیدا نشد." }}>
        {(d) => (
          <>
            <ul className="cards" data-testid="products-list">
              {d.items.map((p) => (
                <li key={p.product_id} className={p.product_id === selected ? "card card--selected" : "card"}>
                  <a href={`#/products/${p.product_id}`} className="card__link" data-testid="product-open">
                    <strong>{p.name_fa}</strong> · شماره <Num value={p.product_no} />
                  </a>
                  <StatusChip {...toneLabel(MASTER_STATUS, p.status)} />
                </li>
              ))}
            </ul>
            <Pager depth={cursor.depth} next={d.page.next_cursor} onNext={cursor.next} onPrev={cursor.prev} />
          </>
        )}
      </DataView>
      {creating ? <CreateProductDialog onClose={() => { setCreating(false); }} /> : null}
    </section>
  );
}

function CreateProductDialog({ onClose }: { onClose: () => void }) {
  const action = useAction();
  const types = useClasses("product_type");
  const [typeId, setTypeId] = useState("");
  const [name, setName] = useState("");
  const [buckle, setBuckle] = useState("");
  const [width, setWidth] = useState("");
  const type = types.data?.items.find((t) => t.product_class_id === typeId);
  const belt = type?.product_no_scheme === BELT;
  const two = /^[0-9]{2}$/;
  const ready = !!type && name.trim() !== "" && (!belt || (two.test(buckle) && two.test(width)));
  return (
    <Dialog title="محصول جدید" onClose={onClose} testId="product-dialog">
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          void action
            .run(
              (key) =>
                send("/identity/products", g.product, {
                  product_class_id: typeId,
                  name_fa: name.trim(),
                  ...(belt ? { buckle_type_code: buckle, belt_width_code: width } : {}),
                }, key),
              [K2.products],
            )
            .then((r) => {
              if (r) {
                onClose();
                navigate(`/products/${r.data.product_id}`);
              }
            });
        }}
      >
        <Field label="نوع محصول *" hint="انواع از برگه Sorce برنامه‌ریزی وارد می‌شوند؛ در این صفحه ساخته نمی‌شوند.">
          {(id, hintId) => (
            <select id={id} className="input" required value={typeId} aria-describedby={hintId} onChange={(e) => { setTypeId(e.target.value); }} data-testid="product-type">
              <option value="">انتخاب کنید</option>
              {(types.data?.items ?? []).filter((t) => t.status === "ACTIVE").map((t) => (
                <option key={t.product_class_id} value={t.product_class_id}>
                  {t.label_fa} ({t.segment_value})
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="نام محصول *">
          {(id) => <input id={id} className="input" required maxLength={200} value={name} onChange={(e) => { setName(e.target.value); }} data-testid="product-name" />}
        </Field>
        {belt ? (
          <fieldset className="fieldset" data-testid="belt-fields">
            <legend>کمربند: شماره محصول = نوع سگک (۲ رقم) + عرض (۲ رقم)</legend>
            <Field label="کد نوع سگک (دو رقم) *">
              {(id) => <input id={id} className="input" dir="ltr" inputMode="numeric" required pattern="[0-9]{2}" maxLength={2} value={buckle} onChange={(e) => { setBuckle(e.target.value); }} data-testid="product-buckle" />}
            </Field>
            <Field label="عرض کمربند (دو رقم، مثلاً ۳۵ برای ۳٫۵ سانتی‌متر) *">
              {(id) => <input id={id} className="input" dir="ltr" inputMode="numeric" required pattern="[0-9]{2}" maxLength={2} value={width} onChange={(e) => { setWidth(e.target.value); }} data-testid="product-width" />}
            </Field>
          </fieldset>
        ) : (
          <p className="field__hint">شماره محصول را سرور می‌دهد (بزرگ‌ترین شماره همان نوع + ۱).</p>
        )}
        <ActionError error={action.error} />
        <div className="form__actions">
          <button type="submit" className="btn btn--primary" disabled={action.pending || !ready} data-testid="product-submit">
            {action.pending ? "در حال ثبت…" : "ثبت محصول (پیش‌نویس)"}
          </button>
          <button type="button" className="btn btn--secondary" onClick={onClose}>انصراف</button>
        </div>
      </form>
    </Dialog>
  );
}

// -------------------------------------------------------------------------------------------- product
function ProductDetail({ id, styleId }: { id: string; styleId: string | undefined }) {
  const q = useQuery({
    queryKey: [...K2.products, "one", id],
    queryFn: async ({ signal }) => get(`/identity/products/${id}`, g.product, undefined, signal),
  });
  return (
    <>
      <section className="panel" aria-labelledby="product-title" data-testid="product-detail">
        <DataView query={q} loading="در حال دریافت محصول…" errorTitle="محصول دریافت نشد">
          {(r) => <ProductProfile p={r.data} version={r.version} />}
        </DataView>
      </section>
      {q.data ? <StyleColumn product={q.data.data} selected={styleId} /> : null}
      {q.data && styleId ? <StyleDetail product={q.data.data} styleId={styleId} /> : null}
    </>
  );
}

function ProductProfile({ p, version }: { p: Product; version: number | null }) {
  const { can } = useAuth();
  const types = useClasses("product_type");
  const type = types.data?.items.find((t) => t.product_class_id === p.product_class_id);
  const action = useAction();
  const [activating, setActivating] = useState(false);
  return (
    <>
      <div className="panel__head">
        <h2 id="product-title">{p.name_fa}</h2>
        <StatusChip {...toneLabel(MASTER_STATUS, p.status)} testId="product-status" />
      </div>
      <dl className="meta meta--rows">
        <div><dt>نوع محصول</dt><dd>{type ? `${type.label_fa} (${type.segment_value})` : "—"}</dd></div>
        <div><dt>شماره محصول</dt><dd><Num value={p.product_no} testId="product-no" /></dd></div>
        <div><dt>واحد</dt><dd>{UOM[p.uom] ?? p.uom}</dd></div>
        {p.buckle_type_code ? <div><dt>نوع سگک / عرض</dt><dd><Num value={p.buckle_type_code} /> / <Num value={p.belt_width_code} /></dd></div> : null}
      </dl>
      {p.status === "DRAFT" && can(PERM.productManage) ? (
        <button type="button" className="btn btn--secondary" onClick={() => { action.reset(); setActivating(true); }} data-testid="product-activate">
          فعال‌سازی محصول
        </button>
      ) : null}
      {activating ? (
        <ReasonDialog
          title="فعال‌سازی محصول"
          submitLabel="فعال شود"
          action={action}
          onClose={() => { setActivating(false); }}
          onSubmit={async (reason) =>
            (await action.run((key) => send(`/identity/products/${p.product_id}`, g.product, { status: "ACTIVE", reason }, key, version, "PATCH"), [K2.products])) !== undefined
          }
        />
      ) : null}
    </>
  );
}

function StyleColumn({ product, selected }: { product: Product; selected: string | undefined }) {
  const { can } = useAuth();
  const [creating, setCreating] = useState(false);
  const list = useQuery({
    queryKey: [...K2.styles, "of", product.product_id],
    queryFn: async ({ signal }) => (await get(`/identity/products/${product.product_id}/styles`, g.stylePage, { page_size: 100 }, signal)).data,
  });
  return (
    <section className="panel product-styles" aria-labelledby="styles-title" data-fid="product-styles">
      <div className="panel__head">
        <h2 id="styles-title">استایل‌های این محصول</h2>
        {can(PERM.productManage) && product.status !== "RETIRED" ? (
          <button type="button" className="btn btn--primary" onClick={() => { setCreating(true); }} data-testid="style-create-open">
            استایل جدید
          </button>
        ) : null}
      </div>
      <DataView query={list} loading="در حال دریافت استایل‌ها…" errorTitle="استایل‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "هنوز استایلی ندارد." }}>
        {(d) => (
          <ul className="cards cards--row" data-testid="styles-list">
            {d.items.map((s) => (
              <li key={s.style_id} className={s.style_id === selected ? "card card--selected" : "card"}>
                <a href={`#/products/${product.product_id}/${s.style_id}`} className="card__link" data-testid="style-open">
                  استایل <Num value={s.style_no} /> · {s.name_fa}
                </a>
                <StatusChip {...toneLabel(MASTER_STATUS, s.status)} />
              </li>
            ))}
          </ul>
        )}
      </DataView>
      {creating ? <CreateStyleDialog product={product} onClose={() => { setCreating(false); }} /> : null}
    </section>
  );
}

function AttributeFields({ value, onChange }: { value: StyleAttributes; onChange: (v: StyleAttributes) => void }) {
  return (
    <>
      {(Object.keys(ATTRIBUTE_LABEL) as (keyof StyleAttributes)[]).map((k) => (
        <Field key={k} label={ATTRIBUTE_LABEL[k] ?? k}>
          {(id) => (
            <input
              id={id}
              className="input"
              maxLength={k === "notes_fa" ? 500 : 200}
              value={value[k] ?? ""}
              onChange={(e) => { onChange({ ...value, [k]: e.target.value }); }}
              data-testid={`attr-${k}`}
            />
          )}
        </Field>
      ))}
    </>
  );
}

function cleanAttrs(a: StyleAttributes): StyleAttributes {
  const out: StyleAttributes = {};
  for (const k of Object.keys(a) as (keyof StyleAttributes)[]) {
    const v = a[k]?.trim();
    if (v) out[k] = v;
  }
  return out;
}

function CreateStyleDialog({ product, onClose }: { product: Product; onClose: () => void }) {
  const action = useAction();
  const cats = useClasses("category", product.product_class_id);
  const [cat, setCat] = useState("");
  const [name, setName] = useState("");
  const [attrs, setAttrs] = useState<StyleAttributes>({});
  return (
    <Dialog title="استایل جدید" onClose={onClose} testId="style-dialog">
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          const initial = cleanAttrs(attrs);
          void action
            .run(
              (key) =>
                send(`/identity/products/${product.product_id}/styles`, g.style, {
                  category_id: cat,
                  name_fa: name.trim(),
                  ...(Object.keys(initial).length ? { initial_attributes: initial } : {}),
                }, key),
              [K2.styles],
            )
            .then((r) => {
              if (r) {
                onClose();
                navigate(`/products/${product.product_id}/${r.data.style_id}`);
              }
            });
        }}
      >
        <Field label="دسته *">
          {(id) => (
            <select id={id} className="input" required value={cat} onChange={(e) => { setCat(e.target.value); }} data-testid="style-category">
              <option value="">انتخاب کنید</option>
              {(cats.data?.items ?? []).filter((c) => c.status === "ACTIVE").map((c: ProductClass) => (
                <option key={c.product_class_id} value={c.product_class_id}>{c.label_fa} ({c.segment_value})</option>
              ))}
            </select>
          )}
        </Field>
        <Field label="نام استایل *">
          {(id) => <input id={id} className="input" required maxLength={200} value={name} onChange={(e) => { setName(e.target.value); }} data-testid="style-name" />}
        </Field>
        <p className="field__hint">شماره استایل را سرور می‌دهد (از ۰۰۰۱؛ ۰۰۰۰ هرگز صادر نمی‌شود). ویژگی‌ها نسخه ۱ پیش‌نویس استایل می‌شوند.</p>
        <AttributeFields value={attrs} onChange={setAttrs} />
        <SimilarStyles productId={product.product_id} name={name} />
        <ActionError error={action.error} />
        <div className="form__actions">
          <button type="submit" className="btn btn--primary" disabled={action.pending || !cat || !name.trim()} data-testid="style-submit">
            {action.pending ? "در حال ثبت…" : "ثبت استایل (پیش‌نویس)"}
          </button>
          <button type="button" className="btn btn--secondary" onClick={onClose}>انصراف</button>
        </div>
      </form>
    </Dialog>
  );
}

/** Suggestions only (C-71): the user decides; nothing is merged. */
function SimilarStyles({ productId, name }: { productId: string; name: string }) {
  const term = name.trim();
  const q = useQuery({
    queryKey: [...K2.styles, "similar", productId, term],
    enabled: term.length >= 2,
    queryFn: async ({ signal }) => (await get("/identity/style-suggestions", g.suggestions, { q: term, product_id: productId }, signal)).data,
  });
  if (term.length < 2 || !q.data || q.data.items.length === 0) return null;
  return (
    <div className="notice notice--info" data-testid="similar-styles">
      <strong>استایل‌های مشابه موجود (فقط پیشنهاد؛ ادغام انجام نمی‌شود):</strong>
      <ul className="notice__list">
        {q.data.items.slice(0, 5).map((s) => (
          <li key={s.style_id}>
            {s.name_fa} — {s.reasons.includes("SAME_PRODUCT") ? "همین محصول" : "محصول دیگر"}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------- style
function StyleDetail({ product, styleId }: { product: Product; styleId: string }) {
  const q = useQuery({
    queryKey: [...K2.styles, "one", styleId],
    queryFn: async ({ signal }) => get(`/identity/styles/${styleId}`, g.style, undefined, signal),
  });
  return (
    <section className="panel panel--wide" aria-labelledby="style-title" data-testid="style-detail">
      <DataView query={q} loading="در حال دریافت استایل…" errorTitle="استایل دریافت نشد">
        {(r) => (
          <>
            <StyleHead s={r.data} version={r.version} product={product} />
            <StyleCode s={r.data} product={product} />
            <Revisions s={r.data} />
          </>
        )}
      </DataView>
    </section>
  );
}

/** DEC-005 amendment 2026-11-18 (REV-0293): style activation and code issue need an ACTIVE product. */
const PRODUCT_NOT_ACTIVE_HINT = "ابتدا محصول را فعال کنید";

function StyleHead({ s, version, product }: { s: Style; version: number | null; product: Product }) {
  const { can } = useAuth();
  const action = useAction();
  const [activating, setActivating] = useState(false);
  return (
    <>
      <div className="panel__head">
        <h2 id="style-title">
          استایل <Num value={s.style_no} /> · {s.name_fa}
        </h2>
        <StatusChip {...toneLabel(MASTER_STATUS, s.status)} testId="style-status" />
      </div>
      <p className="panel__meta">محصول: {product.name_fa} · ثبت {formatJalaliDateTime(s.created_at)}</p>
      {s.status === "DRAFT" && can(PERM.productManage) ? (
        <div className="actions">
          {/* DEC-005 amendment 2026-11-18 (REV-0293): only under an ACTIVE product; the server refuses it too. */}
          <button
            type="button"
            className="btn btn--secondary"
            disabled={product.status !== "ACTIVE"}
            aria-describedby={product.status !== "ACTIVE" ? "style-activate-hint" : undefined}
            onClick={() => { action.reset(); setActivating(true); }}
            data-testid="style-activate"
          >
            فعال‌سازی استایل
          </button>
          {product.status !== "ACTIVE" ? (
            <span id="style-activate-hint" className="field__hint" data-testid="style-activate-hint">
              {PRODUCT_NOT_ACTIVE_HINT}
            </span>
          ) : null}
        </div>
      ) : null}
      {activating ? (
        <ReasonDialog
          title="فعال‌سازی استایل"
          submitLabel="فعال شود"
          action={action}
          onClose={() => { setActivating(false); }}
          onSubmit={async (reason) =>
            (await action.run((key) => send(`/identity/styles/${s.style_id}`, g.style, { status: "ACTIVE", reason }, key, version, "PATCH"), [K2.styles])) !== undefined
          }
        />
      ) : null}
    </>
  );
}

function StyleCode({ s, product }: { s: Style; product: Product }) {
  const { can } = useAuth();
  const codes = useQuery({
    queryKey: [...K2.codes, "of", s.style_id],
    enabled: can(PERM.codeRead),
    queryFn: async ({ signal }) => (await get("/identity/product-codes", g.codePage, { style_id: s.style_id, page_size: 25 }, signal)).data,
  });
  const preview = useAction();
  const issue = useAction();
  const [shown, setShown] = useState<{ code: string; rule: string | null } | null>(null);
  if (!can(PERM.codeRead)) return null;
  return (
    <section aria-labelledby="code-title" className="subsection">
      <h3 id="code-title">کد ۱۴رقمی (DEC-005)</h3>
      <DataView query={codes} loading="در حال دریافت کد…" errorTitle="کد دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "هنوز کدی برای این استایل صادر نشده است." }}>
        {(d) => (
          <ul className="list" data-testid="style-codes">
            {d.items.map((c) => (
              <li key={c.product_code_id}>
                <Code14 code={c.code} copy testId="issued-code" /> <StatusChip {...toneLabel(CODE_STATUS, c.status)} />{" "}
                <span className="field__hint">{c.erp_status ? (ERP_STATUS[c.erp_status] ?? c.erp_status) : ""}</span>
              </li>
            ))}
          </ul>
        )}
      </DataView>
      {codes.data && codes.data.items.length === 0 ? (
        <div className="actions">
          <button
            type="button"
            className="btn btn--secondary"
            disabled={preview.pending}
            onClick={() => {
              void preview.run(() => probe("/identity/product-codes/preview", g.preview, { style_id: s.style_id })).then((r) => {
                if (r) setShown({ code: r.data.code, rule: r.data.rule_revision_id });
              });
            }}
            data-testid="code-preview"
          >
            پیش‌نمایش کد
          </button>
          {shown && can(PERM.codeIssue) ? (
            <button
              type="button"
              className="btn btn--primary"
              disabled={issue.pending || s.status !== "ACTIVE" || product.status !== "ACTIVE"}
              aria-describedby={product.status !== "ACTIVE" ? "code-issue-hint" : undefined}
              onClick={() => {
                void issue.run((key) => send("/identity/product-codes", g.code, { style_id: s.style_id, ...(shown.rule ? { rule_revision_id: shown.rule } : {}) }, key), [K2.codes]);
              }}
              data-testid="code-issue"
            >
              {issue.pending ? "در حال صدور…" : "صدور و رزرو کد"}
            </button>
          ) : null}
        </div>
      ) : null}
      {shown && codes.data?.items.length === 0 ? (
        <p data-testid="code-preview-value">
          کد پیش‌نمایش (هنوز رزرو نشده): <Code14 code={shown.code} />
          {product.status !== "ACTIVE" ? (
            <span id="code-issue-hint" className="field__hint" data-testid="code-issue-hint"> — {PRODUCT_NOT_ACTIVE_HINT}</span>
          ) : s.status !== "ACTIVE" ? (
            <span className="field__hint"> — برای صدور، استایل باید فعال باشد.</span>
          ) : null}
        </p>
      ) : null}
      <ActionError error={preview.error ?? issue.error} />
      <p className="field__hint">کد صادرشده رزرو و «منتظر ثبت دستی در راهکاران» است؛ سامانه چیزی در راهکاران نمی‌نویسد.</p>
    </section>
  );
}

function Revisions({ s }: { s: Style }) {
  const { can } = useAuth();
  const list = useQuery({
    queryKey: [...K2.styles, "revisions", s.style_id],
    queryFn: async ({ signal }) => (await get(`/identity/styles/${s.style_id}/revisions`, g.revisionPage, { page_size: 100 }, signal)).data,
  });
  const action = useAction();
  const [activate, setActivate] = useState<StyleRevision | null>(null);
  const [creating, setCreating] = useState(false);
  const [attrs, setAttrs] = useState<StyleAttributes>({});
  const [revReason, setRevReason] = useState("");
  return (
    <section aria-labelledby="rev-title" className="subsection">
      <div className="panel__head">
        <h3 id="rev-title">نسخه‌های استایل (رنگ، جنس، یراق)</h3>
        {can(PERM.productManage) ? (
          <button type="button" className="btn btn--secondary" onClick={() => { setCreating(true); }} data-testid="revision-create-open">نسخه جدید</button>
        ) : null}
      </div>
      <DataView query={list} loading="در حال دریافت نسخه‌ها…" errorTitle="نسخه‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "نسخه‌ای ثبت نشده است؛ برای سفارش یک نسخه فعال لازم است." }}>
        {(d) => (
          <table className="table table--cards" data-testid="revisions-table">
            <caption className="sr-only">نسخه‌های استایل</caption>
            <thead>
              <tr>
                <th scope="col">نسخه</th>
                <th scope="col">ویژگی‌ها</th>
                <th scope="col">وضعیت</th>
                <th scope="col"><span className="sr-only">اقدام</span></th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((r) => (
                <tr key={r.style_revision_id}>
                  <td data-label="نسخه">R{toFaDigits(r.revision_no)}</td>
                  <td data-label="ویژگی‌ها"><Attrs a={r.attributes} /></td>
                  <td data-label="وضعیت"><StatusChip {...toneLabel(MASTER_STATUS, r.status)} /></td>
                  <td data-label="اقدام">
                    {r.status === "DRAFT" && can(PERM.productManage) ? (
                      <button type="button" className="btn btn--secondary btn--small" onClick={() => { action.reset(); setActivate(r); }} data-testid="revision-activate">فعال‌سازی</button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </DataView>
      {activate ? (
        <ReasonDialog
          title={`فعال‌سازی نسخه R${toFaDigits(activate.revision_no)}`}
          description="نسخه فعال قبلی «جایگزین‌شده» می‌شود؛ سریال‌های موجود Snapshot خود را نگه می‌دارند."
          submitLabel="فعال شود"
          action={action}
          onClose={() => { setActivate(null); }}
          onSubmit={async (reason) =>
            (await action.run(
              (key) => send(`/identity/styles/${s.style_id}/revisions/${activate.style_revision_id}/activate`, g.revision, { reason }, key, activate.row_version),
              [K2.styles],
            )) !== undefined
          }
        />
      ) : null}
      {creating ? (
        <Dialog title="نسخه جدید استایل" onClose={() => { setCreating(false); }} testId="revision-dialog">
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              void action
                .run((key) => send(`/identity/styles/${s.style_id}/revisions`, g.revision, { attributes: cleanAttrs(attrs), reason: revReason.trim() }, key), [K2.styles])
                .then((r) => {
                  if (r) setCreating(false);
                });
            }}
          >
            <AttributeFields value={attrs} onChange={setAttrs} />
            <Field label="دلیل (در ممیزی ثبت می‌شود) *">
              {(id) => <input id={id} className="input" required minLength={3} maxLength={500} value={revReason} onChange={(e) => { setRevReason(e.target.value); }} />}
            </Field>
            <ActionError error={action.error} />
            <div className="form__actions">
              <button type="submit" className="btn btn--primary" disabled={action.pending || Object.keys(cleanAttrs(attrs)).length === 0 || revReason.trim().length < 3}>ثبت نسخه (پیش‌نویس)</button>
              <button type="button" className="btn btn--secondary" onClick={() => { setCreating(false); }}>انصراف</button>
            </div>
          </form>
        </Dialog>
      ) : null}
    </section>
  );
}

function Attrs({ a }: { a: StyleAttributes }) {
  const entries = Object.entries(a).filter(([, v]) => v);
  if (entries.length === 0) return <span>—</span>;
  return (
    <span>
      {entries.map(([k, v], i) => (
        <span key={k}>
          {i > 0 ? " · " : ""}
          {ATTRIBUTE_LABEL[k] ?? k}: {v}
        </span>
      ))}
    </span>
  );
}

// ---------------------------------------------------------------------------------- style 360 view
// REV-0295 / DEC-061: page 4 laid out as the catalogue «product_style_360»: header + actions, five KPI cards,
// filter bar, product identity card (with this product's styles) next to the related serials, the later-phase
// production distribution and events, then the style's own technical detail (code, revisions) and the product
// list. Every number is server data; later-phase parts show the placeholder without numbers.

interface SerialFilter {
  status: string;
  customer: string;
  colour: string;
  material: string;
  from: string | null;
  to: string | null;
}
const NO_FILTER: SerialFilter = { status: "", customer: "", colour: "", material: "", from: null, to: null };

function Style360({ productId, styleId }: { productId: string; styleId: string }) {
  const { can } = useAuth();
  const [filter, setFilter] = useState<SerialFilter>(NO_FILTER);
  const [filterKey, setFilterKey] = useState(0); // remounts the date inputs when the filters are cleared
  const [creating, setCreating] = useState(false);
  const cursor = useCursor();
  const product = useQuery({
    queryKey: [...K2.products, "one", productId],
    queryFn: async ({ signal }) => get(`/identity/products/${productId}`, g.product, undefined, signal),
  });
  const revisions = useQuery({
    queryKey: [...K2.styles, "revisions", styleId],
    queryFn: async ({ signal }) => (await get(`/identity/styles/${styleId}/revisions`, g.revisionPage, { page_size: 100 }, signal)).data,
  });
  const tracking = useQuery({
    queryKey: [...K2.styles, "tracking", styleId, filter, cursor.cursor],
    queryFn: async ({ signal }) =>
      (
        await get(
          `/identity/styles/${styleId}/tracking`,
          g.styleTracking,
          {
            status: filter.status || undefined,
            customer_id: filter.customer || undefined,
            colour: filter.colour || undefined,
            material: filter.material || undefined,
            from: filter.from ?? undefined,
            to: filter.to ?? undefined,
            cursor: cursor.cursor,
            page_size: 25,
          },
          signal,
        )
      ).data,
  });
  const set = (patch: Partial<SerialFilter>) => {
    cursor.reset();
    setFilter((f) => ({ ...f, ...patch }));
  };
  const active = JSON.stringify(filter) !== JSON.stringify(NO_FILTER);
  const c = tracking.data?.counts;
  const num = (v: number | null | undefined) => (tracking.isPending ? "…" : v === null || v === undefined ? "بدون مجوز" : toFaDigits(v));
  return (
    <>
      <PageHead
        compact
        page="صفحه ۴ · فاز ۲ · Product 360"
        title="ردیابی محصولات و استایل‌ها"
        lead={product.data ? `محصول ${product.data.data.name_fa} · شماره ${product.data.data.product_no}` : "محصول، استایل و سریال‌های مرتبط"}
        actions={
          <>
            <button
              type="button"
              className="btn btn--outline btn--compact"
              disabled={!active}
              title={active ? undefined : "فیلتری فعال نیست"}
              onClick={() => {
                setFilter(NO_FILTER);
                setFilterKey((k) => k + 1);
                cursor.reset();
              }}
              data-testid="filters-clear"
            >
              <Icon name="clear" size={16} />
              پاک‌کردن فیلترها
            </button>
            <DisabledAction label="خروجی Excel" icon="download" reason="خروجی Excel در دست ساخت است: قالب و مجوز خروجی (با ممیزی) هنوز تعریف نشده است." testId="export-disabled" />
            {can(PERM.productManage) ? (
              <button type="button" className="btn btn--primary btn--compact" onClick={() => { setCreating(true); }} data-testid="product-create-open">
                <Icon name="plus" size={16} />
                محصول / استایل جدید
              </button>
            ) : (
              <DisabledAction primary icon="plus" label="محصول / استایل جدید" reason="برای ساخت محصول یا استایل مجوز مدیریت داده محصول لازم است." />
            )}
          </>
        }
      />
      {creating ? <CreateProductDialog onClose={() => { setCreating(false); }} /> : null}
      <ul className="kpis kpis--5" data-testid="style-counts" data-fid="kpis" aria-label="شاخص‌های این استایل">
        <Kpi
          label="سریال‌های مرتبط"
          value={num(c?.serials_total)}
          note={c?.serials_active != null ? `فعال: ${toFaDigits(c.serials_active)}` : "سریال‌های این استایل"}
          bar={{ share: c?.serials_total && c.serials_active != null ? c.serials_active / c.serials_total : null, label: "سهم سریال‌های فعال" }}
        />
        <Kpi label="سفارش‌های فعال" value={num(c?.orders_active)} note="تأییدشده، ارسال‌شده یا متوقف" bar={{ share: null }} />
        <Kpi label="مجموع تعداد سفارش" value={num(c?.quantity_total)} note="ردیف‌های تأییدشده سفارش‌های فعال" bar={{ share: null }} />
        <LaterKpi label="در جریان تولید" phase="PHASE_07" bar />
        <LaterKpi label="تعهدهای در معرض ریسک" phase="PHASE_05" bar />
      </ul>
      {(tracking.data?.withheld_sections ?? []).length > 0 ? (
        <p className="notice notice--info" data-testid="withheld">بخشی از داده برای نقش شما نمایش داده نمی‌شود (مجوز خواندن ندارید).</p>
      ) : null}
      <SerialFilters key={filterKey} filter={filter} set={set} revisions={revisions.data?.items ?? []} />
      <div className="grid-side">
        <section className="panel product-card" aria-labelledby="product-title" data-testid="product-detail" data-fid="product-card">
          <DataView query={product} loading="در حال دریافت محصول…" errorTitle="محصول دریافت نشد">
            {(r) => (
              <>
                <p className="product-card__kicker">شناسنامه محصول</p>
                {/* no product image exists in PHASE_02 data: an honest placeholder in the catalogue's picture slot */}
                <div className="product-card__image" role="img" aria-label="تصویر محصول ثبت نشده">
                  <Icon name="image" size={30} />
                  <span aria-hidden="true">تصویر محصول ثبت نشده</span>
                </div>
                <ProductProfile p={r.data} version={r.version} />
                <ProductFacts styleId={styleId} productId={productId} activeSerials={c?.serials_active} revisions={revisions.data?.items} />
                <StyleColumn product={r.data} selected={styleId} />
              </>
            )}
          </DataView>
        </section>
        <section className="panel panel--table" aria-labelledby="ser-title" data-fid="serial-table">
          <div className="panel__head">
            <h2 id="ser-title">سریال‌های مرتبط با محصول / استایل</h2>
            {tracking.data && c?.serials_total != null ? <span className="field__hint">{toFaDigits(tracking.data.serials.length)} سریال در این صفحه</span> : null}
          </div>
          <div className="segmented" role="group" aria-label="وضعیت سریال">
            {[
              { v: "", l: "همه" },
              { v: "ALLOCATED", l: "تخصیص‌یافته" },
              { v: "CANCELLED", l: "لغوشده" },
            ].map((o) => (
              <button key={o.v || "all"} type="button" className={filter.status === o.v ? "btn chipbtn chipbtn--on" : "btn chipbtn"} aria-pressed={filter.status === o.v} onClick={() => { set({ status: o.v }); }}>
                {o.l}
              </button>
            ))}
          </div>
          <DataView query={tracking} loading="در حال دریافت سریال‌ها…" errorTitle="سریال‌ها دریافت نشد">
            {(d) => <SerialRows d={d} />}
          </DataView>
          <p className="field__hint later-note">مرحله فعلی، پیشرفت و تعهد هر سریال: در دست ساخت (فاز مالک <bdi dir="ltr">PHASE_07 / PHASE_05</bdi>).</p>
          {tracking.data ? <Pager depth={cursor.depth} next={tracking.data.page.next_cursor} onNext={cursor.next} onPrev={cursor.prev} /> : null}
        </section>
      </div>
      <div className="grid-half grid-half--lower">
        <LaterSection title="توزیع سریال‌ها در چرخه تولید" phase="PHASE_07" fid="stage-distribution" icon="chart" rails={["بازرگانی / برنامه", "مواد و انبار", "برش / تولید", "کنترل کیفیت", "انبار محصول / ارسال"]} />
        <LaterSection title="آخرین رخدادهای مرتبط" phase="PHASE_07" fid="events" icon="clock" />
      </div>
      {product.data ? <StyleDetail product={product.data.data} styleId={styleId} /> : null}
      <div className="split split--after">
        <ProductList selected={productId} />
      </div>
    </>
  );
}

function SerialFilters({ filter, set, revisions }: { filter: SerialFilter; set: (p: Partial<SerialFilter>) => void; revisions: StyleRevision[] }) {
  const names = useCustomerNames();
  const colours = [...new Set(revisions.map((r) => r.attributes.colour_fa).filter((v): v is string => !!v))];
  const materials = [...new Set(revisions.map((r) => r.attributes.main_material_fa).filter((v): v is string => !!v))];
  return (
    <section className="panel filterbar" aria-label="فیلتر سریال‌های مرتبط" data-fid="filters">
      <ProductSearch />
      <Field label="مشتری / برند">
        {(id) => (
          <select id={id} className="input" value={filter.customer} onChange={(e) => { set({ customer: e.target.value }); }} data-testid="filter-customer">
            <option value="">همه مشتریان</option>
            {[...names.values()].map((x) => <option key={x.customer_id} value={x.customer_id}>{x.display_name_fa}</option>)}
          </select>
        )}
      </Field>
      <Field label="جنس اصلی">
        {(id) => (
          <select id={id} className="input" value={filter.material} onChange={(e) => { set({ material: e.target.value }); }} data-testid="filter-material">
            <option value="">همه جنس‌ها</option>
            {materials.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        )}
      </Field>
      <Field label="رنگ اصلی">
        {(id) => (
          <select id={id} className="input" value={filter.colour} onChange={(e) => { set({ colour: e.target.value }); }} data-testid="filter-colour">
            <option value="">همه رنگ‌ها</option>
            {colours.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        )}
      </Field>
      <Field label="موقعیت سریال">
        {(id) => (
          <select id={id} className="input" value={filter.status} onChange={(e) => { set({ status: e.target.value }); }} data-testid="filter-status">
            <option value="">همه وضعیت‌ها</option>
            <option value="ALLOCATED">تخصیص‌یافته</option>
            <option value="CANCELLED">لغوشده</option>
          </select>
        )}
      </Field>
      <div className="field filterbar__period">
        <span className="field__label">دوره سفارش (تاریخ تخصیص)</span>
        <div className="filterbar__dates">
          <DateInput label="از تاریخ تخصیص" value={filter.from} onChange={(v) => { set({ from: v }); }} />
          <DateInput label="تا تاریخ تخصیص" value={filter.to} onChange={(v) => { set({ to: v }); }} />
        </div>
      </div>
    </section>
  );
}

/** Compact Jalali date input for the filter bar (the full field with hint is JalaliDateField). */
function DateInput({ label, value, onChange }: { label: string; value: string | null; onChange: (iso: string | null) => void }) {
  const [text, setText] = useState(() => isoToJalaliInput(value));
  const iso = text ? jalaliInputToIso(text) : null;
  return (
    <input
      className="input"
      dir="ltr"
      inputMode="numeric"
      placeholder="____/__/__"
      aria-label={`${label} (سال/ماه/روز شمسی)`}
      aria-invalid={text !== "" && iso === null}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        const v = e.target.value ? jalaliInputToIso(e.target.value) : null;
        if (!e.target.value || v) onChange(v);
      }}
    />
  );
}

/** Product / style search of the filter bar: products by name or number, styles by name (links). */
function ProductSearch() {
  const id = useId();
  const [text, setText] = useState("");
  const term = text.trim();
  const q = useQuery({
    queryKey: [...K2.products, "search", term],
    enabled: term.length >= 2,
    queryFn: async ({ signal }) => {
      const [p, s] = await Promise.all([
        get("/identity/products", g.productPage, { q: term, page_size: 5 }, signal),
        get("/identity/style-suggestions", g.suggestions, { q: term }, signal),
      ]);
      return { products: p.data.items, styles: s.data.items.slice(0, 5) };
    },
  });
  return (
    <div className="field filterbar__search">
      <label className="field__label" htmlFor={id}>جستجوی محصول یا استایل (نام یا شماره)</label>
      <input id={id} className="input" type="search" maxLength={100} value={text} onChange={(e) => { setText(e.target.value); }} placeholder="مثلاً نام یا شماره محصول" data-testid="product-style-search" />
      {term.length >= 2 && q.data ? (
        <ul className="filterbar__results" data-testid="product-style-results">
          {q.data.products.map((p) => (
            <li key={p.product_id}><a href={`#/products/${p.product_id}`}>محصول {p.name_fa} · <bdi dir="ltr">{p.product_no}</bdi></a></li>
          ))}
          {q.data.styles.map((s) => (
            <li key={s.style_id}><a href={`#/products/${s.product_id}/${s.style_id}`}>استایل {s.name_fa}</a></li>
          ))}
          {q.data.products.length + q.data.styles.length === 0 ? <li className="field__hint">موردی پیدا نشد.</li> : null}
        </ul>
      ) : null}
    </div>
  );
}

function ProductFacts({ productId, styleId, activeSerials, revisions }: { productId: string; styleId: string; activeSerials: number | null | undefined; revisions: StyleRevision[] | undefined }) {
  const styles = useQuery({
    queryKey: [...K2.styles, "of", productId],
    queryFn: async ({ signal }) => (await get(`/identity/products/${productId}/styles`, g.stylePage, { page_size: 100 }, signal)).data,
  });
  const latest = revisions && revisions.length ? revisions.reduce((a, b) => (b.revision_no > a.revision_no ? b : a)) : null;
  return (
    <dl className="facts" data-testid="product-facts" data-style={styleId}>
      <div><dt>تعداد استایل</dt><dd>{styles.data ? toFaDigits(styles.data.items.length) : "…"}</dd></div>
      <div><dt>گرید پیش‌فرض</dt><dd title="مقایسه گرید تا تصمیم DEC-019 تعریف نشده است">تعریف نشده (DEC-019)</dd></div>
      <div><dt>آخرین نسخه فنی</dt><dd>{latest ? `R${toFaDigits(latest.revision_no)} · ${MASTER_STATUS[latest.status]?.label ?? latest.status}` : revisions ? "ندارد" : "…"}</dd></div>
      <div><dt>سریال‌های فعال</dt><dd>{activeSerials === undefined ? "…" : activeSerials === null ? "بدون مجوز" : toFaDigits(activeSerials)}</dd></div>
    </dl>
  );
}

const LATER_CELL = "در دست ساخت";

/** Later-phase cell in the catalogue form: a neutral dot (stage) or an empty rail (progress), never a value. */
function LaterCell({ kind }: { kind: "dot" | "rail" | "text" }) {
  return (
    <span className="later-cell" title="در دست ساخت">
      {kind === "dot" ? <span className="later-cell__dot" aria-hidden="true" /> : kind === "rail" ? <span className="later-cell__rail" aria-hidden="true" /> : null}
      {LATER_CELL}
    </span>
  );
}

function SerialRows({ d }: { d: StyleTracking }) {
  const names = useCustomerNames();
  const phone = useMediaQuery("(max-width: 600px)");
  if (d.serials.length === 0) return <p className="state state--empty" data-testid="state-empty">سریالی برای این استایل با این فیلتر نیست.</p>;
  if (phone) {
    // phone (catalogue): one card per serial instead of the table
    return (
      <ul className="serial-cards-list" data-testid="style-serials" aria-label="سریال‌های استایل با رنگ و جنس واقعی هر سریال">
        {d.serials.map((x) => {
          const o = x.order_id ? d.orders?.[x.order_id] : undefined;
          return (
            <li key={x.serial_id} className="serial-card">
              <div className="serial-card__head">
                <a href={`#/serials/${x.serial_id}`}><Num value={x.serial_number} /></a>
                <StatusChip {...toneLabel(SERIAL_STATUS, x.status)} />
              </div>
              <dl className="serial-card__facts">
                <div><dt>استایل</dt><dd><Num value={d.style.style_no} /></dd></div>
                <div><dt>تعداد</dt><dd>{x.quantity !== null ? `${toFaDigits(x.quantity)} ${UOM[x.uom ?? ""] ?? ""}` : "—"}</dd></div>
                <div><dt>دوره سفارش</dt><dd>{o?.program_ref ?? "—"}</dd></div>
                <div><dt>گرید</dt><dd>{o?.required_quality_requirement ?? "—"}</dd></div>
                <div className="serial-card__wide"><dt>مشتری</dt><dd><CustomerName id={x.customer_id} names={names} /></dd></div>
                <div className="serial-card__wide"><dt>جنس و رنگ واقعی</dt><dd><Attrs a={x.attributes} /></dd></div>
              </dl>
            </li>
          );
        })}
      </ul>
    );
  }
  return (
    <div className="tablewrap">
      <table className="table table--cards" data-testid="style-serials">
        <caption className="sr-only">سریال‌های استایل با رنگ و جنس واقعی هر سریال (مرحله، پیشرفت و تعهد در فازهای ۵ و ۷)</caption>
        <thead>
          <tr>
            <th scope="col">سریال</th>
            <th scope="col">استایل</th>
            <th scope="col" title="فاز مالک: PHASE_07">مرحله فعلی</th>
            <th scope="col" title="فاز مالک: PHASE_07">پیشرفت</th>
            <th scope="col">مشتری</th>
            <th scope="col">جنس و رنگ واقعی</th>
            <th scope="col">دوره سفارش</th>
            <th scope="col">تعداد</th>
            <th scope="col">گرید</th>
            <th scope="col" title="فاز مالک: PHASE_05">تعهد</th>
          </tr>
        </thead>
        <tbody>
          {d.serials.map((x) => {
            const o = x.order_id ? d.orders?.[x.order_id] : undefined;
            return (
              <tr key={x.serial_id}>
                <td data-label="سریال" className="cell--serial"><a href={`#/serials/${x.serial_id}`}><Num value={x.serial_number} /></a> <StatusChip {...toneLabel(SERIAL_STATUS, x.status)} /></td>
                <td data-label="استایل" className="cell--style"><Num value={d.style.style_no} /></td>
                <td data-label="مرحله فعلی" className="cell--later"><LaterCell kind="dot" /></td>
                <td data-label="پیشرفت" className="cell--later"><LaterCell kind="rail" /></td>
                <td data-label="مشتری" className="cell--wide"><span className="cell-clip" title={names.get(x.customer_id)?.display_name_fa}><CustomerName id={x.customer_id} names={names} /></span></td>
                <td data-label="جنس و رنگ واقعی" className="cell--wide"><span className="cell-clip"><Attrs a={x.attributes} /></span></td>
                <td data-label="دوره سفارش">{o?.program_ref ?? "—"}</td>
                <td data-label="تعداد">{x.quantity !== null ? `${toFaDigits(x.quantity)} ${UOM[x.uom ?? ""] ?? ""}` : "—"}</td>
                <td data-label="گرید">{o?.required_quality_requirement ?? "—"}</td>
                <td data-label="تعهد" className="cell--later"><LaterCell kind="text" /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// --------------------------------------------------------------------------------------- code check
function CodeCheck() {
  const { can } = useAuth();
  const action = useAction();
  const [code, setCode] = useState("");
  const [result, setResult] = useState<{ reasons: string[]; ok: boolean } | null>(null);
  if (!can(PERM.codeRead)) {
    return (
      <section className="panel">
        <p className="state state--empty" data-testid="state-empty">یک محصول را از فهرست انتخاب کنید.</p>
      </section>
    );
  }
  return (
    <section className="panel" aria-labelledby="check-title" data-testid="code-check">
      <h2 id="check-title">بررسی کد ۱۴رقمی</h2>
      <p className="lead">کد دقیقاً همان‌طور که نوشته شده بررسی می‌شود؛ رقم فارسی، فاصله یا نویسه دیگر اصلاح خودکار نمی‌شود.</p>
      <form
        className="form form--inline"
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(() => probe("/identity/product-codes/validate", g.validation, { code, code_namespace: "product_code" })).then((r) => {
            if (r) setResult({ reasons: r.data.reasons, ok: r.data.reasons.length === 0 });
          });
        }}
      >
        <Field label="کد">
          {(id) => <input id={id} className="input code14" dir="ltr" maxLength={64} value={code} onChange={(e) => { setCode(e.target.value); setResult(null); }} data-testid="code-check-input" />}
        </Field>
        <button type="submit" className="btn btn--secondary" disabled={action.pending || !code} data-testid="code-check-submit">بررسی</button>
      </form>
      <ActionError error={action.error} />
      {result ? (
        result.ok ? (
          <p className="notice notice--info" data-testid="code-check-ok">کد معتبر است و در ثبت کدها وجود دارد.</p>
        ) : (
          <ul className="notice notice--warning notice__list" data-testid="code-check-reasons">
            {result.reasons.map((r) => <li key={r}>{CODE_CHECK_REASONS[r] ?? r}</li>)}
          </ul>
        )
      ) : null}
    </section>
  );
}
