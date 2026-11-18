// Shared PHASE_02 presentation (MOCK_UI_BINDING §7.0): codes / serials / technical numbers as LTR text (never a
// number, never Persian digits, leading zeros kept), the "later phase" placeholder without numbers (DEC-027),
// the masked representative name (DEC-058), a Jalali date field that sends ISO dates, and small helpers.
import { useId, useState, type ReactNode } from "react";

import { Dialog } from "./Dialog";
import { Icon } from "./Icon";

import { REDACTED, type Customer } from "../api/phase02";
import { isoToJalaliInput, jalaliInputToIso } from "../lib/jalali";
import { SECTION_LABEL } from "../lib/labels02";

/** 14-digit product code: exact characters, LTR, monospace; optional copy of the exact 14 characters. */
export function Code14({ code, copy = false, testId }: { code: string | null | undefined; copy?: boolean; testId?: string }) {
  const [copied, setCopied] = useState(false);
  if (!code) return <span>—</span>;
  return (
    <span className="code14-wrap">
      <bdi dir="ltr" className="code14" data-testid={testId}>
        {code}
      </bdi>
      {copy ? (
        <button
          type="button"
          className="btn btn--link btn--small"
          onClick={() => {
            if ("clipboard" in navigator) {
              void navigator.clipboard.writeText(code).then(() => {
                setCopied(true);
              });
            }
          }}
          aria-label={`رونوشت کد ${code}`}
        >
          {copied ? "رونوشت شد" : "رونوشت"}
        </button>
      ) : null}
    </span>
  );
}

/** Serial number / SO- / CU- / CR- numbers: shown exactly as returned, LTR inside RTL text. */
export function Num({ value, testId }: { value: string | null | undefined; testId?: string }) {
  if (!value) return <span>—</span>;
  return (
    <bdi dir="ltr" className="code14" data-testid={testId}>
      {value}
    </bdi>
  );
}

export const LATER_TEXT = "در دست ساخت — به داده واقعی متصل نیست";

/** A section owned by a later phase: title + placeholder, never a number (DEC-027 P-A, rule 2). */
/** `fid` = DEC-061 fidelity region id (e2e/fidelity), a measurement marker only. */
export function LaterSection({ title, phase, fid, className, detail }: { title: string; phase: string; fid?: string; className?: string; detail?: string }) {
  return (
    <section className={className ? `later ${className}` : "later"} data-testid="later-section" aria-label={title} data-fid={fid}>
      <h3 className="later__title">{title}</h3>
      {detail ? <p className="later__detail">{detail}</p> : null}
      <p className="later__text">{LATER_TEXT}</p>
      <p className="later__meta">
        فاز مالک: <bdi dir="ltr">{phase}</bdi>
      </p>
    </section>
  );
}

/** The server's `unavailable_sections` as later-phase placeholders. */
export function LaterSections({ sections, only }: { sections: { section: string; phase: string }[]; only?: readonly string[] }) {
  const shown = only ? sections.filter((s) => only.includes(s.section)) : sections;
  return (
    <div className="later-grid">
      {shown.map((s) => (
        <LaterSection key={s.section} title={SECTION_LABEL[s.section] ?? s.section} phase={s.phase} />
      ))}
    </div>
  );
}

/** Representative name (DEC-058 PII): masked for management_viewer; never logged. */
export function Representative({ value }: { value: string | null }) {
  if (value === null) return <span>—</span>;
  if (value === REDACTED)
    return (
      <span className="chip chip--neutral chip--inline" data-testid="rep-masked">
        پنهان (داده شخصی)
      </span>
    );
  return <span data-testid="rep-value">{value}</span>;
}

/** Jalali date text field ("1405/09/18", Persian or Latin digits) bound to an ISO date. */
export function JalaliDateField({
  label,
  value,
  onChange,
  required = false,
  testId,
  hint,
}: {
  label: string;
  value: string | null;
  onChange: (iso: string | null) => void;
  required?: boolean;
  testId?: string;
  hint?: string;
}) {
  const id = useId();
  const [text, setText] = useState(() => isoToJalaliInput(value));
  const iso = text ? jalaliInputToIso(text) : null;
  const invalid = text !== "" && iso === null;
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
        {required ? " *" : ""}
      </label>
      <input
        id={id}
        className="input"
        dir="ltr"
        inputMode="numeric"
        placeholder="____/__/__"
        value={text}
        required={required}
        aria-invalid={invalid}
        aria-describedby={`${id}-hint`}
        onChange={(e) => {
          const t = e.target.value;
          setText(t);
          onChange(t ? jalaliInputToIso(t) : null);
        }}
        data-testid={testId}
      />
      <p className="field__hint" id={`${id}-hint`}>
        {invalid ? <span className="field__error">تاریخ شمسی معتبر نیست (سال/ماه/روز).</span> : (hint ?? "تاریخ شمسی: سال/ماه/روز")}
      </p>
    </div>
  );
}

/** Page intro (REV-0295, catalogue «pageintro»): owner / page chip, title, one-line subtitle, header actions. */
export function PageHead({ page, title, lead, actions, compact = false }: { page: string; title: string; lead?: ReactNode; actions?: ReactNode; compact?: boolean }) {
  if (compact) {
    // page 4 heading (catalogue «section.heading»): title, then the page chip and the subtitle on one line
    return (
      <div className="page__head page__head--compact">
        <div className="page__intro" data-fid="page-header">
          <h1>{title}</h1>
          <p className="lead">
            <span className="eyebrow">{page}</span> {lead}
          </p>
        </div>
        {actions ? <div className="actions page__actions" data-fid="header-actions">{actions}</div> : null}
      </div>
    );
  }
  return (
    <div className="page__head">
      <div className="page__intro" data-fid="page-header">
        <p className="eyebrow">{page}</p>
        <h1>{title}</h1>
        {lead ? <p className="lead">{lead}</p> : null}
      </div>
      {actions ? <div className="actions page__actions" data-fid="header-actions">{actions}</div> : null}
    </div>
  );
}

/** A visibly disabled control with its honest reason (tooltip + accessible description), never a dead button. */
export function DisabledAction({ label, reason, primary = false, icon, testId }: { label: string; reason: string; primary?: boolean; icon?: "download" | "clear" | "plus"; testId?: string }) {
  const id = useId();
  return (
    <>
      <button type="button" className={primary ? "btn btn--primary btn--compact" : "btn btn--outline btn--compact"} disabled title={reason} aria-describedby={id} data-testid={testId}>
        {icon ? <Icon name={icon} size={16} /> : null}
        {label}
      </button>
      <span id={id} className="sr-only">
        {reason}
      </span>
    </>
  );
}

/** «راهنمای صفحه» and «مالکیت و منبع داده»: real dialogs with the page's help text and its owner / sources. */
export function PageInfoButtons({ help, owner, sources }: { help: ReactNode; owner: string; sources: { label: string; detail: string }[] }) {
  const [open, setOpen] = useState<"help" | "source" | null>(null);
  return (
    <>
      <button type="button" className="btn btn--outline btn--compact" onClick={() => { setOpen("help"); }} data-testid="page-help">
        راهنمای صفحه
      </button>
      <button type="button" className="btn btn--outline btn--compact" onClick={() => { setOpen("source"); }} data-testid="page-sources">
        مالکیت و منبع داده
      </button>
      {open === "help" ? (
        <Dialog title="راهنمای صفحه" onClose={() => { setOpen(null); }} testId="page-help-dialog">
          <div className="lead">{help}</div>
          <div className="form__actions">
            <button type="button" className="btn btn--secondary" onClick={() => { setOpen(null); }}>بستن</button>
          </div>
        </Dialog>
      ) : null}
      {open === "source" ? (
        <Dialog title="مالکیت و منبع داده" onClose={() => { setOpen(null); }} testId="page-sources-dialog">
          <p className="lead">مالک صفحه: {owner}</p>
          <dl className="meta meta--rows">
            {sources.map((x) => (
              <div key={x.label}>
                <dt>{x.label}</dt>
                <dd>{x.detail}</dd>
              </div>
            ))}
          </dl>
          <div className="form__actions">
            <button type="button" className="btn btn--secondary" onClick={() => { setOpen(null); }}>بستن</button>
          </div>
        </Dialog>
      ) : null}
    </>
  );
}

/** KPI card (catalogue «.kpi»): title, value, one-line note. The value is real data or an honest state. */
export function Kpi({ label, value, note, tone, testId }: { label: string; value: ReactNode; note?: ReactNode; tone?: "critical" | "good" | "later" | undefined; testId?: string }) {
  return (
    <li className={tone ? `kpi kpi--${tone}` : "kpi"} data-fid-item data-testid={testId}>
      <span className="kpi__label">{label}</span>
      <strong className="kpi__value">{value}</strong>
      {note ? <small className="kpi__note">{note}</small> : null}
    </li>
  );
}

/** KPI whose data belongs to a later phase: title + the placeholder in the value's place, never a number. */
export function LaterKpi({ label, phase }: { label: string; phase: string }) {
  return (
    <li className="kpi kpi--later" data-fid-item data-testid="later-kpi">
      <span className="kpi__label">{label}</span>
      <strong className="kpi__value kpi__value--later">{LATER_TEXT}</strong>
      <small className="kpi__note">
        فاز مالک: <bdi dir="ltr">{phase}</bdi>
      </small>
    </li>
  );
}

export function CustomerName({ id, names }: { id: string; names: Map<string, Customer> }) {
  const c = names.get(id);
  if (!c) return <code dir="ltr" className="code-id" title={id}>{id.slice(0, 8)}</code>;
  return (
    <span>
      {c.display_name_fa} <Num value={c.customer_no} />
    </span>
  );
}
