// Code rule revisions of the 14-digit product code (DEC-005, page 29 «کدگذاری»): list, golden-case summary
// (counts only - real cases live on the server only, DEC-028/046), submit for review (product data steward),
// approve / reject / activate (code_rule_approver or the owner; never the maker; fresh MFA on approve). The
// approval also appears in the page 39 approval inbox (employer decision 2026-11-15).
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { g, get, K2, PERM, send, type CodeRuleRevision } from "../api/phase02";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView, ForbiddenState } from "../components/DataView";
import { ReasonDialog, ShortId } from "../components/Form";
import { PageHead } from "../components/Phase02";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import { toneLabel } from "../lib/labels";
import { RULE_STATUS } from "../lib/labels02";
import { segments, useRoute } from "../lib/router";
import { useAction } from "../lib/useAction";

export function CodeRulesPage() {
  const { can } = useAuth();
  const route = useRoute();
  const [id] = segments(route, "/code-rules");
  return (
    <div className="page" data-testid="page-code-rules">
      <PageHead
        page="صفحه ۲۹ · فاز ۲ · کدگذاری"
        title="قاعده کد ۱۴رقمی محصول"
        lead="کد فقط زیر نسخه «فعال» قاعده صادر می‌شود. نمونه‌های طلایی واقعی فقط روی سرور ثبت می‌شوند و این صفحه فقط شمارش آن‌ها را نشان می‌دهد. سازنده نسخه هرگز آن را تأیید نمی‌کند."
      />
      {!can(PERM.ruleRead) ? (
        <ForbiddenState />
      ) : (
        <div className="split">
          <RuleList selected={id} />
          {id ? <RuleDetail id={id} /> : null}
        </div>
      )}
    </div>
  );
}

function RuleList({ selected }: { selected: string | undefined }) {
  const list = useQuery({
    queryKey: [...K2.rules, "list"],
    queryFn: async ({ signal }) => (await get("/identity/code-rule-revisions", g.rulePage, { page_size: 50 }, signal)).data,
  });
  return (
    <section className="panel" aria-labelledby="rules-title">
      <h2 id="rules-title">نسخه‌های قاعده</h2>
      <DataView query={list} loading="در حال دریافت نسخه‌ها…" errorTitle="نسخه‌های قاعده دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "هنوز نسخه‌ای از قاعده ثبت نشده است؛ تا وجود نسخه فعال، صدور کد مسدود است." }}>
        {(d) => (
          <ul className="cards" data-testid="rules-list">
            {d.items.map((r) => (
              <li key={r.rule_revision_id} className={r.rule_revision_id === selected ? "card card--selected" : "card"}>
                <a href={`#/code-rules/${r.rule_revision_id}`} className="card__link" data-testid="rule-open">
                  نسخه {toFaDigits(r.revision_no)}
                </a>
                <StatusChip {...toneLabel(RULE_STATUS, r.status)} />
              </li>
            ))}
          </ul>
        )}
      </DataView>
    </section>
  );
}

type Op = "submit" | "approve" | "reject" | "activate";

function RuleDetail({ id }: { id: string }) {
  const { can, me } = useAuth();
  const q = useQuery({
    queryKey: [...K2.rules, "one", id],
    queryFn: async ({ signal }) => get(`/identity/code-rule-revisions/${id}`, g.rule, undefined, signal),
  });
  const action = useAction();
  const [op, setOp] = useState<Op | null>(null);
  return (
    <section className="panel panel--wide" aria-labelledby="rule-title" data-testid="rule-detail">
      <DataView query={q} loading="در حال دریافت نسخه…" errorTitle="نسخه دریافت نشد">
        {(r) => {
          const rule = r.data;
          const mine = rule.created_by === me?.user.user_id;
          return (
            <>
              <div className="panel__head">
                <h2 id="rule-title">نسخه {toFaDigits(rule.revision_no)} قاعده کد</h2>
                <StatusChip {...toneLabel(RULE_STATUS, rule.status)} testId="rule-status" />
              </div>
              <RuleMeta rule={rule} />
              <div className="actions" role="group" aria-label="اقدام‌های نسخه قاعده">
                {rule.status === "DRAFT" && can(PERM.ruleManage) ? (
                  <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp("submit"); }} data-testid="rule-submit">ارسال برای بازبینی</button>
                ) : null}
                {rule.status === "IN_REVIEW" && can(PERM.ruleApprove) && !mine ? (
                  <>
                    <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp("approve"); }} data-testid="rule-approve">تأیید</button>
                    <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setOp("reject"); }} data-testid="rule-reject">رد</button>
                  </>
                ) : null}
                {rule.status === "APPROVED" && can(PERM.ruleApprove) ? (
                  <button type="button" className="btn btn--primary" onClick={() => { action.reset(); setOp("activate"); }} data-testid="rule-activate">فعال‌سازی</button>
                ) : null}
              </div>
              {rule.status === "IN_REVIEW" && mine ? <p className="field__hint" data-testid="rule-own">این نسخه را خودتان ساخته‌اید؛ تأیید آن با فرد دیگری است.</p> : null}
              {!op ? <ActionError error={action.error} /> : null}
              {op ? (
                <ReasonDialog
                  title={{ submit: "ارسال برای بازبینی", approve: "تأیید نسخه قاعده", reject: "رد نسخه قاعده", activate: "فعال‌سازی نسخه قاعده" }[op]}
                  label={op === "approve" ? "یادداشت تأیید (در ممیزی ثبت می‌شود)" : "دلیل (در ممیزی ثبت می‌شود)"}
                  minLength={op === "approve" ? 1 : 3}
                  description={op === "activate" ? "پس از فعال‌سازی، کدهای جدید زیر این نسخه صادر می‌شوند." : undefined}
                  submitLabel={{ submit: "ارسال", approve: "تأیید", reject: "رد", activate: "فعال شود" }[op]}
                  danger={op === "reject"}
                  action={action}
                  onClose={() => { setOp(null); }}
                  onSubmit={async (text) => {
                    const body = op === "approve" ? { resource_revision: rule.revision_no, note: text } : { reason: text };
                    const path = { submit: "submit-review", approve: "approve", reject: "reject", activate: "activate" }[op];
                    return (
                      (await action.run(
                        (key) => send(`/identity/code-rule-revisions/${rule.rule_revision_id}/${path}`, g.rule, body, key, r.version),
                        [K2.rules, K2.inbox],
                      )) !== undefined
                    );
                  }}
                />
              ) : null}
            </>
          );
        }}
      </DataView>
    </section>
  );
}

function RuleMeta({ rule }: { rule: CodeRuleRevision }) {
  const s = rule.golden_summary;
  const types = Array.isArray(rule.scope.product_types) ? (rule.scope.product_types as unknown[]).map(String) : [];
  return (
    <>
      <dl className="meta meta--rows">
        <div><dt>تصمیم</dt><dd><bdi dir="ltr">{rule.decision_id}</bdi></dd></div>
        <div><dt>انواع محصول در محدوده</dt><dd>{types.length ? types.map((t) => <bdi key={t} dir="ltr" className="code14">{t} </bdi>) : "—"}</dd></div>
        <div><dt>سازنده</dt><dd><ShortId id={rule.created_by} /></dd></div>
        <div><dt>تأییدکننده</dt><dd>{rule.approved_by ? <><ShortId id={rule.approved_by} /> · {rule.approved_at ? formatJalaliDateTime(rule.approved_at) : ""}</> : "—"}</dd></div>
        <div><dt>شناسه فایل مبنا (SHA-256)</dt><dd><code dir="ltr" className="code-id" title={rule.source_workbook_sha256}>{rule.source_workbook_sha256.slice(0, 12)}…</code></dd></div>
      </dl>
      {s ? (
        <section aria-labelledby="golden-title" className="subsection" data-testid="golden-summary">
          <h3 id="golden-title">خلاصه نمونه‌های طلایی (فقط شمارش)</h3>
          <dl className="meta meta--rows">
            <div><dt>کل نمونه‌ها</dt><dd>{toFaDigits(s.total)}</dd></div>
            <div><dt>بازتولیدنشده</dt><dd>{toFaDigits(s.not_reproduced)}</dd></div>
            <div><dt>کمربند بررسی‌شده</dt><dd>{toFaDigits(s.belt_checked)}</dd></div>
            <div><dt>استایل ۰۰۰۰ (فقط سابقه)</dt><dd>{toFaDigits(s.legacy_only_style_0000)}</dd></div>
            <div><dt>خانواده‌های زیر حداقل ۲۰</dt><dd>{s.families_below_minimum.length ? s.families_below_minimum.map((f) => <bdi key={f} dir="ltr">{f} </bdi>) : "هیچ"}</dd></div>
          </dl>
          <ul className="list list--compact">
            {Object.entries(s.per_family).map(([fam, n]) => (
              <li key={fam}>خانواده <bdi dir="ltr">{fam}</bdi>: {toFaDigits(n)} نمونه</li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

