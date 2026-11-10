// Page 46 «امنیت و کاربران» (MOCK_UI_BINDING §6.5): users, roles, role assignments. Every value comes from the
// API; every write carries a reason, an Idempotency-Key and If-Match (where the contract asks for it).
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  guards,
  read,
  write,
  type OneTimeCredential,
  type Role,
  type RoleAssignment,
  type Scope,
  type User,
} from "../api/phase01";
import { useAuth } from "../auth/context";
import { ActionError } from "../components/ActionError";
import { DataView } from "../components/DataView";
import { Dialog } from "../components/Dialog";
import { Field, ReasonDialog, ShortId, TabPanel, Tabs } from "../components/Form";
import { StatusChip } from "../components/StatusChip";
import { formatJalaliDateTime, toFaDigits } from "../lib/format";
import {
  ACCOUNT_KIND,
  ASSIGNMENT_STATUS,
  NETWORK_POLICY,
  NETWORK_ZONE,
  ROLE_KIND,
  ROLE_STATUS,
  SCOPE_KIND,
  SESSION_STATE,
  toneLabel,
  USER_STATUS,
} from "../lib/labels";
import {
  localInputToUtc,
  QK,
  usePermissionCatalogue,
  useCursor,
  useRoleOptions,
  useUnitOptions,
  useUserOptions,
} from "../lib/queries";
import { useAction } from "../lib/useAction";

const A = {
  userRead: "platform.identity.user.read",
  userCreate: "platform.identity.user.create",
  userDisable: "platform.identity.user.disable",
  userUnlock: "platform.identity.user.unlock",
  resetPw: "platform.identity.user.reset_password",
  resetMfa: "platform.identity.user.reset_mfa",
  sessionRead: "platform.identity.session.read",
  sessionRevoke: "platform.identity.session.revoke",
  roleRead: "platform.identity.role.read",
  assignRead: "platform.identity.assignment.read",
  assignGrant: "platform.identity.assignment.grant",
};

export function SecurityPage() {
  const { can } = useAuth();
  const tabs = [
    ...(can(A.userRead) ? [{ id: "users", label: "کاربران" }] : []),
    ...(can(A.roleRead) ? [{ id: "roles", label: "نقش‌ها و مجوزها" }] : []),
    ...(can(A.assignRead) ? [{ id: "assignments", label: "انتساب نقش" }] : []),
  ];
  const [tab, setTab] = useState(tabs[0]?.id ?? "users");
  return (
    <div className="page" data-testid="page-security">
      <div className="page__head">
        <div>
          <p className="eyebrow">صفحه ۴۶ · فاز ۱</p>
          <h1>امنیت و کاربران</h1>
          <p className="lead">
            کاربران فقط داخل سامانه و توسط مالک ساخته می‌شوند (DEC-003). مالک سامانه درخواست‌های تأیید، تأیید سند و
            انتشار پارامتر قاعده کسب‌وکار را مستقیم تصمیم می‌گیرد، ولی هرگز درخواست خودش را نه (DEC-056)؛ نقش‌های فنی
            دیگر (فناوری اطلاعات، ممیز) حق تأیید کسب‌وکار ندارند و تأییدها طبق نقش‌ها انجام می‌شود.
          </p>
        </div>
      </div>
      {tabs.length === 0 ? (
        <p className="state state--forbidden" data-testid="state-forbidden">به این بخش دسترسی ندارید.</p>
      ) : (
        <>
          <Tabs tabs={tabs} active={tab} onChange={setTab} label="بخش‌های امنیت و کاربران" />
          <TabPanel id={tab}>
            {tab === "users" ? <UsersTab /> : tab === "roles" ? <RolesTab /> : <AssignmentsTab />}
          </TabPanel>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ users
function UsersTab() {
  const { can } = useAuth();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const cursor = useCursor();
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const query = useQuery({
    queryKey: [...QK.users, "list", status, search, cursor.cursor],
    queryFn: async ({ signal }) =>
      (await read("/admin/users", guards.userPage, { status, q: search, cursor: cursor.cursor, page_size: 25 }, signal)).data,
  });

  return (
    <section className="panel panel--wide" aria-labelledby="users-title">
      <div className="panel__head">
        <h2 id="users-title">کاربران</h2>
        {can(A.userCreate) ? (
          <button type="button" className="btn btn--primary" onClick={() => { setCreating(true); }} data-testid="user-create-open">
            کاربر جدید
          </button>
        ) : null}
      </div>
      <form
        className="filters"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          cursor.reset();
          setSearch(q.trim());
        }}
      >
        <Field label="وضعیت">
          {(id) => (
            <select id={id} className="input" value={status} onChange={(e) => { cursor.reset(); setStatus(e.target.value); }} data-testid="user-status-filter">
              <option value="">همه</option>
              {Object.entries(USER_STATUS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="جستجوی نام کاربری یا نام">
          {(id) => (
            <input id={id} className="input" value={q} maxLength={64} onChange={(e) => { setQ(e.target.value); }} data-testid="user-search" />
          )}
        </Field>
        <button type="submit" className="btn btn--secondary">
          جستجو
        </button>
      </form>
      <DataView
        query={query}
        loading="در حال دریافت کاربران…"
        errorTitle="فهرست کاربران دریافت نشد"
        isEmpty={(d) => d.items.length === 0}
        empty={{ title: "کاربری با این شرط پیدا نشد." }}
      >
        {(d) => (
          <>
            <table className="table table--cards" data-testid="users-table">
              <caption className="sr-only">فهرست کاربران</caption>
              <thead>
                <tr>
                  <th scope="col">نام کاربری</th>
                  <th scope="col">نام نمایشی</th>
                  <th scope="col">وضعیت</th>
                  <th scope="col">نوع حساب</th>
                  <th scope="col">ورود دومرحله‌ای</th>
                  <th scope="col">آخرین ورود</th>
                  <th scope="col">
                    <span className="sr-only">اقدام</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((u) => {
                  const st = toneLabel(USER_STATUS, u.status);
                  return (
                    <tr key={u.user_id} aria-selected={selected === u.user_id}>
                      <td data-label="نام کاربری">
                        <code dir="ltr">{u.username}</code>
                      </td>
                      <td data-label="نام نمایشی">{u.display_name}</td>
                      <td data-label="وضعیت">
                        <StatusChip tone={st.tone} label={st.label} />
                      </td>
                      <td data-label="نوع حساب">{ACCOUNT_KIND[u.account_kind] ?? u.account_kind}</td>
                      <td data-label="ورود دومرحله‌ای">
                        {u.mfa_enrolled ? "فعال" : u.mfa_required ? "لازم؛ هنوز فعال نشده" : "لازم نیست"}
                      </td>
                      <td data-label="آخرین ورود">{u.last_login_at ? formatJalaliDateTime(u.last_login_at) : "—"}</td>
                      <td data-label="اقدام">
                        <button type="button" className="btn btn--secondary" onClick={() => { setSelected(u.user_id); }} data-testid={`user-open-${u.username}`}>
                          جزئیات
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <Pager depth={cursor.depth} next={d.page.next_cursor} onNext={cursor.next} onPrev={cursor.prev} />
          </>
        )}
      </DataView>
      {selected ? <UserDetail userId={selected} onClose={() => { setSelected(null); }} /> : null}
      {creating ? <CreateUserDialog onClose={() => { setCreating(false); }} /> : null}
    </section>
  );
}

export function Pager({ depth, next, onNext, onPrev }: { depth: number; next: string | null; onNext: (c: string | null) => void; onPrev: () => void }) {
  if (depth === 0 && !next) return null;
  return (
    <div className="pager">
      <button type="button" className="btn btn--secondary" disabled={depth === 0} onClick={onPrev}>
        صفحه قبل
      </button>
      <button type="button" className="btn btn--secondary" disabled={!next} onClick={() => { onNext(next); }} data-testid="pager-next">
        صفحه بعد
      </button>
    </div>
  );
}

/** One-time password: shown exactly once, never stored in the client after closing (DEC-051). */
function OneTimePasswordDialog({ credential, username, onClose }: { credential: OneTimeCredential; username: string; onClose: () => void }) {
  const [ack, setAck] = useState(false);
  return (
    <Dialog title="رمز یک‌بارمصرف" onClose={onClose} closeOnEscape={false} testId="otp-dialog">
      <p className="notice notice--warning">
        این رمز فقط همین یک بار نمایش داده می‌شود و سامانه آن را دوباره نشان نمی‌دهد. آن را حضوری و امن به کاربر بدهید؛
        در اولین ورود باید عوض شود.
      </p>
      <dl className="meta meta--rows">
        <div>
          <dt>نام کاربری</dt>
          <dd>
            <code dir="ltr">{username}</code>
          </dd>
        </div>
        <div>
          <dt>رمز یک‌بارمصرف</dt>
          <dd>
            <code dir="ltr" className="secret" data-testid="otp-value">
              {credential.one_time_password}
            </code>
          </dd>
        </div>
        <div>
          <dt>اعتبار تا</dt>
          <dd>{formatJalaliDateTime(credential.expires_at)}</dd>
        </div>
      </dl>
      <label className="check">
        <input type="checkbox" checked={ack} onChange={(e) => { setAck(e.target.checked); }} data-testid="otp-ack" />
        رمز را یادداشت کردم و به‌صورت امن تحویل می‌دهم.
      </label>
      <div className="form__actions">
        <button type="button" className="btn btn--primary" disabled={!ack} onClick={onClose} data-testid="otp-close">
          بستن (رمز دیگر نمایش داده نمی‌شود)
        </button>
      </div>
    </Dialog>
  );
}

function CreateUserDialog({ onClose }: { onClose: () => void }) {
  const action = useAction();
  const [form, setForm] = useState({ username: "", display_name: "", account_kind: "PERSON", network_policy: "ANY_WITH_MFA_OUTSIDE", reason: "" });
  const [created, setCreated] = useState<{ user: User; one_time_credential: OneTimeCredential } | null>(null);
  if (created) {
    return <OneTimePasswordDialog credential={created.one_time_credential} username={created.user.username} onClose={onClose} />;
  }
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
  };
  return (
    <Dialog title="ساخت کاربر جدید" onClose={onClose} testId="user-create-dialog">
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          void action
            .run((key) => write("/admin/users", guards.userCreated, { ...form, username: form.username.trim() }, key), [QK.users])
            .then((r) => {
              if (r) setCreated(r.data);
            });
        }}
      >
        <Field label="نام کاربری (حروف کوچک لاتین)">
          {(id) => <input id={id} className="input" dir="ltr" required maxLength={64} value={form.username} onChange={set("username")} data-testid="new-username" />}
        </Field>
        <Field label="نام نمایشی">
          {(id) => <input id={id} className="input" required maxLength={200} value={form.display_name} onChange={set("display_name")} data-testid="new-display-name" />}
        </Field>
        <Field label="نوع حساب">
          {(id) => (
            <select id={id} className="input" value={form.account_kind} onChange={set("account_kind")} data-testid="new-account-kind">
              {Object.entries(ACCOUNT_KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          )}
        </Field>
        <Field label="سیاست شبکه">
          {(id) => (
            <select id={id} className="input" value={form.network_policy} onChange={set("network_policy")}>
              {Object.entries(NETWORK_POLICY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          )}
        </Field>
        <Field label="دلیل (در ممیزی ثبت می‌شود)">
          {(id) => <textarea id={id} className="input" rows={2} required minLength={3} maxLength={500} value={form.reason} onChange={set("reason")} data-testid="new-reason" />}
        </Field>
        <p className="field__hint">رمز یک‌بارمصرف را سرور می‌سازد (اعتبار ۷۲ ساعت، DEC-051) و فقط یک بار نشان داده می‌شود.</p>
        <ActionError error={action.error} />
        <div className="form__actions">
          <button type="submit" className="btn btn--primary" disabled={action.pending} data-testid="user-create-submit">
            {action.pending ? "در حال ساخت…" : "ساخت کاربر"}
          </button>
          <button type="button" className="btn btn--secondary" onClick={onClose}>انصراف</button>
        </div>
      </form>
    </Dialog>
  );
}

type UserOp = "disable" | "enable" | "unlock" | "reset-password" | "reset-mfa" | "revoke-sessions";
const USER_OPS: Record<UserOp, { label: string; path: string; perm: string; danger?: boolean; hint: string }> = {
  disable: { label: "غیرفعال کردن", path: "disable", perm: A.userDisable, danger: true, hint: "کاربر دیگر نمی‌تواند وارد شود و جلسه‌هایش بسته می‌شود." },
  enable: { label: "فعال کردن", path: "enable", perm: A.userDisable, hint: "کاربر دوباره می‌تواند وارد شود." },
  unlock: { label: "باز کردن قفل", path: "unlock", perm: A.userUnlock, hint: "قفل ناشی از ورودهای ناموفق برداشته می‌شود؛ رمز تغییر نمی‌کند." },
  "reset-password": { label: "بازنشانی رمز", path: "reset-password", perm: A.resetPw, danger: true, hint: "رمز یک‌بارمصرف تازه ساخته و فقط یک بار نشان داده می‌شود." },
  "reset-mfa": { label: "بازنشانی ورود دومرحله‌ای", path: "reset-mfa", perm: A.resetMfa, danger: true, hint: "عامل دوم و کدهای بازیابی باطل می‌شوند؛ کاربر باید دوباره فعال کند." },
  "revoke-sessions": { label: "ابطال همه جلسه‌ها", path: "sessions/revoke-all", perm: A.sessionRevoke, danger: true, hint: "کاربر از همه دستگاه‌ها خارج می‌شود." },
};

function UserDetail({ userId, onClose }: { userId: string; onClose: () => void }) {
  const { can } = useAuth();
  const [op, setOp] = useState<UserOp | null>(null);
  const [otp, setOtp] = useState<OneTimeCredential | null>(null);
  const action = useAction();
  const detail = useQuery({
    queryKey: [...QK.users, "detail", userId],
    queryFn: async ({ signal }) => read(`/admin/users/${userId}`, guards.user, undefined, signal),
  });
  const sessions = useQuery({
    queryKey: [...QK.users, "sessions", userId],
    enabled: can(A.sessionRead),
    queryFn: async ({ signal }) => (await read(`/admin/users/${userId}/sessions`, guards.sessionPage, undefined, signal)).data,
  });
  const effective = useQuery({
    queryKey: [...QK.users, "effective", userId],
    queryFn: async ({ signal }) => (await read(`/admin/users/${userId}/effective-permissions`, guards.effective, undefined, signal)).data,
  });

  return (
    <section className="detail" aria-labelledby="user-detail-title" data-testid="user-detail">
      <div className="panel__head">
        <h3 id="user-detail-title">جزئیات کاربر</h3>
        <button type="button" className="btn btn--secondary" onClick={onClose}>بستن جزئیات</button>
      </div>
      <DataView query={detail} loading="در حال دریافت کاربر…" errorTitle="کاربر دریافت نشد">
        {(r) => {
          const u = r.data;
          const st = toneLabel(USER_STATUS, u.status);
          const ops: UserOp[] = [
            ...(u.status === "DISABLED" ? (["enable"] as const) : (["disable"] as const)),
            ...(u.status === "LOCKED" ? (["unlock"] as const) : []),
            "reset-password",
            "reset-mfa",
            "revoke-sessions",
          ];
          return (
            <>
              <dl className="meta meta--rows">
                <div><dt>نام کاربری</dt><dd><code dir="ltr">{u.username}</code></dd></div>
                <div><dt>نام نمایشی</dt><dd>{u.display_name}</dd></div>
                <div><dt>وضعیت</dt><dd><StatusChip tone={st.tone} label={st.label} testId="user-detail-status" /></dd></div>
                <div><dt>سیاست شبکه</dt><dd>{NETWORK_POLICY[u.network_policy] ?? u.network_policy}</dd></div>
                <div><dt>ساخته‌شده</dt><dd>{formatJalaliDateTime(u.created_at)}</dd></div>
                <div><dt>نسخه ردیف</dt><dd>{toFaDigits(u.row_version)}</dd></div>
              </dl>
              <div className="actions" role="group" aria-label="اقدام‌های کاربر">
                {ops.filter((o) => can(USER_OPS[o].perm)).map((o) => (
                  <button key={o} type="button" className={USER_OPS[o].danger ? "btn btn--danger-outline" : "btn btn--secondary"} onClick={() => { action.reset(); setOp(o); }} data-testid={`user-op-${o}`}>
                    {USER_OPS[o].label}
                  </button>
                ))}
              </div>
              {op ? (
                <ReasonDialog
                  title={USER_OPS[op].label}
                  description={USER_OPS[op].hint}
                  submitLabel={USER_OPS[op].label}
                  danger={USER_OPS[op].danger ?? false}
                  action={action}
                  onClose={() => { setOp(null); }}
                  onSubmit={async (reason) => {
                    const path = `/admin/users/${userId}/${USER_OPS[op].path}`;
                    if (op === "reset-password") {
                      const cred = await action.run((key) => write(path, guards.oneTime, { reason }, key, r.version), [QK.users]);
                      if (cred) setOtp(cred.data);
                      return cred !== undefined;
                    }
                    const out = await action.run((key) => write(path, guards.user, { reason }, key, r.version), [QK.users]);
                    return out !== undefined;
                  }}
                />
              ) : null}
              {otp ? <OneTimePasswordDialog credential={otp} username={u.username} onClose={() => { setOtp(null); }} /> : null}
            </>
          );
        }}
      </DataView>
      {can(A.sessionRead) ? (
        <>
          <h4>جلسه‌های فعال کاربر</h4>
          <DataView query={sessions} loading="در حال دریافت جلسه‌ها…" errorTitle="جلسه‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "جلسه فعالی ندارد." }}>
            {(d) => (
              <ul className="list">
                {d.items.map((s) => {
                  const st = toneLabel(SESSION_STATE, s.state);
                  return (
                    <li key={s.session_handle}>
                      <StatusChip tone={st.tone} label={st.label} /> {NETWORK_ZONE[s.network_zone] ?? s.network_zone} · آخرین فعالیت{" "}
                      {formatJalaliDateTime(s.last_seen_at)} · پایان {formatJalaliDateTime(s.expires_at)}
                    </li>
                  );
                })}
              </ul>
            )}
          </DataView>
        </>
      ) : null}
      <h4>مجوزهای مؤثر</h4>
      <DataView query={effective} loading="در حال محاسبه مجوزها…" errorTitle="مجوزها دریافت نشد" isEmpty={(d) => d.grants.length === 0} empty={{ title: "هیچ مجوزی ندارد (همه‌چیز بسته)." }}>
        {(d) => (
          <ul className="list list--compact" data-testid="effective-permissions">
            {d.grants.map((g) => (
              <li key={`${g.action}:${g.via_role}:${g.scope.kind}:${g.scope.ref_id ?? ""}`}>
                <code dir="ltr">{g.action}</code> · نقش <code dir="ltr">{g.via_role}</code> · {SCOPE_KIND[g.scope.kind] ?? g.scope.kind}
                {g.mfa_step_up ? " · نیازمند تأیید دومرحله‌ای" : ""}
              </li>
            ))}
          </ul>
        )}
      </DataView>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------ roles
function RolesTab() {
  const roles = useRoleOptions(true);
  const perms = usePermissionCatalogue(true);
  const [open, setOpen] = useState<string | null>(null);
  const flags = new Map((perms.data?.items ?? []).map((p) => [p.action, p]));
  return (
    <section className="panel panel--wide" aria-labelledby="roles-title">
      <h2 id="roles-title">نقش‌ها (ماتریس دسترسی مصوب)</h2>
      <p className="lead">
        مجوز نقش فعال فقط با نسخه تازه ماتریس تغییر می‌کند. «حق تأیید» یعنی مجوز تأیید کسب‌وکار؛ نقش‌های فنی آن را ندارند،
        جز استثنای مصوب DEC-056 (مالک: تصمیم درباره درخواست‌های تأیید، بدون تأیید درخواست خودش).
      </p>
      <DataView query={roles} loading="در حال دریافت نقش‌ها…" errorTitle="نقش‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "نقشی تعریف نشده است." }}>
        {(d) => (
          <table className="table table--cards" data-testid="roles-table">
            <caption className="sr-only">فهرست نقش‌ها</caption>
            <thead>
              <tr>
                <th scope="col">کد</th>
                <th scope="col">نام</th>
                <th scope="col">نوع</th>
                <th scope="col">وضعیت</th>
                <th scope="col">نسخه ماتریس</th>
                <th scope="col">مجوزها</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((r: Role) => {
                const st = toneLabel(ROLE_STATUS, r.status);
                const ba = r.permissions.filter((p) => flags.get(p)?.business_approval);
                return (
                  <tr key={r.role_id}>
                    <td data-label="کد"><code dir="ltr">{r.code}</code></td>
                    <td data-label="نام">{r.name_fa}</td>
                    <td data-label="نوع">{ROLE_KIND[r.kind] ?? r.kind}</td>
                    <td data-label="وضعیت"><StatusChip tone={st.tone} label={st.label} /></td>
                    <td data-label="نسخه ماتریس"><bdi dir="ltr">{r.matrix_version ?? "—"}</bdi></td>
                    <td data-label="مجوزها">
                      <button type="button" className="btn btn--link" aria-expanded={open === r.role_id} onClick={() => { setOpen(open === r.role_id ? null : r.role_id); }} data-testid={`role-open-${r.code}`}>
                        {toFaDigits(r.permissions.length)} مجوز{ba.length ? ` (${toFaDigits(ba.length)} حق تأیید)` : ""}
                      </button>
                      {open === r.role_id ? (
                        <ul className="list list--compact" data-testid={`role-perms-${r.code}`}>
                          {r.permissions.map((p) => (
                            <li key={p}>
                              <code dir="ltr">{p}</code> {flags.get(p)?.description_fa ?? ""}
                              {flags.get(p)?.business_approval ? <strong> · حق تأیید</strong> : null}
                              {flags.get(p)?.mfa_step_up ? " · دومرحله‌ای" : ""}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </DataView>
    </section>
  );
}

// ------------------------------------------------------------------------------------------ assignments
function AssignmentsTab() {
  const { can, me } = useAuth();
  const users = useUserOptions(can(A.userRead));
  const roles = useRoleOptions(can(A.roleRead));
  const [userFilter, setUserFilter] = useState("");
  const [granting, setGranting] = useState(false);
  const [revoke, setRevoke] = useState<RoleAssignment | null>(null);
  const action = useAction();
  const cursor = useCursor();
  const list = useQuery({
    queryKey: [...QK.assignments, userFilter, cursor.cursor],
    queryFn: async ({ signal }) =>
      (await read("/admin/role-assignments", guards.assignmentPage, { user_id: userFilter, cursor: cursor.cursor, page_size: 50 }, signal)).data,
  });
  const userName = new Map((users.data?.items ?? []).map((u) => [u.user_id, u]));
  const roleById = new Map((roles.data?.items ?? []).map((r) => [r.role_id, r]));

  return (
    <section className="panel panel--wide" aria-labelledby="assign-title">
      <div className="panel__head">
        <h2 id="assign-title">انتساب نقش</h2>
        {can(A.assignGrant) ? (
          <button type="button" className="btn btn--primary" onClick={() => { setGranting(true); }} data-testid="grant-open">
            انتساب نقش تازه
          </button>
        ) : null}
      </div>
      <p className="lead">
        انتساب نقشی که حق تأیید کسب‌وکار دارد تا تأیید نفر دوم «در انتظار» می‌ماند (DEC-032). نخستین دارنده هر نقش
        تأییدی را مالک یک بار و با دلیل و تأیید دومرحله‌ای تأیید می‌کند (DEC-055) — در صفحه «کارها و تأییدها».
      </p>
      <div className="filters">
        <Field label="کاربر">
          {(id) => (
            <select id={id} className="input" value={userFilter} onChange={(e) => { cursor.reset(); setUserFilter(e.target.value); }} data-testid="assign-user-filter">
              <option value="">همه کاربران</option>
              {(users.data?.items ?? []).map((u) => <option key={u.user_id} value={u.user_id}>{u.display_name} ({u.username})</option>)}
            </select>
          )}
        </Field>
      </div>
      <DataView query={list} loading="در حال دریافت انتساب‌ها…" errorTitle="انتساب‌ها دریافت نشد" isEmpty={(d) => d.items.length === 0} empty={{ title: "انتسابی وجود ندارد." }}>
        {(d) => (
          <>
            <table className="table table--cards" data-testid="assignments-table">
              <caption className="sr-only">انتساب‌های نقش</caption>
              <thead>
                <tr>
                  <th scope="col">کاربر</th>
                  <th scope="col">نقش</th>
                  <th scope="col">دامنه</th>
                  <th scope="col">وضعیت</th>
                  <th scope="col">از / تا</th>
                  <th scope="col">دلیل</th>
                  <th scope="col"><span className="sr-only">اقدام</span></th>
                </tr>
              </thead>
              <tbody>
                {d.items.map((a) => {
                  const st = toneLabel(ASSIGNMENT_STATUS, a.status);
                  const role = roleById.get(a.role_id);
                  const u = userName.get(a.user_id);
                  return (
                    <tr key={a.assignment_id} data-testid={`assignment-${role?.code ?? a.role_id}`}>
                      <td data-label="کاربر">{u ? u.display_name : <ShortId id={a.user_id} />}{a.user_id === me?.user.user_id ? " (شما)" : ""}</td>
                      <td data-label="نقش">{role ? <>{role.name_fa} <code dir="ltr">{role.code}</code></> : <ShortId id={a.role_id} />}</td>
                      <td data-label="دامنه">{SCOPE_KIND[a.scope.kind] ?? a.scope.kind}</td>
                      <td data-label="وضعیت">
                        <StatusChip tone={st.tone} label={st.label} />
                        {a.self_assignment ? <span className="chip chip--warning chip--inline">خودانتسابی</span> : null}
                      </td>
                      <td data-label="از / تا">{formatJalaliDateTime(a.valid_from)} — {a.valid_to ? formatJalaliDateTime(a.valid_to) : "بی‌پایان"}</td>
                      <td data-label="دلیل">{a.reason}</td>
                      <td data-label="اقدام">
                        {can(A.assignGrant) && (a.status === "ACTIVE" || a.status === "PENDING_APPROVAL") ? (
                          <button type="button" className="btn btn--danger-outline" onClick={() => { action.reset(); setRevoke(a); }} data-testid="assignment-revoke">
                            لغو
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <Pager depth={cursor.depth} next={d.page.next_cursor} onNext={cursor.next} onPrev={cursor.prev} />
          </>
        )}
      </DataView>
      {revoke ? (
        <ReasonDialog
          title="لغو انتساب نقش"
          submitLabel="لغو انتساب"
          danger
          action={action}
          onClose={() => { setRevoke(null); }}
          onSubmit={async (reason) =>
            (await action.run((key) => write(`/admin/role-assignments/${revoke.assignment_id}/revoke`, guards.assignment, { reason }, key, revoke.row_version), [QK.assignments, QK.work])) !== undefined
          }
        />
      ) : null}
      {granting ? <GrantDialog onClose={() => { setGranting(false); }} /> : null}
    </section>
  );
}

function GrantDialog({ onClose }: { onClose: () => void }) {
  const { me, can } = useAuth();
  const users = useUserOptions(can(A.userRead));
  const roles = useRoleOptions(true);
  const perms = usePermissionCatalogue(true);
  const units = useUnitOptions(can("platform.org.read"));
  const action = useAction();
  const [userId, setUserId] = useState("");
  const [roleId, setRoleId] = useState("");
  const [scopeKind, setScopeKind] = useState<Scope["kind"]>("GLOBAL");
  const [unitId, setUnitId] = useState("");
  const [validTo, setValidTo] = useState("");
  const [confirmSelf, setConfirmSelf] = useState(false);
  const [reason, setReason] = useState("");
  const [result, setResult] = useState<RoleAssignment | null>(null);
  const role = roles.data?.items.find((r) => r.role_id === roleId);
  const ba = new Set((perms.data?.items ?? []).filter((p) => p.business_approval).map((p) => p.action));
  const needsSecond = role ? role.permissions.some((p) => ba.has(p)) : false;
  const isSelf = userId !== "" && userId === me?.user.user_id;

  if (result) {
    const st = toneLabel(ASSIGNMENT_STATUS, result.status);
    return (
      <Dialog title="نتیجه انتساب" onClose={onClose} testId="grant-result">
        <p>
          وضعیت: <StatusChip tone={st.tone} label={st.label} testId="grant-result-status" />
        </p>
        {result.status === "PENDING_APPROVAL" ? (
          <p className="notice notice--info">
            این نقش حق تأیید کسب‌وکار دارد؛ انتساب تا تصمیم نفر دوم در صفحه «کارها و تأییدها» در انتظار می‌ماند (DEC-032).
          </p>
        ) : null}
        <div className="form__actions">
          <button type="button" className="btn btn--primary" onClick={onClose} data-testid="grant-result-close">بستن</button>
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog title="انتساب نقش" onClose={onClose} testId="grant-dialog">
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          const scope: Scope = scopeKind === "GLOBAL" ? { kind: "GLOBAL" } : { kind: scopeKind, ref_id: unitId };
          const body: Record<string, unknown> = { user_id: userId, role_id: roleId, scope, reason: reason.trim() };
          const to = localInputToUtc(validTo);
          if (to) body.valid_to = to;
          if (isSelf) body.confirm_self_assignment = confirmSelf;
          void action.run((key) => write("/admin/role-assignments", guards.assignment, body, key), [QK.assignments, QK.work]).then((r) => {
            if (r) setResult(r.data);
          });
        }}
      >
        <Field label="کاربر">
          {(id) => (
            <select id={id} className="input" required value={userId} onChange={(e) => { setUserId(e.target.value); }} data-testid="grant-user">
              <option value="">انتخاب کنید</option>
              {(users.data?.items ?? []).map((u) => <option key={u.user_id} value={u.user_id}>{u.display_name} ({u.username})</option>)}
            </select>
          )}
        </Field>
        <Field label="نقش">
          {(id) => (
            <select id={id} className="input" required value={roleId} onChange={(e) => { setRoleId(e.target.value); }} data-testid="grant-role">
              <option value="">انتخاب کنید</option>
              {(roles.data?.items ?? []).filter((r) => r.status === "ACTIVE").map((r) => <option key={r.role_id} value={r.role_id}>{r.name_fa} ({r.code})</option>)}
            </select>
          )}
        </Field>
        {needsSecond ? (
          <p className="notice notice--warning" data-testid="grant-needs-second">
            این نقش حق تأیید کسب‌وکار دارد: انتساب تا تأیید نفر دوم «در انتظار» می‌ماند (DEC-032).
          </p>
        ) : null}
        <Field label="دامنه">
          {(id) => (
            <select id={id} className="input" value={scopeKind} onChange={(e) => { setScopeKind(e.target.value as Scope["kind"]); }} data-testid="grant-scope">
              <option value="GLOBAL">{SCOPE_KIND.GLOBAL}</option>
              <option value="ORG_UNIT">{SCOPE_KIND.ORG_UNIT}</option>
              <option value="ORG_UNIT_SUBTREE">{SCOPE_KIND.ORG_UNIT_SUBTREE}</option>
            </select>
          )}
        </Field>
        {scopeKind !== "GLOBAL" ? (
          <Field label="واحد سازمانی">
            {(id) => (
              <select id={id} className="input" required value={unitId} onChange={(e) => { setUnitId(e.target.value); }}>
                <option value="">انتخاب کنید</option>
                {(units.data?.items ?? []).map((u) => <option key={u.unit_id} value={u.unit_id}>{u.name_fa} ({u.code})</option>)}
              </select>
            )}
          </Field>
        ) : null}
        <Field label="پایان اعتبار (اختیاری)" hint="شروع اعتبار همین لحظه است؛ تاریخ گذشته پذیرفته نمی‌شود.">
          {(id, hintId) => <input id={id} aria-describedby={hintId} className="input" type="datetime-local" value={validTo} onChange={(e) => { setValidTo(e.target.value); }} />}
        </Field>
        {validTo && localInputToUtc(validTo) ? <p className="field__hint">به تقویم شمسی: {formatJalaliDateTime(localInputToUtc(validTo) ?? "")}</p> : null}
        {isSelf ? (
          <label className="check notice notice--warning" data-testid="grant-self">
            <input type="checkbox" checked={confirmSelf} onChange={(e) => { setConfirmSelf(e.target.checked); }} data-testid="grant-self-confirm" />
            این نقش را به خودم انتساب می‌دهم؛ می‌دانم که با علامت «خودانتسابی» در ممیزی ثبت می‌شود (DEC-003).
          </label>
        ) : null}
        <Field label="دلیل (در ممیزی ثبت می‌شود)">
          {(id) => <textarea id={id} className="input" rows={2} required minLength={3} maxLength={500} value={reason} onChange={(e) => { setReason(e.target.value); }} data-testid="grant-reason" />}
        </Field>
        <ActionError error={action.error} />
        <div className="form__actions">
          <button type="submit" className="btn btn--primary" disabled={action.pending || (isSelf && !confirmSelf)} data-testid="grant-submit">
            {action.pending ? "در حال ثبت…" : "ثبت انتساب"}
          </button>
          <button type="button" className="btn btn--secondary" onClick={onClose}>انصراف</button>
        </div>
      </form>
    </Dialog>
  );
}
