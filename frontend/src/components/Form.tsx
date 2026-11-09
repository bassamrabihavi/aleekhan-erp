// Small form building blocks (label + control + hint), a reason dialog (every audited action needs a reason)
// and tabs with roving keyboard focus (WAI-ARIA tabs pattern).
import { useId, useRef, useState, type ReactNode } from "react";

import type { Action } from "../lib/useAction";
import { ActionError } from "./ActionError";
import { Dialog } from "./Dialog";

export function Field({ label, hint, children }: { label: string; hint?: string; children: (id: string, hintId?: string) => ReactNode }) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      {children(id, hintId)}
      {hint ? (
        <p className="field__hint" id={hintId}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

interface ReasonProps {
  title: string;
  description?: ReactNode;
  label?: string;
  submitLabel: string;
  action: Action;
  minLength?: number;
  danger?: boolean;
  onSubmit: (reason: string) => Promise<boolean>;
  onClose: () => void;
  testId?: string;
}

/** Dialog asking a mandatory reason (>= 3 characters) before an audited action. */
export function ReasonDialog({
  title,
  description,
  label = "دلیل (در ممیزی ثبت می‌شود)",
  submitLabel,
  action,
  minLength = 3,
  danger = false,
  onSubmit,
  onClose,
  testId = "reason-dialog",
}: ReasonProps) {
  const [reason, setReason] = useState("");
  return (
    <Dialog title={title} onClose={onClose} testId={testId}>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          void onSubmit(reason.trim()).then((ok) => {
            if (ok) onClose();
          });
        }}
      >
        {description ? <div className="lead">{description}</div> : null}
        <Field label={label}>
          {(id) => (
            <textarea
              id={id}
              className="input"
              rows={3}
              required
              minLength={minLength}
              maxLength={500}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
              }}
              data-testid="reason-input"
            />
          )}
        </Field>
        <ActionError error={action.error} />
        <div className="form__actions">
          <button
            type="submit"
            className={danger ? "btn btn--danger" : "btn btn--primary"}
            disabled={action.pending || reason.trim().length < minLength}
            data-testid="reason-submit"
          >
            {action.pending ? "در حال ارسال…" : submitLabel}
          </button>
          <button type="button" className="btn btn--secondary" onClick={onClose}>
            انصراف
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export interface TabDef {
  id: string;
  label: string;
}

export function Tabs({ tabs, active, onChange, label }: { tabs: TabDef[]; active: string; onChange: (id: string) => void; label: string }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  function onKey(e: React.KeyboardEvent, i: number): void {
    // RTL: ArrowLeft moves to the next tab, ArrowRight to the previous one
    const moves: Record<string, number> = { ArrowLeft: i + 1, ArrowRight: i - 1, Home: 0, End: tabs.length - 1 };
    const target = moves[e.key];
    if (target === undefined) return;
    e.preventDefault();
    const next = (target + tabs.length) % tabs.length;
    const t = tabs[next];
    if (t) {
      onChange(t.id);
      refs.current[next]?.focus();
    }
  }
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="tab"
          id={`tab-${t.id}`}
          aria-selected={t.id === active}
          aria-controls={`panel-${t.id}`}
          tabIndex={t.id === active ? 0 : -1}
          className="tab"
          onClick={() => {
            onChange(t.id);
          }}
          onKeyDown={(e) => {
            onKey(e, i);
          }}
          data-testid={`tab-${t.id}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} className="tabpanel">
      {children}
    </div>
  );
}

/** Short id for display: first 8 hex chars, full value in the title, always LTR. */
export function ShortId({ id }: { id: string | null | undefined }) {
  if (!id) return <span>—</span>;
  return (
    <code dir="ltr" className="code-id" title={id}>
      {id.slice(0, 8)}
    </code>
  );
}
