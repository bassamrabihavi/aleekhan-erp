// PHASE_01 / 01.5 E2E against the real stack (scripts/e2e.sh: Django runserver + throw-away PostgreSQL DB +
// Vite proxy). No API mocking. Serial: one synthetic owner is bootstrapped on the console (global-setup.ts) and
// then sets the platform up through the UI, exactly as the employer will in UAT.
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";

import {
  answerStepUp,
  expectNoAxeViolations,
  OWNER_USERNAME,
  screenshots,
  SYN_LABEL,
  SYN_PW_DOCCTL_NEW,
  SYN_PW_OWNER_NEW,
  SYN_PW_OWNER_ONE_TIME,
  Totp,
} from "./phase01-helpers";

test.describe.configure({ mode: "serial" });
test.setTimeout(240_000);

const PDF = Buffer.from("%PDF-1.7\n% synthetic E2E document\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");
const RUN = Date.now().toString(36).slice(-5);
const DOCCTL = `syn.e2e.docctl.${RUN}`;
const APPROVER = `syn.e2e.approver.${RUN}`;

let ownerCtx: BrowserContext;
let owner: Page;
let totp: Totp;
let docctlOneTime = "";

async function newPage(browser: Browser): Promise<[BrowserContext, Page]> {
  const ctx = await browser.newContext({ locale: "fa-IR", timezoneId: "Asia/Tehran", viewport: { width: 1440, height: 900 } });
  return [ctx, await ctx.newPage()];
}

async function go(page: Page, hash: string, testId: string): Promise<void> {
  await page.goto(`/#${hash}`);
  await expect(page.getByTestId(testId)).toBeVisible();
}

test.afterAll(async () => {
  await ownerCtx.close();
});

test("login page: Farsi RTL, synthetic-data banner, generic error, four sizes", async ({ browser }) => {
  [ownerCtx, owner] = await newPage(browser);
  await go(owner, "/", "login");
  await expect(owner.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(owner.getByTestId("env-banner")).toContainText(SYN_LABEL);
  await owner.getByTestId("login-username").fill("syn.nobody");
  await owner.getByTestId("login-password").fill("wrong-Pass-0!");
  await owner.getByTestId("login-submit").click();
  const err = owner.getByTestId("action-error");
  await expect(err).toBeVisible();
  await expect(err.getByTestId("action-error-code")).toHaveText("INVALID_CREDENTIALS");
  await expectNoAxeViolations(owner);
  await screenshots(owner, "login", async () => {
    await expect(owner.getByTestId("login")).toBeVisible();
  });
});

test("owner first login: one-time password -> forced change -> TOTP enrolment -> 10 recovery codes", async () => {
  await owner.getByTestId("login-username").fill(OWNER_USERNAME);
  await owner.getByTestId("login-password").fill(SYN_PW_OWNER_ONE_TIME);
  await owner.getByTestId("login-submit").click();
  await expect(owner.getByTestId("password-change")).toBeVisible();
  await owner.getByTestId("pw-current").fill(SYN_PW_OWNER_ONE_TIME);
  await owner.getByTestId("pw-new").fill(SYN_PW_OWNER_NEW);
  await owner.getByTestId("pw-repeat").fill(SYN_PW_OWNER_NEW);
  await owner.getByTestId("pw-submit").click();
  await expect(owner.getByTestId("mfa-enrolment")).toBeVisible();
  await owner.getByTestId("enrol-start").click();
  const secret = (await owner.getByTestId("enrol-secret").innerText()).replace(/\s+/g, "");
  expect(secret).toMatch(/^[A-Z2-7]{16,}$/);
  totp = new Totp(secret);
  await owner.getByTestId("enrol-code").fill(await totp.next());
  await owner.getByTestId("enrol-confirm").click();
  await expect(owner.getByTestId("recovery-code-list").locator("li")).toHaveCount(10);
  await owner.getByTestId("recovery-done").click();
  await expect(owner.getByTestId("page-home")).toBeVisible();
  await expect(owner.getByTestId("main-nav")).toContainText("امنیت و کاربران");
  await expectNoAxeViolations(owner);
  await screenshots(owner, "home-owner", async () => {
    await expect(owner.getByTestId("home-tiles")).toBeVisible();
  });
});

test("org tree: create units / unit-head position / holder (step-up MFA), keyboard tree", async () => {
  await go(owner, "/org", "page-org");
  await expect(owner.getByTestId("state-empty")).toBeVisible();
  await screenshots(owner, "org-empty", async () => {
    await expect(owner.getByTestId("state-empty")).toBeVisible();
  });
  // root company
  await owner.getByTestId("org-new-unit").click();
  await owner.getByTestId("unit-code").fill(`syn_co_${RUN}`);
  await owner.getByTestId("unit-name").fill(`شرکت ساختگی (${SYN_LABEL})`);
  await owner.getByTestId("org-reason").fill("ساخت درخت ساختگی E2E");
  await owner.getByTestId("unit-dialog-submit").click();
  await answerStepUp(owner, totp);
  await expect(owner.getByTestId("unit-dialog")).toBeHidden();
  // department under it
  await owner.getByTestId("org-new-unit").click();
  await owner.getByTestId("unit-code").fill(`syn_dep_${RUN}`);
  await owner.getByTestId("unit-name").fill(`اداره ساختگی (${SYN_LABEL})`);
  await owner.getByTestId("unit-type").selectOption("DEPARTMENT");
  await owner.getByTestId("unit-parent").selectOption({ label: `شرکت ساختگی (${SYN_LABEL}) (syn_co_${RUN})` });
  await owner.getByTestId("org-reason").fill("زیرمجموعه ساختگی");
  await owner.getByTestId("unit-dialog-submit").click();
  await answerStepUp(owner, totp, 1500);
  await expect(owner.getByTestId("unit-dialog")).toBeHidden();
  // unit-head position: capacity fixed to 1
  await owner.getByTestId("org-new-position").click();
  await owner.getByTestId("position-unit").selectOption({ label: `اداره ساختگی (${SYN_LABEL}) (syn_dep_${RUN})` });
  await owner.getByTestId("position-code").fill(`syn_head_${RUN}`);
  await owner.getByTestId("position-title").fill("رئیس اداره ساختگی");
  await owner.getByTestId("position-head").check();
  await expect(owner.getByTestId("position-capacity")).toBeDisabled();
  await owner.getByTestId("org-reason").fill("سمت ساختگی");
  await owner.getByTestId("position-dialog-submit").click();
  await answerStepUp(owner, totp, 1500);
  await expect(owner.getByTestId("position-dialog")).toBeHidden();
  // the owner holds it (valid from now: no back-dating)
  await owner.getByTestId("org-new-assignment").click();
  await owner.getByTestId("assign-position").selectOption({ label: `رئیس اداره ساختگی (syn_head_${RUN}) — رئیس واحد` });
  await owner.getByTestId("assign-user").selectOption({ index: 1 });
  await owner.getByTestId("org-reason").fill("انتصاب ساختگی");
  await owner.getByTestId("assign-dialog-submit").click();
  await answerStepUp(owner, totp, 1500);
  await expect(owner.getByTestId("assign-dialog")).toBeHidden();

  const tree = owner.getByTestId("org-tree");
  await expect(tree.getByRole("treeitem")).toHaveCount(3);
  await expect(tree).toContainText("متصدی: مالک ساختگی");
  // keyboard (RTL tree): ArrowDown to the department, ArrowRight collapses it, ArrowRight again goes to the
  // parent, ArrowLeft on an open unit goes to its first child, ArrowLeft on a closed one opens it
  const items = tree.getByRole("treeitem");
  await items.first().focus();
  await owner.keyboard.press("ArrowDown");
  await expect(items.nth(1)).toBeFocused();
  await owner.keyboard.press("ArrowRight");
  await expect(items.nth(1)).toHaveAttribute("aria-expanded", "false");
  await expect(items).toHaveCount(2);
  await owner.keyboard.press("ArrowRight");
  await expect(items.first()).toBeFocused();
  await owner.keyboard.press("ArrowLeft");
  await expect(items.nth(1)).toBeFocused();
  await owner.keyboard.press("ArrowLeft");
  await expect(items.nth(1)).toHaveAttribute("aria-expanded", "true");
  await expect(items).toHaveCount(3);
  await expect(items.nth(1)).toBeFocused();
  const outline = await items.nth(1).evaluate((el) => getComputedStyle(el).boxShadow);
  expect(outline).not.toBe("none"); // visible focus ring
  await expectNoAxeViolations(owner);
  await screenshots(owner, "org-tree", async () => {
    await expect(tree).toBeVisible();
  });
});

test("page 46: create users (one-time password shown once), grant roles, pending second approval", async () => {
  await go(owner, "/security", "page-security");
  await expect(owner.getByTestId("users-table")).toBeVisible();
  // document controller
  await owner.getByTestId("user-create-open").click();
  await owner.getByTestId("new-username").fill(DOCCTL);
  await owner.getByTestId("new-display-name").fill(`مسئول اسناد ساختگی (${SYN_LABEL})`);
  await owner.getByTestId("new-reason").fill("کاربر ساختگی E2E");
  await owner.getByTestId("user-create-submit").click();
  await answerStepUp(owner, totp, 2500);
  await expect(owner.getByTestId("otp-dialog")).toBeVisible();
  docctlOneTime = (await owner.getByTestId("otp-value").innerText()).trim();
  expect(docctlOneTime.length).toBeGreaterThanOrEqual(12);
  await expect(owner.getByTestId("otp-close")).toBeDisabled();
  await owner.getByTestId("otp-ack").check();
  await owner.getByTestId("otp-close").click();
  await expect(owner.getByText(docctlOneTime)).toHaveCount(0); // never shown again
  // approver
  await owner.getByTestId("user-create-open").click();
  await owner.getByTestId("new-username").fill(APPROVER);
  await owner.getByTestId("new-display-name").fill(`تأییدکننده ساختگی (${SYN_LABEL})`);
  await owner.getByTestId("new-reason").fill("کاربر ساختگی E2E");
  await owner.getByTestId("user-create-submit").click();
  await answerStepUp(owner, totp, 1500);
  await owner.getByTestId("otp-ack").check();
  await owner.getByTestId("otp-close").click();
  await expectNoAxeViolations(owner);
  await screenshots(owner, "security-users", async () => {
    await expect(owner.getByTestId("users-table")).toBeVisible();
  });
  // user detail
  await owner.getByTestId(`user-open-${DOCCTL}`).click();
  await expect(owner.getByTestId("user-detail")).toContainText(DOCCTL);
  await expect(owner.getByTestId("effective-permissions").or(owner.getByText("هیچ مجوزی ندارد (همه‌چیز بسته)."))).toBeVisible();

  // grants
  await owner.getByTestId("tab-assignments").click();
  await owner.getByTestId("grant-open").click();
  await owner.getByTestId("grant-user").selectOption({ label: `مسئول اسناد ساختگی (${SYN_LABEL}) (${DOCCTL})` });
  await owner.getByTestId("grant-role").selectOption({ label: "مسئول اسناد (document_controller)" });
  await expect(owner.getByTestId("grant-needs-second")).toHaveCount(0);
  await owner.getByTestId("grant-reason").fill("انتساب ساختگی");
  await owner.getByTestId("grant-submit").click();
  await answerStepUp(owner, totp, 1500);
  await expect(owner.getByTestId("grant-result-status")).toHaveText("فعال");
  await owner.getByTestId("grant-result-close").click();
  await owner.getByTestId("grant-open").click();
  await owner.getByTestId("grant-user").selectOption({ label: `تأییدکننده ساختگی (${SYN_LABEL}) (${APPROVER})` });
  await owner.getByTestId("grant-role").selectOption({ label: "تأییدکننده درخواست‌ها (workflow_approver)" });
  await expect(owner.getByTestId("grant-needs-second")).toBeVisible();
  await owner.getByTestId("grant-reason").fill("نخستین تأییدکننده ساختگی");
  await owner.getByTestId("grant-submit").click();
  await answerStepUp(owner, totp, 1500);
  await expect(owner.getByTestId("grant-result-status")).toHaveText("در انتظار تأیید نفر دوم");
  await owner.getByTestId("grant-result-close").click();
  // self-assignment needs an explicit confirmation
  await owner.getByTestId("grant-open").click();
  await owner.getByTestId("grant-user").selectOption({ label: `مالک ساختگی (${SYN_LABEL}) (${OWNER_USERNAME})` });
  await expect(owner.getByTestId("grant-self")).toBeVisible();
  await expect(owner.getByTestId("grant-submit")).toBeDisabled();
  await owner.getByTestId("grant-self-confirm").check();
  await expect(owner.getByTestId("grant-submit")).toBeEnabled();
  await owner.keyboard.press("Escape");
  await expect(owner.getByTestId("grant-dialog")).toBeHidden();
  await expect(owner.getByTestId("assignments-table")).toContainText("در انتظار تأیید نفر دوم");
  await expectNoAxeViolations(owner);
  await screenshots(owner, "security-assignments", async () => {
    await expect(owner.getByTestId("assignments-table")).toBeVisible();
  });
  await owner.getByTestId("tab-roles").click();
  await owner.getByTestId("role-open-owner_admin").click();
  await expect(owner.getByTestId("role-perms-owner_admin")).toContainText("platform.workflow.approval.decide"); // DEC-056
  await screenshots(owner, "security-roles", async () => {
    await expect(owner.getByTestId("roles-table")).toBeVisible();
  });
});

test("page 39: own request is not decided normally; DEC-055 bootstrap approval with reason", async () => {
  await go(owner, "/work", "page-work");
  // to_decide: the owner's own request is not in his decision inbox (maker != checker)
  await expect(owner.getByTestId("state-empty")).toBeVisible();
  await owner.getByTestId("approval-inbox").selectOption("requested_by_me");
  const card = owner.getByTestId("approval-card").first();
  await expect(card).toContainText("انتساب نقش دارای حق تأیید");
  await expectNoAxeViolations(owner);
  await screenshots(owner, "work-approvals", async () => {
    await expect(owner.getByTestId("approvals-list")).toBeVisible();
  });
  await card.getByTestId("approval-open").click();
  await expect(owner.getByTestId("approval-approve")).toHaveCount(0);
  await owner.getByTestId("approval-bootstrap").click();
  await owner.getByTestId("reason-input").fill("نخستین تأییدکننده درخواست‌ها (DEC-055، ساختگی)");
  await owner.getByTestId("reason-submit").click();
  await answerStepUp(owner, totp, 2500);
  await expect(owner.getByTestId("approval-actions")).toBeHidden();
  await owner.getByTestId("approval-status").selectOption("APPROVED");
  await expect(owner.getByTestId("approval-card").first()).toContainText("تأیید اولیه مالک (DEC-055)");
  // role-sensitive: the matrix gives owner_admin no platform.workflow.task.read, so there is no task tab
  await expect(owner.getByTestId("tab-tasks")).toHaveCount(0);
});

test("page 42: OWNER_POLICY value published by the owner in one step", async () => {
  await go(owner, "/parameters", "page-parameters");
  await expect(owner.getByTestId("parameters-table")).toBeVisible();
  await screenshots(owner, "parameters", async () => {
    await expect(owner.getByTestId("parameters-table")).toBeVisible();
  });
  await owner.getByTestId("param-open-password_initial_validity_hours").click();
  await expect(owner.getByTestId("param-class-hint")).toContainText("سیاست مالک");
  await owner.getByTestId("param-propose-open").click();
  await owner.getByTestId("param-value").fill("72");
  await owner.getByTestId("param-reason").fill("تأیید دوباره مقدار مصوب DEC-051 (ساختگی)");
  await owner.getByTestId("param-propose-submit").click();
  await answerStepUp(owner, totp, 2500);
  await expect(owner.getByTestId("param-propose-form")).toBeHidden();
  await expect(owner.getByTestId("param-values")).toContainText("منتشرشده");
  await expect(owner.getByTestId("param-values")).toContainText("جایگزین‌شده"); // the seeded value is superseded
  await expectNoAxeViolations(owner);
  await screenshots(owner, "parameter-detail", async () => {
    await expect(owner.getByTestId("parameter-detail")).toBeVisible();
  });
});

test("page 36: health counters, audit integrity, protected job not cancellable, safe cancel with reason", async () => {
  await go(owner, "/ops", "page-ops");
  await expect(owner.getByTestId("health-panel")).toContainText("پایگاه داده");
  await expect(owner.getByTestId("integrity-status")).toHaveText("سالم");
  await expect(owner.getByTestId("job-db_backup").getByTestId("job-not-cancellable")).toContainText("محافظت‌شده");
  await expectNoAxeViolations(owner);
  await screenshots(owner, "ops", async () => {
    await expect(owner.getByTestId("jobs-table")).toBeVisible();
  });
  const queued = owner.getByTestId("job-session_expiry_sweep");
  await queued.getByTestId("job-cancel").click();
  await owner.getByTestId("reason-input").fill("لغو امن ساختگی E2E");
  await owner.getByTestId("reason-submit").click();
  await answerStepUp(owner, totp, 2500);
  await expect(owner.getByTestId("job-cancel-dialog")).toBeHidden();
  await expect(owner.getByTestId("job-session_expiry_sweep")).toContainText("لغوشده");
});

test("document controller: first login, role-sensitive nav, server-side 403, upload into quarantine", async ({ browser }) => {
  const [ctx, page] = await newPage(browser);
  await go(page, "/", "login");
  await page.getByTestId("login-username").fill(DOCCTL);
  await page.getByTestId("login-password").fill(docctlOneTime);
  await page.getByTestId("login-submit").click();
  await page.getByTestId("pw-current").fill(docctlOneTime);
  await page.getByTestId("pw-new").fill(SYN_PW_DOCCTL_NEW);
  await page.getByTestId("pw-repeat").fill(SYN_PW_DOCCTL_NEW);
  await page.getByTestId("pw-submit").click();
  await expect(page.getByTestId("page-home")).toBeVisible();
  const nav = page.getByTestId("main-nav");
  await expect(nav).toContainText("اسناد");
  await expect(nav).not.toContainText("امنیت و کاربران");
  await expect(nav).not.toContainText("سلامت سامانه و Job");
  // hiding is cosmetic: the server refuses the call itself
  const res = await page.request.get("/api/v1/admin/users");
  expect(res.status()).toBe(403);
  await go(page, "/security", "page-security");
  await expect(page.getByTestId("state-forbidden")).toBeVisible();
  await screenshots(page, "forbidden", async () => {
    await expect(page.getByTestId("state-forbidden")).toBeVisible();
  });

  await go(page, "/documents", "page-documents");
  await expect(page.getByTestId("state-empty")).toBeVisible();
  await page.getByTestId("doc-create-open").click();
  await page.getByTestId("doc-type").fill("syn_drawing");
  await page.getByTestId("doc-title").fill(`نقشه ساختگی (${SYN_LABEL})`);
  await page.getByTestId("doc-create-submit").click();
  await expect(page.getByTestId("document-detail")).toBeVisible();
  await page.getByTestId("upload-file").setInputFiles({ name: "syn-sheet.pdf", mimeType: "application/pdf", buffer: PDF });
  await page.getByTestId("upload-note").fill("نسخه اول ساختگی");
  await page.getByTestId("upload-submit").click();
  await expect(page.getByTestId("upload-done")).toContainText("قرنطینه");
  const rev = page.getByTestId("revision-1");
  await expect(rev.getByTestId("scan-status")).toContainText("قرنطینه");
  await expect(rev.getByTestId("download-disabled")).toBeDisabled();
  // a disallowed type is refused by the server (415), never stored
  await page.getByTestId("upload-file").setInputFiles({ name: "tool.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZsynthetic") });
  await page.getByTestId("upload-submit").click();
  await expect(page.getByTestId("action-error-code")).toHaveText("FILE_TYPE_NOT_ALLOWED");
  await expectNoAxeViolations(page);
  await screenshots(page, "document-detail", async () => {
    await expect(page.getByTestId("revisions-table")).toBeVisible();
  });
  await go(page, "/documents", "page-documents");
  await screenshots(page, "documents", async () => {
    await expect(page.getByTestId("documents-table")).toBeVisible();
  });

  // mobile navigation: the menu toggle exposes aria-expanded
  await page.setViewportSize({ width: 390, height: 844 });
  const toggle = page.getByTestId("nav-toggle");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(nav).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });

  // my sessions, then the session ends (cookie gone) -> login screen with a notice
  await go(page, "/me/sessions", "page-sessions");
  await expect(page.getByTestId("session-current")).toBeVisible();
  await screenshots(page, "my-sessions", async () => {
    await expect(page.getByTestId("sessions-list")).toBeVisible();
  });
  await ctx.clearCookies({ name: "aleekhan_session" });
  await page.goto("/#/documents");
  await expect(page.getByTestId("login")).toBeVisible();
  await ctx.close();
});

test("logout ends the owner's session", async () => {
  await go(owner, "/", "page-home");
  await owner.getByTestId("logout").click();
  await expect(owner.getByTestId("login-notice")).toContainText("خارج شدید");
  const res = await owner.request.get("/api/v1/me");
  expect(res.status()).toBe(401);
});
