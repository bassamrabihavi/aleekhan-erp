// Inline result of a failed action: Persian message, machine code, request id; RULE_NOT_APPROVED names the
// decision (MOCK_UI_BINDING §2 rule 3) and field errors list the field paths. 02.5: 412 VERSION_CONFLICT is a
// clear "data changed - reload" state (the edit is NOT retried with the newer version automatically).
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { toFaDigits } from "../lib/format";
import { FIELD_ERROR_LABELS } from "../lib/labels";
import { REASON_LABELS } from "../lib/labels02";

export function ActionError({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error instanceof ApiError ? error : new ApiError({ kind: "network", status: null });
  if (e.code === "RULE_NOT_APPROVED") {
    return (
      <div className="notice notice--blocked" role="alert" data-testid="rule-blocked">
        <strong>این قاعده هنوز تصویب نشده است{e.decisionId ? ` (${e.decisionId})` : ""}.</strong>{" "}
        <span>اقدام تا تصمیم کارفرما مسدود است؛ سامانه آن را حدس نمی‌زند.</span>
        <FieldList e={e} />
        <RequestRef e={e} />
      </div>
    );
  }
  if (e.code === "VERSION_CONFLICT") return <VersionConflict e={e} />;
  return (
    <div className="notice notice--error" role="alert" data-testid="action-error">
      <strong>{e.messageFa}</strong>
      <FieldList e={e} />
      <RequestRef e={e} />
    </div>
  );
}

function VersionConflict({ e }: { e: ApiError }) {
  const qc = useQueryClient();
  return (
    <div className="notice notice--warning" role="alert" data-testid="version-conflict">
      <strong>این داده در این فاصله تغییر کرده است.</strong>{" "}
      <span>کس دیگری آن را ویرایش کرده است؛ تغییر شما ثبت نشد. داده تازه را بارگذاری کنید و دوباره بررسی کنید.</span>
      <div className="actions">
        <button
          type="button"
          className="btn btn--secondary btn--small"
          onClick={() => void qc.invalidateQueries()}
          data-testid="version-conflict-reload"
        >
          بارگذاری دوباره داده
        </button>
      </div>
      <RequestRef e={e} />
    </div>
  );
}

function FieldList({ e }: { e: ApiError }) {
  if (e.fieldErrors.length === 0) return null;
  return (
    <ul className="notice__list">
      {e.fieldErrors.map((f) => (
        <li key={`${f.field}:${f.code}`}>
          <code dir="ltr">{f.field || "—"}</code>:{" "}
          {FIELD_ERROR_LABELS[f.code] ?? REASON_LABELS[f.code] ?? <code dir="ltr">{f.code}</code>}
        </li>
      ))}
    </ul>
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
