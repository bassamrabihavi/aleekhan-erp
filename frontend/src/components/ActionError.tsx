// Inline result of a failed action: Persian message, machine code, request id; RULE_NOT_APPROVED names the
// decision (MOCK_UI_BINDING §2 rule 3) and field errors list the field paths.
import { ApiError } from "../api/client";
import { toFaDigits } from "../lib/format";
import { FIELD_ERROR_LABELS } from "../lib/labels";

export function ActionError({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error instanceof ApiError ? error : new ApiError({ kind: "network", status: null });
  if (e.code === "RULE_NOT_APPROVED") {
    return (
      <div className="notice notice--blocked" role="alert" data-testid="rule-blocked">
        <strong>این قاعده هنوز تصویب نشده است{e.decisionId ? ` (${e.decisionId})` : ""}.</strong>{" "}
        <span>اقدام تا تصمیم کارفرما مسدود است؛ سامانه آن را حدس نمی‌زند.</span>
        <RequestRef e={e} />
      </div>
    );
  }
  return (
    <div className="notice notice--error" role="alert" data-testid="action-error">
      <strong>{e.messageFa}</strong>
      {e.fieldErrors.length > 0 ? (
        <ul className="notice__list">
          {e.fieldErrors.map((f) => (
            <li key={`${f.field}:${f.code}`}>
              <code dir="ltr">{f.field || "—"}</code>: {FIELD_ERROR_LABELS[f.code] ?? <code dir="ltr">{f.code}</code>}
            </li>
          ))}
        </ul>
      ) : null}
      <RequestRef e={e} />
    </div>
  );
}

function RequestRef({ e }: { e: ApiError }) {
  return (
    <span className="notice__meta">
      کد خطا <code dir="ltr" data-testid="action-error-code">{e.code ?? (e.kind === "network" ? "NETWORK" : "CONTRACT")}</code>
      {e.status !== null ? <> · HTTP {toFaDigits(e.status)}</> : null}
      {e.requestId ? (
        <>
          {" "}
          · شناسه درخواست <code dir="ltr">{e.requestId}</code>
        </>
      ) : null}
    </span>
  );
}
