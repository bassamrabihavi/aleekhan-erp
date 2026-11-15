// Shared PHASE_02 presentation (MOCK_UI_BINDING §7.0): codes / serials / technical numbers as LTR text (never a
// number, never Persian digits, leading zeros kept), the "later phase" placeholder without numbers (DEC-027),
// the masked representative name (DEC-058), a Jalali date field that sends ISO dates, and small helpers.
import { useId, useState, type ReactNode } from "react";

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
export function LaterSection({ title, phase }: { title: string; phase: string }) {
  return (
    <section className="later" data-testid="later-section" aria-label={title}>
      <h3 className="later__title">{title}</h3>
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

export function PageHead({ page, title, lead, actions }: { page: string; title: string; lead?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page__head">
      <div>
        <p className="eyebrow">{page}</p>
        <h1>{title}</h1>
        {lead ? <p className="lead">{lead}</p> : null}
      </div>
      {actions ? <div className="actions">{actions}</div> : null}
    </div>
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
