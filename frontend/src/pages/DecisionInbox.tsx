// Page 39 approval inbox, PHASE_02 part (employer decision 2026-11-15): the order confirmations, change-request
// decisions, planning decisions and code-rule approvals waiting for ME (GET /me/decision-inbox, contract
// 0.8.3-draft). The server lists only kinds I may decide and never my own requests; the decision itself is made
// on the linked page (fresh MFA, maker-checker and version re-checked there).
import { useQuery } from "@tanstack/react-query";

import { g, get, K2, type DecisionItem } from "../api/phase02";
import { DataView } from "../components/DataView";
import { Requester } from "../components/Form";
import { Num } from "../components/Phase02";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import { DECISION_KIND } from "../lib/labels02";

function href(it: DecisionItem): string {
  if (it.entity_type === "customer_order") return `#/orders/${it.entity_id}`;
  if (it.entity_type === "change_request") return `#/changes/${it.entity_id}`;
  return `#/code-rules/${it.entity_id}`;
}

export function DecisionsTab() {
  const q = useQuery({
    queryKey: [...K2.inbox],
    queryFn: async ({ signal }) => (await get("/me/decision-inbox", g.inbox, undefined, signal)).data,
  });
  return (
    <section className="panel panel--wide" aria-labelledby="decisions-title">
      <h2 id="decisions-title">تصمیم‌های سفارش، تغییر و کد</h2>
      <p className="field__hint">فقط مواردی که شما اجازه تصمیم دارید و درخواست خودتان نیستند. تصمیم در صفحه هر مورد ثبت می‌شود.</p>
      <DataView query={q} loading="در حال دریافت تصمیم‌ها…" errorTitle="تصمیم‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "تصمیمی منتظر شما نیست." }}>
        {(d) => (
          <>
            <ul className="cards" data-testid="decisions-list">
              {d.items.map((it) => (
                <li key={`${it.kind}:${it.entity_id}`} className="card" data-testid={`decision-${it.kind}`}>
                  <div className="card__head">
                    <strong>{DECISION_KIND[it.kind] ?? it.kind}</strong>
                  </div>
                  <dl className="meta">
                    <div>
                      <dt>شماره</dt>
                      <dd>{it.number ? <Num value={it.number} /> : it.revision_no ? `نسخه ${toFaDigits(it.revision_no)}` : "—"}</dd>
                    </div>
                    <div><dt>درخواست‌کننده</dt><dd><Requester id={it.requested_by} name={it.requested_by_name} /></dd></div>
                    <div><dt>زمان</dt><dd>{formatJalaliDateTime(it.requested_at)}</dd></div>
                  </dl>
                  <a className="btn btn--secondary" href={href(it)} data-testid="decision-open">باز کردن و تصمیم</a>
                </li>
              ))}
            </ul>
            {d.truncated ? <p className="field__hint">موارد بیشتری هم هست؛ فهرست کامل را در صفحه هر بخش ببینید.</p> : null}
          </>
        )}
      </DataView>
    </section>
  );
}
