// Login ceremony screens (MOCK_UI_BINDING §6.0): password -> MFA code -> forced password change (DEC-051) ->
// MFA enrolment (DEC-050, TOTP + 10 one-time recovery codes shown once). The 401 text of a failed login is
// the server's single generic message (no "user not found").
import { useEffect, useState, type ReactNode } from "react";

import { auth } from "../api/phase01";
import { ActionError } from "../components/ActionError";
import { ErrorState } from "../components/States";
import { toFaDigits } from "../lib/format";
import { useAuth } from "./context";

function Card({ title, lead, children, testId }: { title: string; lead?: ReactNode; children: ReactNode; testId: string }) {
  return (
    <section className="auth-card" aria-labelledby={`${testId}-title`} data-testid={testId}>
      <h1 id={`${testId}-title`}>{title}</h1>
      {lead ? <p className="lead">{lead}</p> : null}
      {children}
    </section>
  );
}

function useSubmit(): { pending: boolean; error: unknown; submit: (fn: () => Promise<unknown>) => Promise<boolean> } {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return {
    pending,
    error,
    submit: async (fn) => {
      setPending(true);
      setError(null);
      try {
        await fn();
        return true;
      } catch (e) {
        setError(e);
        return false;
      } finally {
        setPending(false);
      }
    },
  };
}

export function LoginScreen() {
  const { notice, refresh } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const s = useSubmit();

  useEffect(() => {
    void auth.context().catch(() => undefined); // sets the csrftoken cookie (login CSRF)
  }, []);

  return (
    <Card
      title="ورود به سامانه"
      lead="حساب کاربری را فقط مالک سامانه داخل همین سامانه می‌سازد (بدون Active Directory)."
      testId="login"
    >
      {notice ? (
        <p className="notice notice--info" role="status" data-testid="login-notice">
          {notice}
        </p>
      ) : null}
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          void s.submit(async () => {
            if (!document.cookie.includes("csrftoken=")) await auth.context();
            await auth.login(username.trim(), password);
            setPassword("");
            await refresh();
          });
        }}
      >
        <div className="field">
          <label className="field__label" htmlFor="login-username">
            نام کاربری
          </label>
          <input
            id="login-username"
            className="input"
            dir="ltr"
            autoComplete="username"
            required
            value={username}
            onChange={(e) => {
              setUsername(e.target.value);
            }}
            data-testid="login-username"
          />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="login-password">
            رمز عبور
          </label>
          <input
            id="login-password"
            className="input"
            dir="ltr"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
            }}
            data-testid="login-password"
          />
        </div>
        <ActionError error={s.error} />
        <button type="submit" className="btn btn--primary btn--block" disabled={s.pending} data-testid="login-submit">
          {s.pending ? "در حال ورود…" : "ورود"}
        </button>
      </form>
      <p className="auth-card__foot">
        <a href="#/status">وضعیت سامانه (بدون نیاز به ورود)</a>
      </p>
    </Card>
  );
}

function CancelLogin() {
  const { logout } = useAuth();
  return (
    <button type="button" className="btn btn--secondary btn--block" onClick={() => void logout()} data-testid="cancel-login">
      انصراف و خروج
    </button>
  );
}

export function MfaScreen() {
  const { refresh } = useAuth();
  const [code, setCode] = useState("");
  const s = useSubmit();
  return (
    <Card
      title="کد ورود دومرحله‌ای"
      lead="کد شش‌رقمی برنامه احراز هویت روی گوشی (یا یکی از کدهای بازیابی) را وارد کنید."
      testId="mfa"
    >
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          void s.submit(async () => {
            await auth.verifyMfa(code.trim());
            await refresh();
          });
        }}
      >
        <div className="field">
          <label className="field__label" htmlFor="mfa-code">
            کد تأیید
          </label>
          <input
            id="mfa-code"
            className="input"
            dir="ltr"
            autoComplete="one-time-code"
            required
            minLength={6}
            maxLength={32}
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
            }}
            data-testid="mfa-code"
          />
        </div>
        <ActionError error={s.error} />
        <button type="submit" className="btn btn--primary btn--block" disabled={s.pending} data-testid="mfa-submit">
          {s.pending ? "در حال بررسی…" : "تأیید"}
        </button>
        <CancelLogin />
      </form>
    </Card>
  );
}

export function PasswordChangeScreen() {
  const { refresh } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const s = useSubmit();
  const mismatch = repeat.length > 0 && next !== repeat;
  return (
    <Card
      title="تعویض رمز عبور"
      lead="پیش از ادامه باید رمز عبور را عوض کنید (رمز یک‌بارمصرف یا رمز منقضی)."
      testId="password-change"
    >
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          if (mismatch) return;
          void s.submit(async () => {
            await auth.changePassword(current, next);
            setCurrent("");
            setNext("");
            setRepeat("");
            await refresh();
          });
        }}
      >
        <div className="field">
          <label className="field__label" htmlFor="pw-current">
            رمز فعلی (یا رمز یک‌بارمصرف)
          </label>
          <input id="pw-current" className="input" dir="ltr" type="password" autoComplete="current-password" required value={current} onChange={(e) => { setCurrent(e.target.value); }} data-testid="pw-current" />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="pw-new">
            رمز تازه
          </label>
          <input id="pw-new" className="input" dir="ltr" type="password" autoComplete="new-password" required minLength={8} aria-describedby="pw-rules" value={next} onChange={(e) => { setNext(e.target.value); }} data-testid="pw-new" />
          <p className="field__hint" id="pw-rules">
            طبق سیاست مصوب (DEC-051): حداقل {toFaDigits(8)} نویسه، شامل حرف بزرگ لاتین، عدد و نماد؛ تکرار {toFaDigits(5)} رمز
            آخر پذیرفته نمی‌شود. سرور قوانین را بررسی می‌کند.
          </p>
        </div>
        <div className="field">
          <label className="field__label" htmlFor="pw-repeat">
            تکرار رمز تازه
          </label>
          <input id="pw-repeat" className="input" dir="ltr" type="password" autoComplete="new-password" required value={repeat} aria-invalid={mismatch} onChange={(e) => { setRepeat(e.target.value); }} data-testid="pw-repeat" />
          {mismatch ? <p className="field__error" role="alert">تکرار رمز با رمز تازه یکسان نیست.</p> : null}
        </div>
        <ActionError error={s.error} />
        <button type="submit" className="btn btn--primary btn--block" disabled={s.pending || mismatch} data-testid="pw-submit">
          {s.pending ? "در حال ثبت…" : "ثبت رمز تازه"}
        </button>
        <CancelLogin />
      </form>
    </Card>
  );
}

function secretOf(uri: string): string {
  try {
    return new URL(uri).searchParams.get("secret") ?? "";
  } catch {
    return "";
  }
}

export function MfaEnrolmentScreen() {
  const { refresh } = useAuth();
  const [uri, setUri] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  const start = useSubmit();
  const confirm = useSubmit();

  if (codes) {
    return (
      <Card title="کدهای بازیابی" lead="این ده کد فقط همین یک بار نمایش داده می‌شوند. آن‌ها را در جای امن نگه دارید؛ هر کد یک بار کار می‌کند." testId="recovery-codes">
        <ol className="codes" dir="ltr" data-testid="recovery-code-list">
          {codes.map((c) => (
            <li key={c}>
              <code>{c}</code>
            </li>
          ))}
        </ol>
        <button type="button" className="btn btn--primary btn--block" onClick={() => void refresh()} data-testid="recovery-done">
          کدها را ذخیره کردم؛ ادامه
        </button>
      </Card>
    );
  }

  const secret = uri ? secretOf(uri) : "";
  return (
    <Card
      title="فعال‌سازی ورود دومرحله‌ای"
      lead="نقش شما ورود دومرحله‌ای لازم دارد (DEC-050: برنامه کد روی گوشی، مثل Google/Microsoft Authenticator)."
      testId="mfa-enrolment"
    >
      {!uri ? (
        <>
          <ActionError error={start.error} />
          <button
            type="button"
            className="btn btn--primary btn--block"
            disabled={start.pending}
            onClick={() =>
              void start.submit(async () => {
                setUri((await auth.startEnrolment()).data.provisioning_uri);
              })
            }
            data-testid="enrol-start"
          >
            {start.pending ? "در حال آماده‌سازی…" : "شروع فعال‌سازی"}
          </button>
        </>
      ) : (
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault();
            void confirm.submit(async () => {
              setCodes((await auth.confirmEnrolment(code.trim())).data.recovery_codes ?? []);
            });
          }}
        >
          <p>
            در برنامه احراز هویت «افزودن حساب با کلید» را بزنید و این کلید را وارد کنید (نوع: مبتنی بر زمان):
          </p>
          <p className="secret" dir="ltr" data-testid="enrol-secret">
            {secret.replace(/(.{4})/g, "$1 ").trim()}
          </p>
          <details>
            <summary>نشانی کامل otpauth (برای کپی)</summary>
            <code dir="ltr" className="break" data-testid="enrol-uri">
              {uri}
            </code>
          </details>
          <div className="field">
            <label className="field__label" htmlFor="enrol-code">
              کد شش‌رقمی که برنامه نشان می‌دهد
            </label>
            <input id="enrol-code" className="input" dir="ltr" inputMode="numeric" autoComplete="one-time-code" required minLength={6} maxLength={6} value={code} onChange={(e) => { setCode(e.target.value); }} data-testid="enrol-code" />
          </div>
          <ActionError error={confirm.error} />
          <button type="submit" className="btn btn--primary btn--block" disabled={confirm.pending} data-testid="enrol-confirm">
            {confirm.pending ? "در حال بررسی…" : "تأیید و فعال‌سازی"}
          </button>
        </form>
      )}
      <CancelLogin />
    </Card>
  );
}

export function BootErrorScreen() {
  const { bootError, refresh } = useAuth();
  return (
    <Card title="سامانه در دسترس نیست" testId="boot-error">
      <ErrorState error={bootError} title="وضعیت جلسه دریافت نشد" onRetry={() => void refresh()} />
      <p className="auth-card__foot">
        <a href="#/status">وضعیت سامانه</a>
      </p>
    </Card>
  );
}
