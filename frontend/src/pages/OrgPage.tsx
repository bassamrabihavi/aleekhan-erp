// Organisational tree (DEC-043 / DEC-048, MOCK_UI_BINDING §6.6): units -> positions -> holders, WAI-ARIA tree
// with keyboard navigation; on mobile the same tree renders as nested cards. Changes take effect from now on
// only (no back-dating); a unit-head position has exactly one PRIMARY holder (stand-in = ACTING with end date).
// Holding a position grants no permission (DEC-048: PHASE_01 approval routing = role + unit scope only).
import { useQuery } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";

import { orgGuards, read, write, type OrgTreeNode, type OrgUnit } from "../api/phase01";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView } from "../components/DataView";
import { Dialog } from "../components/Dialog";
import { Field, ReasonDialog } from "../components/Form";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import { localInputToUtc, nowUtc, QK, useUnitOptions, useUserOptions } from "../lib/queries";
import { useAction } from "../lib/useAction";

const MANAGE = "platform.org.manage";
const UNIT_TYPES: Record<string, string> = { COMPANY: "شرکت", DEPARTMENT: "معاونت/اداره", SECTION: "بخش", LINE: "خط" };

interface FlatItem {
  key: string;
  level: number;
  kind: "unit" | "position";
  label: string;
  detail: string;
  expandable: boolean;
  parentKey: string | null;
  unit?: OrgUnit;
}

function flatten(roots: OrgTreeNode[], collapsed: ReadonlySet<string>): FlatItem[] {
  const out: FlatItem[] = [];
  function walk(n: OrgTreeNode, level: number, parentKey: string | null): void {
    const key = `u:${n.unit.unit_id}`;
    const expandable = n.positions.length > 0 || n.children.length > 0;
    out.push({
      key,
      level,
      kind: "unit",
      label: n.unit.name_fa,
      detail: `${UNIT_TYPES[n.unit.unit_type] ?? n.unit.unit_type} · ${n.unit.code}${n.unit.status === "INACTIVE" ? " · غیرفعال" : ""}`,
      expandable,
      parentKey,
      unit: n.unit,
    });
    if (collapsed.has(key)) return;
    for (const p of n.positions) {
      const holders = p.holders.map((h) => `${h.display_name}${h.kind === "ACTING" ? " (سرپرست موقت)" : ""}`).join("، ");
      out.push({
        key: `p:${p.position.position_id}`,
        level: level + 1,
        kind: "position",
        label: `${p.position.title_fa}${p.position.is_unit_head ? " — رئیس واحد" : ""}`,
        detail: holders ? `متصدی: ${holders}` : "بدون متصدی",
        expandable: false,
        parentKey: key,
      });
    }
    for (const c of n.children) walk(c, level + 1, key);
  }
  for (const r of roots) walk(r, 1, null);
  return out;
}

function allUnitKeys(roots: OrgTreeNode[]): string[] {
  const out: string[] = [];
  const walk = (n: OrgTreeNode): void => {
    out.push(`u:${n.unit.unit_id}`);
    n.children.forEach(walk);
  };
  roots.forEach(walk);
  return out;
}

export function OrgPage() {
  const { can } = useAuth();
  const tree = useQuery({
    queryKey: [...QK.org, "tree"],
    queryFn: async ({ signal }) => (await read("/org/tree", orgGuards.tree, { depth: 6 }, signal)).data,
  });
  const [dialog, setDialog] = useState<"unit" | "position" | "assign" | null>(null);
  return (
    <div className="page" data-testid="page-org">
      <div className="page__head">
        <div>
          <p className="eyebrow">درخت سازمانی · فاز ۱ (DEC-043، DEC-048)</p>
          <h1>درخت سازمانی</h1>
          <p className="lead">
            واحدها، سمت‌ها و متصدیان. تغییرات فقط از همین لحظه اثر دارند (تاریخ گذشته ممنوع). داشتن سمت به‌تنهایی هیچ مجوزی
            نمی‌دهد؛ مجوزها فقط از نقش‌ها می‌آیند.
          </p>
        </div>
        {can(MANAGE) ? (
          <div className="toolbar">
            <button type="button" className="btn btn--primary" onClick={() => { setDialog("unit"); }} data-testid="org-new-unit">واحد تازه</button>
            <button type="button" className="btn btn--secondary" onClick={() => { setDialog("position"); }} data-testid="org-new-position">سمت تازه</button>
            <button type="button" className="btn btn--secondary" onClick={() => { setDialog("assign"); }} data-testid="org-new-assignment">انتصاب فرد به سمت</button>
          </div>
        ) : null}
      </div>
      <DataView query={tree} loading="در حال دریافت درخت سازمانی…" errorTitle="درخت سازمانی دریافت نشد" isEmpty={(d) => d.roots.length === 0} empty={{ title: "هنوز واحدی تعریف نشده است.", hint: can(MANAGE) ? "با «واحد تازه» نخستین واحد (شرکت) را بسازید." : undefined }}>
        {(d) => (
          <section className="panel panel--wide" aria-labelledby="tree-title">
            <div className="panel__head">
              <h2 id="tree-title">ساختار در لحظه {formatJalaliDateTime(d.as_of)}</h2>
            </div>
            <OrgTreeView roots={d.roots} canManage={can(MANAGE)} />
          </section>
        )}
      </DataView>
      {dialog === "unit" ? <UnitDialog onClose={() => { setDialog(null); }} /> : null}
      {dialog === "position" ? <PositionDialog onClose={() => { setDialog(null); }} /> : null}
      {dialog === "assign" ? <AssignDialog onClose={() => { setDialog(null); }} /> : null}
    </div>
  );
}

function OrgTreeView({ roots, canManage }: { roots: OrgTreeNode[]; canManage: boolean }) {
  // collapsed set (not expanded): units added later appear expanded, like the rest of the tree
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set());
  const expanded = useMemo(() => new Set(allUnitKeys(roots).filter((k) => !collapsed.has(k))), [roots, collapsed]);
  const items = useMemo(() => flatten(roots, collapsed), [roots, collapsed]);
  const [focusKey, setFocusKey] = useState<string | null>(items[0]?.key ?? null);
  const [selected, setSelected] = useState<OrgUnit | null>(null);
  const refs = useRef(new Map<string, HTMLDivElement>());
  const active = items.some((i) => i.key === focusKey) ? focusKey : (items[0]?.key ?? null);

  function focus(key: string | null | undefined): void {
    if (!key) return;
    setFocusKey(key);
    refs.current.get(key)?.focus();
  }
  function toggle(key: string, open?: boolean): void {
    setCollapsed((s) => {
      const n = new Set(s);
      const willOpen = open ?? n.has(key);
      if (willOpen) n.delete(key);
      else n.add(key);
      return n;
    });
  }
  function onKey(e: React.KeyboardEvent, i: number): void {
    const it = items[i];
    if (!it) return;
    // RTL tree: ArrowLeft opens / goes to the first child, ArrowRight closes / goes to the parent
    switch (e.key) {
      case "ArrowDown":
        focus(items[i + 1]?.key);
        break;
      case "ArrowUp":
        focus(items[i - 1]?.key);
        break;
      case "Home":
        focus(items[0]?.key);
        break;
      case "End":
        focus(items[items.length - 1]?.key);
        break;
      case "ArrowLeft":
        if (it.expandable && !expanded.has(it.key)) toggle(it.key, true);
        else if (it.expandable) focus(items[i + 1]?.key);
        break;
      case "ArrowRight":
        if (it.expandable && expanded.has(it.key)) toggle(it.key, false);
        else focus(it.parentKey);
        break;
      case "Enter":
      case " ":
        if (it.unit) setSelected(it.unit);
        break;
      default:
        return;
    }
    e.preventDefault();
  }

  return (
    <>
      <div className="tree" role="tree" aria-label="درخت سازمانی" data-testid="org-tree">
        {items.map((it, i) => (
          <div
            key={it.key}
            ref={(el) => {
              if (el) refs.current.set(it.key, el);
              else refs.current.delete(it.key);
            }}
            role="treeitem"
            aria-level={it.level}
            aria-expanded={it.expandable ? expanded.has(it.key) : undefined}
            aria-selected={selected?.unit_id === it.unit?.unit_id && it.kind === "unit"}
            tabIndex={it.key === active ? 0 : -1}
            className={`tree__item tree__item--${it.kind}`}
            style={{ paddingInlineStart: `calc(${String(it.level - 1)} * var(--space-5))` }}
            onKeyDown={(e) => { onKey(e, i); }}
            onFocus={() => { setFocusKey(it.key); }}
            onClick={() => {
              setFocusKey(it.key);
              if (it.expandable) toggle(it.key);
              if (it.unit) setSelected(it.unit);
            }}
            data-testid={`tree-${it.kind}`}
          >
            <span className="tree__twisty" aria-hidden="true">{it.expandable ? (expanded.has(it.key) ? "▾" : "◂") : "•"}</span>
            <span className="tree__label">{it.label}</span>
            <span className="tree__detail">{it.detail}</span>
          </div>
        ))}
      </div>
      <p className="field__hint">صفحه‌کلید: بالا/پایین جابه‌جایی، چپ باز کردن، راست بستن، Enter انتخاب واحد.</p>
      {selected ? <UnitPanel unit={selected} canManage={canManage} onClose={() => { setSelected(null); }} /> : null}
    </>
  );
}

function UnitPanel({ unit, canManage, onClose }: { unit: OrgUnit; canManage: boolean; onClose: () => void }) {
  const action = useAction();
  const [op, setOp] = useState<"rename" | "deactivate" | null>(null);
  const [name, setName] = useState(unit.name_fa);
  return (
    <section className="detail" aria-labelledby="unit-title" data-testid="unit-panel">
      <div className="panel__head">
        <h3 id="unit-title">{unit.name_fa}</h3>
        <button type="button" className="btn btn--secondary" onClick={onClose}>بستن</button>
      </div>
      <dl className="meta">
        <div><dt>کد</dt><dd><code dir="ltr">{unit.code}</code></dd></div>
        <div><dt>نوع</dt><dd>{UNIT_TYPES[unit.unit_type] ?? unit.unit_type}</dd></div>
        <div><dt>وضعیت</dt><dd><StatusChip tone={unit.status === "ACTIVE" ? "success" : "neutral"} label={unit.status === "ACTIVE" ? "فعال" : "غیرفعال"} /></dd></div>
        <div><dt>از</dt><dd>{formatJalaliDateTime(unit.valid_from)}</dd></div>
      </dl>
      {canManage && unit.status === "ACTIVE" ? (
        <div className="actions">
          <button type="button" className="btn btn--secondary" onClick={() => { action.reset(); setOp("rename"); }} data-testid="unit-rename">تغییر نام</button>
          <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setOp("deactivate"); }} data-testid="unit-deactivate">غیرفعال کردن</button>
        </div>
      ) : null}
      {op === "rename" ? (
        <ReasonDialog
          title="تغییر نام واحد"
          description={<Field label="نام تازه">{(id) => <input id={id} className="input" value={name} maxLength={200} onChange={(e) => { setName(e.target.value); }} data-testid="unit-new-name" />}</Field>}
          submitLabel="ثبت نام تازه"
          action={action}
          onClose={() => { setOp(null); }}
          onSubmit={async (reason) =>
            (await action.run((key) => write(`/org/units/${unit.unit_id}`, orgGuards.unit, { name_fa: name.trim(), reason }, key, unit.row_version, "PATCH"), [QK.org])) !== undefined
          }
        />
      ) : null}
      {op === "deactivate" ? (
        <ReasonDialog
          title="غیرفعال کردن واحد"
          description="از همین لحظه اثر دارد؛ تاریخچه حفظ می‌شود."
          submitLabel="غیرفعال کن"
          danger
          action={action}
          onClose={() => { setOp(null); }}
          onSubmit={async (reason) =>
            (await action.run((key) => write(`/org/units/${unit.unit_id}/deactivate`, orgGuards.unit, { reason }, key, unit.row_version), [QK.org])) !== undefined
          }
        />
      ) : null}
    </section>
  );
}

function FormDialog({ title, testId, action, onClose, onSubmit, children, submitLabel }: { title: string; testId: string; action: ReturnType<typeof useAction>; onClose: () => void; onSubmit: () => void; children: React.ReactNode; submitLabel: string }) {
  return (
    <Dialog title={title} onClose={onClose} testId={testId}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
        {children}
        <ActionError error={action.error} />
        <div className="form__actions">
          <button type="submit" className="btn btn--primary" disabled={action.pending} data-testid={`${testId}-submit`}>{action.pending ? "در حال ثبت…" : submitLabel}</button>
          <button type="button" className="btn btn--secondary" onClick={onClose}>انصراف</button>
        </div>
      </form>
    </Dialog>
  );
}

function ReasonField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <Field label="دلیل (در ممیزی ثبت می‌شود)">{(id) => <textarea id={id} className="input" rows={2} required minLength={3} maxLength={500} value={value} onChange={(e) => { onChange(e.target.value); }} data-testid="org-reason" />}</Field>;
}

function UnitDialog({ onClose }: { onClose: () => void }) {
  const action = useAction();
  const units = useUnitOptions(true);
  const [f, setF] = useState({ code: "", name_fa: "", unit_type: "COMPANY", parent: "", reason: "" });
  return (
    <FormDialog title="واحد تازه" testId="unit-dialog" submitLabel="ساخت واحد" action={action} onClose={onClose}
      onSubmit={() => {
        void action.run((key) => write("/org/units", orgGuards.unit, { code: f.code.trim(), name_fa: f.name_fa.trim(), unit_type: f.unit_type, parent_unit_id: f.parent || null, reason: f.reason.trim() }, key), [QK.org]).then((r) => { if (r) onClose(); });
      }}>
      <Field label="کد (کلید سیستمی لاتین)">{(id) => <input id={id} className="input" dir="ltr" required value={f.code} onChange={(e) => { setF({ ...f, code: e.target.value }); }} data-testid="unit-code" />}</Field>
      <Field label="نام واحد">{(id) => <input id={id} className="input" required maxLength={200} value={f.name_fa} onChange={(e) => { setF({ ...f, name_fa: e.target.value }); }} data-testid="unit-name" />}</Field>
      <Field label="سطح واحد" hint="سطوح مصوب DEC-048؛ حداکثر ۶ سطح.">
        {(id, hintId) => (
          <select id={id} aria-describedby={hintId} className="input" value={f.unit_type} onChange={(e) => { setF({ ...f, unit_type: e.target.value }); }} data-testid="unit-type">
            {Object.entries(UNIT_TYPES).map(([k, v]) => <option key={k} value={k}>{v} ({k})</option>)}
          </select>
        )}
      </Field>
      <Field label="واحد بالادست">
        {(id) => (
          <select id={id} className="input" value={f.parent} onChange={(e) => { setF({ ...f, parent: e.target.value }); }} data-testid="unit-parent">
            <option value="">— ریشه (بدون بالادست) —</option>
            {(units.data?.items ?? []).filter((u) => u.status === "ACTIVE").map((u) => <option key={u.unit_id} value={u.unit_id}>{u.name_fa} ({u.code})</option>)}
          </select>
        )}
      </Field>
      <p className="field__hint">شروع اعتبار: همین لحظه (تاریخ گذشته پذیرفته نمی‌شود).</p>
      <ReasonField value={f.reason} onChange={(v) => { setF({ ...f, reason: v }); }} />
    </FormDialog>
  );
}

function usePositions() {
  return useQuery({
    queryKey: [...QK.org, "positions", "options"],
    queryFn: async ({ signal }) => (await read("/org/positions", orgGuards.positionPage, { page_size: 100 }, signal)).data,
  });
}

function PositionDialog({ onClose }: { onClose: () => void }) {
  const action = useAction();
  const units = useUnitOptions(true);
  const positions = usePositions();
  const [f, setF] = useState({ unit_id: "", code: "", title_fa: "", reports_to: "", head: false, capacity: "1", reason: "" });
  return (
    <FormDialog title="سمت تازه" testId="position-dialog" submitLabel="ساخت سمت" action={action} onClose={onClose}
      onSubmit={() => {
        const body: Record<string, unknown> = { unit_id: f.unit_id, code: f.code.trim(), title_fa: f.title_fa.trim(), is_unit_head: f.head, reason: f.reason.trim() };
        if (f.reports_to) body.reports_to_position_id = f.reports_to;
        if (!f.head) body.primary_capacity = Number(f.capacity);
        void action.run((key) => write("/org/positions", orgGuards.position, body, key), [QK.org]).then((r) => { if (r) onClose(); });
      }}>
      <Field label="واحد">
        {(id) => (
          <select id={id} className="input" required value={f.unit_id} onChange={(e) => { setF({ ...f, unit_id: e.target.value }); }} data-testid="position-unit">
            <option value="">انتخاب کنید</option>
            {(units.data?.items ?? []).filter((u) => u.status === "ACTIVE").map((u) => <option key={u.unit_id} value={u.unit_id}>{u.name_fa} ({u.code})</option>)}
          </select>
        )}
      </Field>
      <Field label="کد سمت (کلید سیستمی لاتین)">{(id) => <input id={id} className="input" dir="ltr" required value={f.code} onChange={(e) => { setF({ ...f, code: e.target.value }); }} data-testid="position-code" />}</Field>
      <Field label="عنوان سمت">{(id) => <input id={id} className="input" required maxLength={200} value={f.title_fa} onChange={(e) => { setF({ ...f, title_fa: e.target.value }); }} data-testid="position-title" />}</Field>
      <Field label="گزارش به (سمت بالادست)">
        {(id) => (
          <select id={id} className="input" value={f.reports_to} onChange={(e) => { setF({ ...f, reports_to: e.target.value }); }}>
            <option value="">— ندارد —</option>
            {(positions.data?.items ?? []).map((p) => <option key={p.position_id} value={p.position_id}>{p.title_fa} ({p.code})</option>)}
          </select>
        )}
      </Field>
      <label className="check">
        <input type="checkbox" checked={f.head} onChange={(e) => { setF({ ...f, head: e.target.checked, capacity: "1" }); }} data-testid="position-head" />
        رئیس واحد (همیشه دقیقاً یک متصدی اصلی؛ جانشین با «سرپرست موقت» ثبت می‌شود)
      </label>
      <Field label="ظرفیت متصدی اصلی" hint={f.head ? "برای رئیس واحد ثابت ۱ است." : "پیش‌فرض ۱ (پاسخ کارفرما Q-0106)."}>
        {(id, hintId) => <input id={id} aria-describedby={hintId} className="input" type="number" min={1} max={99} disabled={f.head} value={f.head ? "1" : f.capacity} onChange={(e) => { setF({ ...f, capacity: e.target.value }); }} data-testid="position-capacity" />}
      </Field>
      <ReasonField value={f.reason} onChange={(v) => { setF({ ...f, reason: v }); }} />
    </FormDialog>
  );
}

function AssignDialog({ onClose }: { onClose: () => void }) {
  const { can } = useAuth();
  const [openedAt] = useState(() => Date.now());
  const action = useAction();
  const positions = usePositions();
  const users = useUserOptions(can("platform.identity.user.read"));
  const [f, setF] = useState({ position_id: "", user_id: "", kind: "PRIMARY", valid_to: "", reason: "" });
  return (
    <FormDialog title="انتصاب فرد به سمت" testId="assign-dialog" submitLabel="ثبت انتصاب" action={action} onClose={onClose}
      onSubmit={() => {
        const body: Record<string, unknown> = { position_id: f.position_id, user_id: f.user_id, kind: f.kind, valid_from: nowUtc(), reason: f.reason.trim() };
        const to = localInputToUtc(f.valid_to);
        if (to) body.valid_to = to;
        void action.run((key) => write("/org/position-assignments", orgGuards.pa, body, key), [QK.org]).then((r) => { if (r) onClose(); });
      }}>
      <Field label="سمت">
        {(id) => (
          <select id={id} className="input" required value={f.position_id} onChange={(e) => { setF({ ...f, position_id: e.target.value }); }} data-testid="assign-position">
            <option value="">انتخاب کنید</option>
            {(positions.data?.items ?? []).map((p) => <option key={p.position_id} value={p.position_id}>{p.title_fa} ({p.code}){p.is_unit_head ? " — رئیس واحد" : ""}</option>)}
          </select>
        )}
      </Field>
      <Field label="فرد">
        {(id) => (
          <select id={id} className="input" required value={f.user_id} onChange={(e) => { setF({ ...f, user_id: e.target.value }); }} data-testid="assign-user">
            <option value="">انتخاب کنید</option>
            {(users.data?.items ?? []).map((u) => <option key={u.user_id} value={u.user_id}>{u.display_name} ({u.username})</option>)}
          </select>
        )}
      </Field>
      <Field label="نوع">
        {(id) => (
          <select id={id} className="input" value={f.kind} onChange={(e) => { setF({ ...f, kind: e.target.value }); }} data-testid="assign-kind">
            <option value="PRIMARY">متصدی اصلی</option>
            <option value="ACTING">سرپرست موقت (با تاریخ پایان)</option>
          </select>
        )}
      </Field>
      <p className="field__hint">شروع: همین لحظه ({formatJalaliDateTime(openedAt)})؛ تاریخ گذشته پذیرفته نمی‌شود.</p>
      <Field label={f.kind === "ACTING" ? "پایان (برای سرپرست موقت لازم است)" : "پایان (اختیاری)"}>
        {(id) => <input id={id} className="input" type="datetime-local" required={f.kind === "ACTING"} value={f.valid_to} onChange={(e) => { setF({ ...f, valid_to: e.target.value }); }} />}
      </Field>
      {f.valid_to && localInputToUtc(f.valid_to) ? <p className="field__hint">به تقویم شمسی: {formatJalaliDateTime(localInputToUtc(f.valid_to) ?? "")}</p> : null}
      <ReasonField value={f.reason} onChange={(v) => { setF({ ...f, reason: v }); }} />
      <p className="field__hint">ظرفیت و قاعده «یک متصدی اصلی برای رئیس واحد» را سرور بررسی می‌کند ({toFaDigits(1)} نفر).</p>
    </FormDialog>
  );
}
