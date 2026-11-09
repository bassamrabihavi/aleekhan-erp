// Role-aware dashboard: the sections the caller may open (from GET /me/permissions) and his live role and
// position assignments (GET /me). No KPI numbers (there is no approved KPI endpoint in PHASE_01).
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { auth, guards, read, write } from "../api/phase01";
import { useAuth } from "../auth/context";
import { NAV } from "../lib/nav";
import { DataView } from "../components/DataView";
import { ReasonDialog } from "../components/Form";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime } from "../lib/format";
import { ASSIGNMENT_STATUS, NETWORK_ZONE, SCOPE_KIND, SESSION_STATE, toneLabel } from "../lib/labels";
import { QK } from "../lib/queries";
import { useAction } from "../lib/useAction";

export function HomePage() {
  const { me, canAny, permissions } = useAuth();
  const items = NAV.filter((n) => n.path !== "/" && n.anyOf && canAny(n.anyOf));
  return (
    <div className="page" data-testid="page-home">
      <div className="page__head">
        <div>
          <p className="eyebrow">پیشخوان</p>
          <h1>سلام، {me?.user.display_name}</h1>
          <p className="lead">بخش‌هایی که نقش‌های شما اجازه می‌دهد در زیر آمده است. هر اقدام دوباره در سرور بررسی می‌شود.</p>
        </div>
      </div>
      {items.length === 0 ? (
        <p className="state state--empty" data-testid="state-empty">
          هنوز نقشی به شما داده نشده یا نقش شما به هیچ بخشی دسترسی ندارد. از مالک سامانه بخواهید نقش مناسب را انتساب دهد.
        </p>
      ) : (
        <ul className="tiles" data-testid="home-tiles">
          {items.map((n) => (
            <li key={n.path}>
              <a className="tile" href={`#${n.path}`}>
                <span className="tile__title">{n.label}</span>
                {n.page ? <span className="tile__meta">صفحه {n.page.toLocaleString("fa-IR")} کاتالوگ</span> : null}
              </a>
            </li>
          ))}
        </ul>
      )}
      <section className="panel panel--wide" aria-labelledby="my-roles">
        <h2 id="my-roles">نقش‌های من</h2>
        {(me?.roles ?? []).length === 0 ? (
          <p>نقش فعالی ندارید ({permissions.size.toLocaleString("fa-IR")} مجوز).</p>
        ) : (
          <MyRoles />
        )}
      </section>
    </div>
  );
}

function MyRoles() {
  const { me, can } = useAuth();
  const roles = useQuery({
    queryKey: [...QK.roles, "options"],
    enabled: can("platform.identity.role.read"),
    queryFn: async ({ signal }) => (await read("/admin/roles", guards.rolePage, { page_size: 100 }, signal)).data,
  });
  const name = new Map((roles.data?.items ?? []).map((r) => [r.role_id, `${r.name_fa} (${r.code})`]));
  return (
    <ul className="list" data-testid="my-roles-list">
      {(me?.roles ?? []).map((r) => {
        const st = toneLabel(ASSIGNMENT_STATUS, r.status);
        return (
          <li key={r.assignment_id}>
            {name.get(r.role_id) ?? <code dir="ltr">{r.role_id.slice(0, 8)}</code>} · {SCOPE_KIND[r.scope.kind] ?? r.scope.kind} ·{" "}
            <StatusChip tone={st.tone} label={st.label} />
            {r.self_assignment ? " · خودانتسابی" : ""}
          </li>
        );
      })}
    </ul>
  );
}

export function MySessionsPage() {
  const q = useQuery({ queryKey: QK.sessions, queryFn: async ({ signal }) => (await auth.mySessions(signal)).data });
  const action = useAction();
  const [revoke, setRevoke] = useState<string | null>(null);
  return (
    <div className="page" data-testid="page-sessions">
      <div className="page__head">
        <div>
          <p className="eyebrow">حساب من</p>
          <h1>جلسه‌های من</h1>
          <p className="lead">حداکثر ۳ جلسه هم‌زمان؛ با ورود چهارم قدیمی‌ترین جلسه خودکار بسته می‌شود (DEC-051).</p>
        </div>
      </div>
      <DataView query={q} loading="در حال دریافت جلسه‌ها…" errorTitle="جلسه‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "جلسه فعالی نیست." }}>
        {(d) => (
          <ul className="cards" data-testid="sessions-list">
            {d.items.map((s) => {
              const st = toneLabel(SESSION_STATE, s.state);
              return (
                <li key={s.session_handle} className="card">
                  <div className="card__head">
                    <StatusChip tone={st.tone} label={st.label} />
                    {s.is_current ? <strong data-testid="session-current">جلسه همین مرورگر</strong> : null}
                  </div>
                  <dl className="meta">
                    <div><dt>شبکه</dt><dd>{NETWORK_ZONE[s.network_zone] ?? s.network_zone}</dd></div>
                    <div><dt>شروع</dt><dd>{formatJalaliDateTime(s.created_at)}</dd></div>
                    <div><dt>آخرین فعالیت</dt><dd>{formatJalaliDateTime(s.last_seen_at)}</dd></div>
                    <div><dt>پایان</dt><dd>{formatJalaliDateTime(s.expires_at)}</dd></div>
                    <div><dt>آخرین تأیید دومرحله‌ای</dt><dd>{s.mfa_verified_at ? formatJalaliDateTime(s.mfa_verified_at) : "—"}</dd></div>
                  </dl>
                  {!s.is_current ? (
                    <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setRevoke(s.session_handle); }}>بستن این جلسه</button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </DataView>
      {revoke ? (
        <ReasonDialog
          title="بستن جلسه"
          submitLabel="بستن جلسه"
          danger
          action={action}
          onClose={() => { setRevoke(null); }}
          onSubmit={async (reason) =>
            (await action.run((key) => write(`/auth/sessions/${revoke}/revoke`, guards.session, { reason }, key), [QK.sessions])) !== undefined
          }
        />
      ) : null}
    </div>
  );
}
