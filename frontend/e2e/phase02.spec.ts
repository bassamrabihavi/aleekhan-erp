// PHASE_02 / 02.5 E2E against the real stack (scripts/e2e.sh: Django runserver + throw-away PostgreSQL DB + Vite
// proxy). No API mocking. Serial: synthetic people (one per DEC-057 role) are seeded on the console
// (phase02-helpers.ts), then the full flow runs through the UI with distinct people (maker-checker):
//   code rule approve + activate (inbox) -> product / style / revision -> code preview + issue -> customer
//   (duplicate-name warning) + brand -> order wizard -> validate -> confirm (serial) -> serial center (pages 1/2)
//   -> due-date change request -> commercial decision -> planning decision -> apply (version 2, snapshot 2)
//   -> role views (viewer read-only + masked representative, employee forbidden, server 403).
import { expect, test, type Page } from "@playwright/test";

import { answerStepUp, expectNoAxeViolations, SYN_LABEL } from "./phase01-helpers";
import { login, seedPhase02, shots, type Seed, type Session } from "./phase02-helpers";

test.describe.configure({ mode: "serial" });
test.setTimeout(300_000);

const RUN = Date.now().toString(36).slice(-5);
const CUSTOMER = `مشتری ساختگی ${RUN} (${SYN_LABEL})`;
const PO = `PO-SYN-${RUN}`;
const REP = "نماینده ساختگی";
let seed: Seed;
const s: Partial<Record<"co" | "cm" | "po" | "pds" | "cra", Session>> = {};
let orderUrl = "";
let serialUrl = "";
let changeUrl = "";
let issuedCode = "";

function who(k: "co" | "cm" | "po" | "pds" | "cra"): Session {
  const x = s[k];
  if (!x) throw new Error(`${k} not logged in`);
  return x;
}

async function go(page: Page, hash: string, testId: string): Promise<void> {
  await page.goto(`/#${hash}`);
  await expect(page.getByTestId(testId)).toBeVisible();
}

test.beforeAll(() => {
  seed = seedPhase02(RUN);
});

test.afterAll(async () => {
  for (const x of Object.values(s)) await x.ctx.close();
});

test("code rule: approver sees it in the inbox, opens it, approves (fresh MFA) and activates; maker cannot", async ({ browser }) => {
  s.pds = await login(browser, seed.pds);
  const pds = who("pds").page;
  await go(pds, `/code-rules/${seed.rule_revision_id}`, "rule-detail");
  await expect(pds.getByTestId("rule-status")).toContainText("در بازبینی");
  await expect(pds.getByTestId("rule-approve")).toHaveCount(0); // the maker never approves (and has no approve right)

  s.cra = await login(browser, seed.cra);
  const cra = who("cra").page;
  await expect(cra.getByTestId("main-nav")).toContainText("کارها و تأییدها");
  await go(cra, "/work", "page-work");
  const item = cra.getByTestId("decision-CODE_RULE_APPROVE");
  await expect(item).toBeVisible();
  await expectNoAxeViolations(cra);
  await shots(cra, "inbox-decisions", async () => {
    await expect(item).toBeVisible();
  });
  await item.getByTestId("decision-open").click();
  await expect(cra.getByTestId("golden-summary")).toContainText("۴۰");
  await expectNoAxeViolations(cra);
  await shots(cra, "code-rule-review", async () => {
    await expect(cra.getByTestId("rule-detail")).toBeVisible();
  });
  await cra.getByTestId("rule-approve").click();
  await cra.getByTestId("reason-input").fill("تأیید ساختگی E2E");
  await cra.getByTestId("reason-submit").click();
  await answerStepUp(cra, who("cra").totp, 3000);
  await expect(cra.getByTestId("rule-status")).toContainText("تأییدشده");
  await cra.getByTestId("rule-activate").click();
  await cra.getByTestId("reason-input").fill("فعال‌سازی ساختگی E2E");
  await cra.getByTestId("reason-submit").click();
  await answerStepUp(cra, who("cra").totp, 3000);
  await expect(cra.getByTestId("rule-status")).toContainText("فعال");
});

test("page 4: product (belt fields only for belts), style with colour, activate, code preview + issue (MFA)", async () => {
  const pds = who("pds").page;
  await go(pds, "/products", "page-products");
  await expect(pds.getByTestId("code-check")).toBeVisible();
  // 14-digit check: Persian digits are never converted
  await pds.getByTestId("code-check-input").fill("۰۲۹۷۰۷۹۰۰۱۰۰۰۱");
  await pds.getByTestId("code-check-submit").click();
  await expect(pds.getByTestId("code-check-reasons")).toContainText("رقم فارسی");
  await pds.getByTestId("product-create-open").click();
  const beltOption = pds.getByTestId("product-type").locator("option", { hasText: "(96)" });
  await pds.getByTestId("product-type").selectOption({ value: (await beltOption.getAttribute("value")) ?? "" });
  await expect(pds.getByTestId("belt-fields")).toBeVisible();
  const bagOption = pds.getByTestId("product-type").locator("option", { hasText: "(97)" });
  await pds.getByTestId("product-type").selectOption({ value: (await bagOption.getAttribute("value")) ?? "" });
  await expect(pds.getByTestId("belt-fields")).toHaveCount(0);
  await pds.getByTestId("product-name").fill(`کیف اداری ساختگی ${RUN}`);
  await pds.getByTestId("product-submit").click();
  await expect(pds.getByTestId("product-detail")).toBeVisible();
  await expect(pds.getByTestId("product-no")).toHaveText(/^[0-9]{4}$/);
  await pds.getByTestId("product-activate").click();
  await pds.getByTestId("reason-input").fill("فعال‌سازی ساختگی");
  await pds.getByTestId("reason-submit").click();
  await expect(pds.getByTestId("product-status")).toContainText("فعال");
  // style with initial attributes (revision 1 DRAFT)
  await pds.getByTestId("style-create-open").click();
  await pds.getByTestId("style-category").selectOption({ index: 1 });
  await pds.getByTestId("style-name").fill(`استایل ساختگی ${RUN}`);
  await pds.getByTestId("attr-colour_fa").fill("مشکی ساختگی");
  await pds.getByTestId("attr-main_material_fa").fill("چرم ساختگی");
  await pds.getByTestId("style-submit").click();
  await expect(pds.getByTestId("style-detail")).toBeVisible();
  await expect(pds.getByTestId("style-detail")).toContainText("0001"); // style 0000 is never issued
  await pds.getByTestId("style-activate").click();
  await pds.getByTestId("reason-input").fill("فعال‌سازی ساختگی");
  await pds.getByTestId("reason-submit").click();
  await expect(pds.getByTestId("style-status")).toContainText("فعال");
  await pds.getByTestId("revision-activate").click();
  await pds.getByTestId("reason-input").fill("فعال‌سازی نسخه ساختگی");
  await pds.getByTestId("reason-submit").click();
  await expect(pds.getByTestId("revisions-table")).toContainText("فعال");
  // code
  await pds.getByTestId("code-preview").click();
  await expect(pds.getByTestId("code-preview-value")).toContainText(/029707[0-9]{4}0001/);
  await pds.getByTestId("code-issue").click();
  await answerStepUp(pds, who("pds").totp, 3000);
  const code = pds.getByTestId("issued-code");
  await expect(code).toHaveText(/^029707[0-9]{4}0001$/);
  issuedCode = (await code.innerText()).trim();
  expect(issuedCode).toHaveLength(14);
  await expect(code).toHaveAttribute("dir", "ltr");
  await expect(pds.getByTestId("style-codes")).toContainText("منتظر ثبت دستی در راهکاران");
  await expectNoAxeViolations(pds);
  await shots(pds, "page04-product-style", async () => {
    await expect(pds.getByTestId("style-detail")).toBeVisible();
  });
});

test("customers: create (CU- number), duplicate name needs acknowledgement, brand", async ({ browser }) => {
  s.co = await login(browser, seed.co);
  const co = who("co").page;
  await go(co, "/customers", "page-customers");
  for (const attempt of [1, 2]) {
    await co.getByTestId("customer-create-open").click();
    await co.getByTestId("customer-name").fill(CUSTOMER);
    await co.getByTestId("customer-submit").click();
    if (attempt === 2) {
      await expect(co.getByTestId("customer-dup-warning")).toBeVisible();
      await expect(co.getByTestId("customer-submit")).toBeDisabled();
      await co.getByTestId("customer-dup-ack").check();
      await co.getByTestId("customer-submit").click();
    }
    await expect(co.getByTestId("customer-dialog")).toBeHidden();
    await expect(co.getByTestId("customer-detail")).toBeVisible();
    await expect(co.getByTestId("customer-no")).toHaveText(/^CU-[0-9]{4}-[0-9]{6,}$/);
  }
  await expect(co.getByTestId("customer-detail").getByTestId("state-empty")).toBeVisible(); // brands loaded
  await co.getByTestId("brand-name").fill(`برند ساختگی ${RUN}`);
  await expect(co.getByTestId("brand-submit")).toBeEnabled();
  await co.getByTestId("brand-submit").click();
  await expect(co.getByTestId("brands-list")).toContainText(`برند ساختگی ${RUN}`);
  await expectNoAxeViolations(co);
  await shots(co, "customers", async () => {
    await expect(co.getByTestId("customer-detail")).toBeVisible();
  });
});

test("page 29: order wizard (Jalali dates), line with the issued code, validate; the creator cannot confirm", async () => {
  const co = who("co").page;
  await go(co, "/orders/new", "order-wizard");
  await co.getByTestId("wiz-customer-search").fill(RUN);
  await co.getByTestId("wiz-customer").selectOption({ index: 1 });
  await co.getByTestId("wiz-brand").selectOption({ index: 1 });
  await co.getByTestId("wiz-type").selectOption("series_production");
  await co.getByTestId("wiz-po").fill(PO);
  await co.getByTestId("wiz-rep").fill(REP);
  await co.getByTestId("wiz-due").fill("1406/01/20");
  await expectNoAxeViolations(co);
  await shots(co, "page29-wizard-step1", async () => {
    await expect(co.getByTestId("order-wizard")).toBeVisible();
  });
  await co.getByTestId("wiz-create").click();
  await expect(co.getByTestId("order-detail")).toBeVisible();
  await expect(co.getByTestId("order-no")).toHaveText(/^SO-[0-9]{4}-[0-9]{6,}$/);
  await expect(co.getByTestId("order-due")).toContainText("۱۴۰۶");
  orderUrl = co.url();
  // line: product -> style -> active revision -> issued code -> quantity
  await co.getByTestId("line-product-search").fill(RUN);
  await co.getByTestId("line-product").selectOption({ index: 1 });
  await co.getByTestId("line-style").selectOption({ index: 1 });
  await expect(co.getByTestId("line-revision")).toContainText("مشکی ساختگی");
  await co.getByTestId("line-code").selectOption({ label: issuedCode });
  await co.getByTestId("line-qty").fill("40");
  await co.getByTestId("line-add").click();
  await expect(co.getByTestId("lines-table")).toContainText(issuedCode);
  await expectNoAxeViolations(co);
  await shots(co, "page29-order-draft", async () => {
    await expect(co.getByTestId("lines-table")).toBeVisible();
  });
  await co.getByTestId("order-validate").click();
  await co.getByTestId("validate-submit").click();
  await expect(co.getByTestId("order-status")).toContainText("بررسی‌شده");
  await expect(co.getByTestId("order-confirm")).toHaveCount(0); // no confirm right, and never the creator
});

test("duplicate PO: a second order with the same PO must acknowledge the warning", async () => {
  const co = who("co").page;
  await go(co, "/orders/new", "order-wizard");
  await co.getByTestId("wiz-customer-search").fill(RUN);
  await co.getByTestId("wiz-customer").selectOption({ index: 1 });
  await co.getByTestId("wiz-po").fill(PO);
  await co.getByTestId("wiz-create").click();
  await expect(co.getByTestId("order-detail")).toBeVisible();
  await co.getByTestId("line-product-search").fill(RUN);
  await co.getByTestId("line-product").selectOption({ index: 1 });
  await co.getByTestId("line-style").selectOption({ index: 1 });
  await co.getByTestId("line-qty").fill("5");
  await co.getByTestId("line-add").click();
  await expect(co.getByTestId("lines-table")).toBeVisible();
  await co.getByTestId("order-validate").click();
  await co.getByTestId("validate-submit").click();
  await expect(co.getByTestId("po-dup-warning")).toBeVisible();
  await expect(co.getByTestId("validate-submit")).toBeDisabled();
  await co.getByTestId("po-dup-ack").check();
  await co.getByTestId("validate-submit").click();
  await expect(co.getByTestId("order-status")).toContainText("بررسی‌شده");
});

test("planning confirms from the inbox (fresh MFA): the serial is shown; pages 1 and 2", async ({ browser }) => {
  s.po = await login(browser, seed.po);
  const po = who("po").page;
  await go(po, "/work", "page-work");
  const orderId = orderUrl.split("/").pop() ?? "";
  const card = po.getByTestId("decisions-list").locator(`a[href="#/orders/${orderId}"]`);
  await expect(card).toBeVisible();
  await card.click();
  await expect(po.getByTestId("order-detail")).toBeVisible();
  await expect(po.getByTestId("rep-value")).toHaveText(REP); // planning holds customer.read: name visible (audited)
  await po.getByTestId("order-confirm").click();
  await po.getByTestId("confirm-submit").click();
  await answerStepUp(po, who("po").totp, 3000);
  await expect(po.getByTestId("order-status")).toContainText("تأییدشده");
  const serialLink = po.getByTestId("line-serial").first();
  await expect(serialLink).toHaveText(/^[1-9][0-9]*$/);
  await expect(po.getByTestId("order-version")).toContainText("۱");
  await shots(po, "page29-order-confirmed", async () => {
    await expect(po.getByTestId("lines-table")).toBeVisible();
  });
  await serialLink.click();
  await expect(po.getByTestId("serial-header")).toBeVisible();
  serialUrl = po.url();
  await expect(po.getByTestId("serial-code")).toHaveText(issuedCode);
  await expect(po.getByTestId("serial-qty")).toContainText("۴۰");
  const later = po.getByTestId("later-section");
  expect(await later.count()).toBeGreaterThanOrEqual(6);
  for (const t of await later.locator(".later__text").allInnerTexts()) expect(t).toBe("در دست ساخت — به داده واقعی متصل نیست");
  await expectNoAxeViolations(po);
  await shots(po, "page01-serial-summary", async () => {
    await expect(po.getByTestId("serial-summary")).toBeVisible();
  });
  // keyboard: RTL tabs (ArrowLeft = next)
  await po.getByTestId("tab-summary").focus();
  await po.keyboard.press("ArrowLeft");
  await expect(po.getByTestId("tab-order")).toBeFocused();
  await expect(po.getByTestId("serial-order")).toBeVisible();
  await expect(po.getByTestId("serial-snapshots")).toContainText(issuedCode);
  await expect(po.getByTestId("serial-timeline")).toContainText("سریال تخصیص یافت");
  await expectNoAxeViolations(po);
  await shots(po, "page02-serial-order", async () => {
    await expect(po.getByTestId("serial-order")).toBeVisible();
  });
});

test("page 33: due-date change -> commercial decision -> planning decision -> apply (version 2)", async ({ browser }) => {
  const co = who("co").page;
  await co.goto(orderUrl);
  await co.getByTestId("order-request-change").click();
  await expect(co.getByTestId("change-new")).toBeVisible();
  await co.getByTestId("change-kind").selectOption("DUE_DATE_CHANGE");
  await co.getByTestId("change-due").fill("1406/02/10");
  await co.getByTestId("change-reason").fill("درخواست ساختگی مشتری برای تاریخ دیرتر");
  await co.getByTestId("change-submit").click();
  await expect(co.getByTestId("change-detail")).toBeVisible();
  await expect(co.getByTestId("cr-no")).toHaveText(/^CR-[0-9]{4}-[0-9]{6,}$/);
  await expect(co.getByTestId("cr-own")).toBeVisible();
  await expect(co.getByTestId("cr-approve")).toHaveCount(0);
  changeUrl = co.url();
  const crId = changeUrl.split("/").pop() ?? "";

  s.cm = await login(browser, seed.cm);
  const cm = who("cm").page;
  await go(cm, "/work", "page-work");
  await cm.getByTestId("decisions-list").locator(`a[href="#/changes/${crId}"]`).click();
  await expect(cm.getByTestId("cr-before-after")).toContainText("۱۴۰۶");
  await expectNoAxeViolations(cm);
  await shots(cm, "page33-change-decide", async () => {
    await expect(cm.getByTestId("change-detail")).toBeVisible();
  });
  await expect(cm.getByTestId("cr-plan-approve")).toHaveCount(0);
  await cm.getByTestId("cr-approve").click();
  await cm.getByTestId("cr-decision-submit").click();
  await answerStepUp(cm, who("cm").totp, 3000);
  await expect(cm.getByTestId("cr-status")).toContainText("تأییدشده");

  const po = who("po").page;
  await go(po, "/work", "page-work");
  await po.getByTestId("decisions-list").locator(`a[href="#/changes/${crId}"]`).click();
  await po.getByTestId("cr-plan-approve").click();
  await po.getByTestId("cr-decision-submit").click();
  await answerStepUp(po, who("po").totp, 3000);
  await expect(po.getByTestId("cr-planning-gate")).toContainText("تأیید");
  await po.getByTestId("cr-apply").click();
  await po.getByTestId("cr-decision-submit").click();
  await answerStepUp(po, who("po").totp, 1500);
  await expect(po.getByTestId("cr-status")).toContainText("اعمال‌شده");
  await expect(po.getByTestId("cr-applied-version")).toContainText("۲");
  await shots(po, "page33-change-applied", async () => {
    await expect(po.getByTestId("change-detail")).toBeVisible();
  });
  await po.goto(serialUrl);
  await po.getByTestId("tab-order").click();
  await expect(po.getByTestId("serial-snapshots").locator("li")).toHaveCount(2);
  await expect(po.getByTestId("serial-versions").locator("li")).toHaveCount(2);
});

test("412: a stale edit shows the data-changed state", async () => {
  const co = who("co").page;
  // two tabs of the same draft: the second save carries an old If-Match
  await go(co, "/orders/new", "order-wizard");
  await co.getByTestId("wiz-customer-search").fill(RUN);
  await co.getByTestId("wiz-customer").selectOption({ index: 1 });
  await co.getByTestId("wiz-create").click();
  await expect(co.getByTestId("order-detail")).toBeVisible();
  const other = await who("co").ctx.newPage();
  await other.goto(co.url());
  await expect(other.getByTestId("order-detail")).toBeVisible();
  await co.getByTestId("order-edit").click();
  await co.getByTestId("edit-po").fill(`PO-SYN-EDIT-${RUN}`);
  await co.getByTestId("edit-submit").click();
  await expect(co.getByTestId("order-edit-dialog")).toBeHidden();
  await other.getByTestId("order-edit").click();
  await other.getByTestId("edit-po").fill(`PO-SYN-STALE-${RUN}`);
  await other.getByTestId("edit-submit").click();
  await expect(other.getByTestId("version-conflict")).toBeVisible();
  await shots(other, "state-version-conflict", async () => {
    await expect(other.getByTestId("version-conflict")).toBeVisible();
  });
  await other.close();
});

test("roles: management viewer read-only with masked representative; employee has no PHASE_02 access", async ({ browser }) => {
  const viewer = await login(browser, seed.viewer);
  const v = viewer.page;
  await expect(v.getByTestId("main-nav")).toContainText("مرکز کنترل سریال");
  await v.goto(serialUrl);
  await v.getByTestId("tab-order").click();
  await expect(v.getByTestId("rep-masked")).toBeVisible();
  await v.goto(orderUrl);
  await expect(v.getByTestId("order-detail")).toBeVisible();
  await expect(v.getByTestId("order-request-change")).toHaveCount(0);
  await expect(v.getByTestId("order-release")).toHaveCount(0);
  await go(v, "/orders", "page-orders");
  await expect(v.getByTestId("order-new")).toHaveCount(0);
  await shots(v, "page29-orders-viewer", async () => {
    await expect(v.getByTestId("orders-table")).toBeVisible();
  });
  const write = await v.request.post("/api/v1/commercial/customer-orders", { data: {}, headers: { "Idempotency-Key": crypto.randomUUID() } });
  expect([401, 403]).toContain(write.status());
  await viewer.ctx.close();

  const emp = await login(browser, seed.emp);
  const e = emp.page;
  await expect(e.getByTestId("main-nav")).not.toContainText("مرکز کنترل سریال");
  await expect(e.getByTestId("main-nav")).not.toContainText("ثبت سفارش");
  for (const [hash, id] of [["/serials", "page-serials"], ["/orders", "page-orders"], ["/products", "page-products"], ["/changes", "page-changes"]] as const) {
    await go(e, hash, id);
    await expect(e.getByTestId("state-forbidden")).toBeVisible();
  }
  await shots(e, "forbidden-employee", async () => {
    await expect(e.getByTestId("state-forbidden")).toBeVisible();
  });
  const res = await e.request.get("/api/v1/identity/serials");
  expect(res.status()).toBe(403);
  await emp.ctx.close();
});

test("empty / error states and the synthetic-data banner on PHASE_02 pages [simulated failure]", async () => {
  const po = who("po").page;
  await go(po, "/changes", "page-changes");
  await expect(po.getByTestId("env-banner")).toContainText(SYN_LABEL);
  await po.getByTestId("change-status-filter").selectOption("EXPIRED");
  await expect(po.getByTestId("state-empty")).toBeVisible();
  await shots(po, "page33-empty", async () => {
    await expect(po.getByTestId("state-empty")).toBeVisible();
  });
  // simulated failure (named): the API answers 503 without a problem body -> network error state with retry
  await po.route("**/api/v1/identity/serials?*", (route) => route.fulfill({ status: 503, body: "down" }));
  await go(po, "/serials", "page-serials");
  await expect(po.getByTestId("state-error")).toBeVisible();
  await shots(po, "state-error", async () => {
    await expect(po.getByTestId("state-error")).toBeVisible();
  });
  await po.unroute("**/api/v1/identity/serials?*");
});
