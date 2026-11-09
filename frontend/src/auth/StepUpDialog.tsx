// MFA step-up (DEC-051: 15-minute window). Shown when an action answers 401 MFA_REQUIRED; the action is then
// re-sent once (with a new Idempotency-Key - the refused request had no effect).
import { useState } from "react";

import { auth } from "../api/phase01";
import { ActionError } from "../components/ActionError";
import { Dialog } from "../components/Dialog";

export function StepUpDialog({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: React.SyntheticEvent): Promise<void> {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      await auth.stepUp(code.trim());
      onDone();
    } catch (err) {
      setError(err);
      setPending(false);
    }
  }

  return (
    <Dialog title="تأیید دومرحله‌ای لازم است" onClose={onCancel} testId="step-up-dialog">
      <form onSubmit={(e) => void submit(e)} className="form">
        <p className="lead">
          این اقدام به تأیید تازه دومرحله‌ای (حداکثر ۱۵ دقیقه پیش) نیاز دارد. کد شش‌رقمی برنامه احراز هویت یا یکی از
          کدهای بازیابی را وارد کنید.
        </p>
        <label className="field">
          <span className="field__label">کد تأیید</span>
          <input
            className="input"
            dir="ltr"
            inputMode="text"
            autoComplete="one-time-code"
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
            }}
            required
            minLength={6}
            maxLength={32}
            data-testid="step-up-code"
          />
        </label>
        <ActionError error={error} />
        <div className="form__actions">
          <button type="submit" className="btn btn--primary" disabled={pending} data-testid="step-up-submit">
            {pending ? "در حال بررسی…" : "تأیید"}
          </button>
          <button type="button" className="btn btn--secondary" onClick={onCancel}>
            انصراف
          </button>
        </div>
      </form>
    </Dialog>
  );
}
