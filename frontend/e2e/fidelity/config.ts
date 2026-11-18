// DEC-061 fidelity harness (PHASE_02 / 02.8 rework, REV-0295 measurement): constants and the mockup region map.
//
// The ONE place for the acceptance threshold, the score weights and the widths. The region map below names, per
// page, which mockup element is which region (CSS selector inside the rendered mockup) and which labels are its
// required children. Boxes, children texts, item counts and style references are then EXTRACTED automatically
// from the rendered mockup (fidelity.spec.ts, FIDELITY_EXTRACT=1) into specs/page-XX.json. Pages 1 and 2 have no
// HTML mockup (only the concept PNGs in 01_02_concepts): their specs are hand-authored (README.md).
import path from "node:path";
import { fileURLToPath } from "node:url";

/** DEC-061: a page is accepted only at >= 95 % at every width. */
export const THRESHOLD = 0.95;
/** Score per width = 0.5 x presence + 0.3 x layout + 0.2 x style. */
export const WEIGHTS = { presence: 0.5, layout: 0.3, style: 0.2 } as const;
/** A region is "in place" when the IoU of its normalised box with the mockup box is at least this. */
export const IOU_MIN = 0.5;
/** A child label counts as present when at least this share of its words occurs in the region text. */
export const LABEL_TOKEN_SHARE = 0.6;
/** Style tolerances. */
export const TOL = { radiusPx: 4, headingRatio: 0.25, paddingPx: 8 } as const;
/**
 * DEC-061 amendment (2026-11-18): a built section that is not a mockup region is allowed only below all mockup
 * content (or in a dialog / a tab that is not the default view). Each visible extra section whose top edge lies above
 * the bottom edge of the lowest mockup region present on the built page costs this share of the TOTAL score, taken
 * from the layout part (layout -= EXTRA_PENALTY / WEIGHTS.layout per section, floored at 0: the cap is the whole
 * layout weight). Reported per width as `extra_above`.
 */
export const EXTRA_PENALTY = 0.05;
/** What counts as a "section / panel" when the built page content is scanned for extra sections (README.md). */
export const EXTRA_SECTION_SELECTOR = "section, aside, article, form, table, .panel, .card, [role=region], [role=tabpanel]";
/** Elements that are never extra sections (a dialog is not the default view; fixed overlays are not page content). */
export const EXTRA_IGNORE_SELECTOR = "dialog, [role=dialog], [role=alertdialog], [aria-modal=true], .dialog-backdrop";
/** Honest placeholder text of a later-phase region (DEC-027 / DEC-061: never mock numbers). */
export const LATER_TEXT = "در دست ساخت";

export const WIDTHS = [1440, 1180, 768, 390] as const;
export type Width = (typeof WIDTHS)[number];
export const HEIGHTS: Record<Width, number> = { 1440: 900, 1180: 820, 768: 1024, 390: 844 };
/** Side-by-side screenshots are saved at these widths only. */
export const SHOT_WIDTHS: readonly Width[] = [1440, 390];

const here = path.dirname(fileURLToPath(import.meta.url));
export const REPO = path.resolve(here, "../../..");
export const SPEC_DIR = path.join(here, "specs");
export const CATALOG = "handoff/08_UI_AND_UX/DESIGN_CATALOG_52";
/** Output (baseline.json, BASELINE.md, shots/). Override with FIDELITY_OUT. */
export const OUT_DIR = process.env.FIDELITY_OUT
  ? path.resolve(process.env.FIDELITY_OUT)
  : path.join(REPO, "reports/phase-02/step-8/fidelity");

export type RegionKind =
  | "header"
  | "actions"
  | "kpis"
  | "filters"
  | "panel"
  | "table"
  | "side-panel"
  | "events"
  | "chart"
  | "tabs"
  | "side-menu"
  | "topbar"
  | "topbar-search"
  | "topbar-date"
  | "topbar-user"
  | "menu-toggle"
  | "bottom-nav";

/** Boxes of "content" regions are relative to the content area (<main>), of "viewport" regions to the page. */
export type Frame = "content" | "viewport";

/** Panel-like kinds whose radius / border / shadow are compared. */
export const PANEL_KINDS: readonly RegionKind[] = ["kpis", "filters", "panel", "table", "side-panel", "events", "chart"];

export interface RegionDef {
  id: string;
  label_fa: string;
  kind: RegionKind;
  frame: Frame;
  /** CSS selector of the region inside the rendered mockup. */
  selector: string;
  /** Selectors (inside the region) whose texts are the required child labels. `sel::own` = own text nodes only. */
  children?: string[];
  /** Child labels added by hand (e.g. a heading that sits just outside the selected element). */
  extra_children?: string[];
  /** Selector of the repeated items (KPI cards, nav links) whose count is required. */
  items?: string;
  /** Data owned by a later phase: an honest «در دست ساخت» / empty state in place is enough. */
  later_phase?: string;
}

export interface MockupDef {
  page: string;
  title_fa: string;
  /** Built route (hash); {placeholders} are filled from the fidelity seed. */
  route: string;
  /** Optional UI step after loading the built route (page 2: open the «سفارش» tab). */
  after_load?: "open-order-tab";
  /** Test id that must be visible on the built page before measuring. */
  ready_testid: string;
  html: string;
  query?: string;
  /** Files whose sha256 is recorded (html + its assets + preview PNGs). */
  files: string[];
  content_selector: string;
  /** Mockup parts deliberately NOT regions (catalogue navigation, demo captions). */
  excluded: string[];
  regions: RegionDef[];
}

const SHELL_04: RegionDef[] = [
  { id: "side-menu", label_fa: "منوی کناری (آیکون‌دار)", kind: "side-menu", frame: "viewport", selector: "aside#sidebar", items: "a.navitem" },
  { id: "topbar", label_fa: "نوار بالا", kind: "topbar", frame: "viewport", selector: "header.toolbar" },
  { id: "topbar-search", label_fa: "جستجوی سراسری", kind: "topbar-search", frame: "viewport", selector: "header.toolbar .topsearch" },
  { id: "topbar-date", label_fa: "تاریخ امروز", kind: "topbar-date", frame: "viewport", selector: "header.toolbar .date" },
  { id: "topbar-user", label_fa: "کاربر", kind: "topbar-user", frame: "viewport", selector: "header.toolbar .avatar" },
  { id: "menu-toggle", label_fa: "دکمه باز کردن منو (موبایل)", kind: "menu-toggle", frame: "viewport", selector: "#mobileToggle" },
];

const SHELL_29_36: RegionDef[] = [
  { id: "side-menu", label_fa: "منوی کناری (آیکون‌دار)", kind: "side-menu", frame: "viewport", selector: "aside#sidebar", items: "#sidenav a" },
  { id: "topbar", label_fa: "نوار بالا", kind: "topbar", frame: "viewport", selector: "header.topbar" },
  { id: "topbar-search", label_fa: "جستجوی سراسری", kind: "topbar-search", frame: "viewport", selector: "header.topbar .globalsearch" },
  { id: "topbar-date", label_fa: "تاریخ امروز", kind: "topbar-date", frame: "viewport", selector: "header.topbar .date" },
  { id: "topbar-user", label_fa: "کاربر", kind: "topbar-user", frame: "viewport", selector: "header.topbar .avatar" },
  { id: "menu-toggle", label_fa: "دکمه باز کردن منو (موبایل)", kind: "menu-toggle", frame: "viewport", selector: "#mobileMenu" },
];

const INTRO_29_36: RegionDef[] = [
  { id: "page-header", label_fa: "سربرگ و عنوان صفحه", kind: "header", frame: "content", selector: "section.pageintro > div:first-child", children: ["h1"] },
  { id: "header-actions", label_fa: "دکمه‌های اقدام صفحه", kind: "actions", frame: "content", selector: "section.pageintro .actionbar", children: ["button"] },
  { id: "kpis", label_fa: "کارت‌های شاخص (KPI)", kind: "kpis", frame: "content", selector: "#dashboard > .kpis", items: ".kpi", children: [".kpi > span"] },
];

const P29_36_FILES = ["index.html", "assets/styles.css", "assets/app.js"].map((f) => `${CATALOG}/29_36_commercial_planning_admin/${f}`);
const P29_36_EXCLUDED = [
  "nav.pagechips (catalogue navigation between mockup pages 29-36, not a page element)",
  ".captionline / footer / .demo badge (catalogue captions: «داده نمایشی»)",
  "#modal / .toast (demo dialogs)",
];

export const MOCKUPS: MockupDef[] = [
  {
    page: "04",
    title_fa: "ردیابی محصولات و استایل‌ها",
    route: "/products/{product_id}/{style_id}",
    ready_testid: "style-detail",
    html: `${CATALOG}/04_product_style/product_style_360.html`,
    files: ["product_style_360.html", "desktop.png", "laptop.png", "tablet.png", "mobile.png"].map((f) => `${CATALOG}/04_product_style/${f}`),
    content_selector: "main.content",
    excluded: ["p.footnote (prototype caption)", "#sel selected-serial hint (interaction demo)", "#mobileRows (mobile duplicate of the serial table, measured through the table region)"],
    regions: [
      ...SHELL_04,
      { id: "page-header", label_fa: "سربرگ و عنوان صفحه", kind: "header", frame: "content", selector: "section.heading > div:first-child", children: ["h2"] },
      { id: "header-actions", label_fa: "دکمه‌های اقدام صفحه", kind: "actions", frame: "content", selector: "section.heading .actions", children: ["button"] },
      { id: "kpis", label_fa: "کارت‌های شاخص (KPI)", kind: "kpis", frame: "content", selector: "section.metrics", items: ".metric", children: [".metric > span"] },
      { id: "filters", label_fa: "نوار فیلتر", kind: "filters", frame: "content", selector: "section.filters", children: ["label"] },
      { id: "product-card", label_fa: "شناسنامه محصول", kind: "panel", frame: "content", selector: ".layout > section.card:nth-of-type(1)", children: [":scope > .cardhd::own", ".info small"] },
      { id: "product-styles", label_fa: "استایل‌های این محصول", kind: "panel", frame: "content", selector: "#styles", extra_children: ["استایل‌های این محصول"] },
      { id: "serial-table", label_fa: "جدول سریال‌های مرتبط", kind: "table", frame: "content", selector: ".layout > section.card:nth-of-type(2)", children: [":scope > .cardhd::own", "th"] },
      { id: "stage-distribution", label_fa: "نمودار توزیع سریال‌ها در چرخه تولید", kind: "chart", frame: "content", selector: ".lower > section.card:nth-of-type(1)", children: [":scope > .cardhd::own", ".barrow label"], later_phase: "PHASE_07" },
      { id: "events", label_fa: "آخرین رخدادهای مرتبط", kind: "events", frame: "content", selector: ".lower > section.card:nth-of-type(2)", children: [":scope > .cardhd::own"], later_phase: "PHASE_07" },
    ],
  },
  {
    page: "29",
    title_fa: "ثبت سفارش و کدگذاری",
    route: "/orders/new",
    ready_testid: "order-wizard",
    html: `${CATALOG}/29_36_commercial_planning_admin/index.html`,
    query: "?page=29",
    files: [...P29_36_FILES, ...["desktop", "laptop", "tablet", "mobile"].map((w) => `${CATALOG}/29_36_commercial_planning_admin/previews/page29_${w}.png`)],
    content_selector: "main.content",
    excluded: P29_36_EXCLUDED,
    regions: [
      ...SHELL_29_36,
      ...INTRO_29_36,
      { id: "order-wizard", label_fa: "فرم مرحله‌ای ثبت سفارش", kind: "panel", frame: "content", selector: "#dashboard > .grid.g2 > section.panel:nth-of-type(1)", children: [".panelhead h2", "label.field > span", ".rowbuttons button"] },
      { id: "wizard-steps", label_fa: "مراحل فرم", kind: "tabs", frame: "content", selector: "#dashboard > .grid.g2 > section.panel:nth-of-type(1) .steps", items: "button.step" },
      { id: "coding-validation", label_fa: "کدگذاری راهکاران و اعتبارسنجی", kind: "table", frame: "content", selector: "#dashboard > .grid.g2 > section.panel:nth-of-type(2)", children: [".panelhead h2", "th"] },
      { id: "similar-styles", label_fa: "بررسی استایل‌های موجود", kind: "table", frame: "content", selector: "#dashboard > .grid.g22 > section.panel:nth-of-type(1)", children: [".panelhead h2", "th"] },
      { id: "pre-checks", label_fa: "کنترل‌های داده پیش از ثبت", kind: "side-panel", frame: "content", selector: "#dashboard > .grid.g22 > section.panel:nth-of-type(2)", children: [".panelhead h2", ".bullet strong"] },
    ],
  },
  {
    page: "33",
    title_fa: "تغییرات سفارش",
    route: "/changes",
    ready_testid: "changes-table",
    html: `${CATALOG}/29_36_commercial_planning_admin/index.html`,
    query: "?page=33",
    files: [...P29_36_FILES, ...["desktop", "laptop", "tablet", "mobile"].map((w) => `${CATALOG}/29_36_commercial_planning_admin/previews/page33_${w}.png`)],
    content_selector: "main.content",
    excluded: [...P29_36_EXCLUDED, "request rows of the list (demo records: CR-2451-03 ...) - only the panel heading is required"],
    regions: [
      ...SHELL_29_36,
      ...INTRO_29_36,
      { id: "change-list", label_fa: "فهرست درخواست‌ها", kind: "table", frame: "content", selector: "#dashboard > .grid.g2 > section.panel:nth-of-type(1)", children: [".panelhead h2"] },
      { id: "change-compare", label_fa: "مقایسه قبل و بعد و گیت‌های تأیید", kind: "side-panel", frame: "content", selector: "#dashboard > .grid.g2 > section.panel:nth-of-type(2)", children: [".panelhead h2", ".tile h3", ".parttitle", ".bullet strong"] },
      { id: "revision-effectivity", label_fa: "قاعده اثرپذیری Revision بر مقدار", kind: "panel", frame: "content", selector: "#dashboard > section.panel", children: [".panelhead h2"], later_phase: "PHASE_04 / PHASE_05" },
    ],
  },
];

/** Hand-authored pages (concept PNGs only). Their spec files are never overwritten by the extractor. */
export const HAND_PAGES = [
  { page: "01", title_fa: "مرکز کنترل سریال — نمای خلاصه", route: "/serials/{serial_id}", ready_testid: "serial-summary" },
  { page: "02", title_fa: "مرکز کنترل سریال — تب سفارش", route: "/serials/{serial_id}", ready_testid: "serial-order", after_load: "open-order-tab" as const },
] as const;
