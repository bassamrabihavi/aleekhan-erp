import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState, type ReactNode } from "react";

import { g, get, PERM } from "../api/phase02";
import logoUrl from "../assets/brand/aleekhan-logo.png";
import { useAuth } from "../auth/context";
import { useOnline } from "../lib/hooks";
import { formatJalaliDate, todayTehranIso } from "../lib/jalali";
import { ENVIRONMENT_LABELS } from "../lib/labels";
import { NAV, useVersion, type NavItem } from "../lib/nav";
import { navigate, useRoute } from "../lib/router";
import { Icon } from "./Icon";

/** The most specific navigation item for the route ("/orders/new" beats "/orders"). */
function activePath(route: string, items: readonly NavItem[]): string | null {
  let best: string | null = null;
  for (const n of items) {
    const hit = n.path === "/" ? route === "/" : route === n.path || route.startsWith(`${n.path}/`);
    if (hit && (best === null || n.path.length > best.length)) best = n.path;
  }
  return best;
}

const PIN_KEY = "aleekhan.nav.pinned";

function readPinned(): boolean {
  try {
    return window.localStorage.getItem(PIN_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Page frame (REV-0295 / DEC-061, catalogue shell of pages 4 and 29-36): skip link; icon side menu on the right
 * (hover or keyboard focus expands it, the pin keeps it open; on tablets the menu button expands it, on phones it
 * is a drawer); top bar with the brand, the page title, the global search over PHASE_02 records, today's Jalali
 * date, the work inbox and the user menu; environment and offline banners; main; footer; on phones a bottom
 * navigation. Navigation items the matrix denies are hidden (cosmetic only - the server re-checks every call).
 */
export function AppShell({ children, authenticated = true }: { children: ReactNode; authenticated?: boolean }) {
  const online = useOnline();
  const version = useVersion();
  const v = version.data;
  const route = useRoute();
  const { me, can, canAny, logout, status } = useAuth();
  // a menu is open for the route it was opened on: navigating closes it (no state reset in an effect)
  const [menuAt, setMenuAt] = useState<string | null>(null);
  const [pinned, setPinned] = useState(readPinned);
  const [userAt, setUserAt] = useState<string | null>(null);
  const menuOpen = menuAt === route;
  const userOpen = userAt === route;
  const setMenuOpen = (open: boolean | ((o: boolean) => boolean)) => {
    const next = typeof open === "function" ? open(menuOpen) : open;
    setMenuAt(next ? route : null);
  };
  const setUserOpen = (open: boolean | ((o: boolean) => boolean)) => {
    const next = typeof open === "function" ? open(userOpen) : open;
    setUserAt(next ? route : null);
  };
  const showNav = authenticated && status === "ready";
  const items = NAV.filter((n) => !n.anyOf || canAny(n.anyOf));
  const active = activePath(route, items);
  const title = items.find((n) => n.path === active)?.label ?? null;

  useEffect(() => {
    if (!menuOpen && !userOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuAt(null);
        setUserAt(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen, userOpen]);

  const togglePin = () => {
    setPinned((p) => {
      try {
        window.localStorage.setItem(PIN_KEY, p ? "0" : "1");
      } catch {
        /* private mode: the pin lasts for this page only */
      }
      return !p;
    });
  };

  const shellClass = ["shell", showNav ? "shell--nav" : "", showNav && pinned ? "shell--pinned" : "", menuOpen ? "shell--menu-open" : ""].filter(Boolean).join(" ");

  return (
    <div className={shellClass}>
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>
        رفتن به محتوای اصلی
      </a>
      {showNav ? (
        <>
          <nav id="main-nav" className={menuOpen ? "rail rail--open" : "rail"} aria-label="بخش‌های سامانه" data-testid="main-nav" data-fid="side-menu">
            <div className="rail__head">
              <button
                type="button"
                className="iconbtn rail__pin"
                aria-pressed={pinned}
                onClick={togglePin}
                title={pinned ? "باز کردن ثابت منو" : "ثابت‌کردن منو"}
                data-testid="nav-pin"
              >
                <Icon name="pin" size={18} />
                <span className="sr-only">{pinned ? "منو ثابت است؛ برای جمع شدن بزنید" : "ثابت‌کردن منو"}</span>
              </button>
              <span className="rail__title">منوی سامانه</span>
            </div>
            <ul className="rail__list">
              {items.map((n) => (
                <li key={n.path} data-fid-item>
                  <a
                    href={`#${n.path}`}
                    className="rail__link"
                    aria-current={n.path === active ? "page" : undefined}
                    title={n.label}
                    onClick={() => {
                      setMenuOpen(false);
                    }}
                    data-testid={`nav-${n.path === "/" ? "home" : n.path.slice(1).replace("/", "-")}`}
                  >
                    <Icon name={n.icon} className="rail__icon" />
                    <span className="rail__label">{n.label}</span>
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          {menuOpen ? <button type="button" className="scrim" aria-label="بستن منو" tabIndex={-1} onClick={() => { setMenuOpen(false); }} /> : null}
          <button
            type="button"
            className="iconbtn nav-toggle"
            aria-expanded={menuOpen}
            aria-controls="main-nav"
            onClick={() => {
              setMenuOpen((o) => !o);
            }}
            data-testid="nav-toggle"
            data-fid="menu-toggle"
          >
            <Icon name={menuOpen ? "close" : "menu"} size={18} />
            <span className="sr-only">منو</span>
          </button>
        </>
      ) : null}
      <div className="app">
        <header className="topbar" data-fid="topbar">
          <div className="topbar__brand">
            {/* Official logo (docs/ui/brand/README.md): same bytes, no recolouring; intrinsic size keeps the ratio. */}
            <img className="brand__logo" src={logoUrl} alt="لوگوی سراجی سنتی عالیخان" width={300} height={298} data-testid="brand-logo" />
            <span className="brand__text">
              <span className="brand__name">سراجی سنتی عالیخان</span>
              <span className="brand__sub">{showNav && title ? title : "سامانه یکپارچه کارخانه"}</span>
            </span>
          </div>
          {showNav ? (
            <>
              <GlobalSearch canSerial={can(PERM.serialRead)} canOrder={can(PERM.orderRead)} canProduct={can(PERM.productRead)} />
              <div className="topbar__end">
                <TodayDate />
                {items.some((n) => n.path === "/work") ? (
                  <a href="#/work" className="iconbtn topbar__inbox" title="کارها و تأییدها" data-testid="topbar-inbox">
                    <Icon name="inbox" size={18} />
                    <span className="sr-only">کارها و تأییدها</span>
                  </a>
                ) : null}
                <div className="usermenu">
                  <button
                    type="button"
                    className="avatar"
                    aria-expanded={userOpen}
                    aria-controls="user-menu"
                    onClick={() => {
                      setUserOpen((o) => !o);
                    }}
                    data-testid="user-menu"
                    data-fid="topbar-user"
                  >
                    <Icon name="user" size={18} />
                    <span className="sr-only">حساب کاربری: {me?.user.display_name}</span>
                  </button>
                  {userOpen ? (
                    <div id="user-menu" className="usermenu__pop" data-testid="user-menu-pop">
                      <p className="usermenu__who" data-testid="current-user">{me?.user.display_name}</p>
                      <a href="#/me/sessions" className="usermenu__item">جلسه‌های من</a>
                      <button type="button" className="btn btn--secondary btn--block" onClick={() => void logout()} data-testid="logout">
                        خروج
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            </>
          ) : null}
        </header>

        {v && v.environment !== "production" ? (
          <p className="banner banner--env" data-testid="env-banner">
            محیط آزمایشی — داده ساختگی (محیط {ENVIRONMENT_LABELS[v.environment]})؛ این محیط داده واقعی کارخانه ندارد.
          </p>
        ) : null}
        {!online ? (
          <p className="banner banner--offline" role="status" data-testid="offline-banner">
            مرورگر آفلاین است؛ داده‌های نمایش‌داده‌شده ممکن است قدیمی باشند.
          </p>
        ) : null}

        <main id="main" tabIndex={-1} className="main">
          {children}
        </main>

        <footer className="footer" data-testid="footer-version">
          {v ? (
            <span>
              نسخه API <bdi dir="ltr">{v.api_version}</bdi> · قرارداد <bdi dir="ltr">{v.contract_version}</bdi> · ساخت{" "}
              <code dir="ltr" data-testid="footer-build">
                {v.build_commit}
              </code>
            </span>
          ) : version.isError ? (
            <span>نسخه سامانه دریافت نشد.</span>
          ) : (
            <span>در حال دریافت نسخه…</span>
          )}
        </footer>
      </div>
      {showNav ? (
        <BottomNav
          route={route}
          canNewOrder={can(PERM.orderManage)}
          onMore={() => {
            setMenuOpen(true);
          }}
        />
      ) : null}
    </div>
  );
}

/** Today in Asia/Tehran, Jalali (re-read every minute so a session past midnight shows the new day). */
function TodayDate() {
  const [iso, setIso] = useState(() => todayTehranIso());
  useEffect(() => {
    const id = window.setInterval(() => {
      setIso(todayTehranIso());
    }, 60_000);
    return () => {
      window.clearInterval(id);
    };
  }, []);
  return (
    <time className="topbar__date" dateTime={iso} data-testid="topbar-date" data-fid="topbar-date">
      <span className="sr-only">امروز: </span>
      {formatJalaliDate(iso)}
    </time>
  );
}

interface Hit {
  key: string;
  href: string;
  kind: string;
  text: string;
}

/**
 * Global search over the PHASE_02 records the user may read (serial number prefix, order number / PO, product
 * name / number). Each source is asked only when its read permission is granted; the server re-checks.
 */
function GlobalSearch({ canSerial, canOrder, canProduct }: { canSerial: boolean; canOrder: boolean; canProduct: boolean }) {
  const id = useId();
  const [text, setText] = useState("");
  const [term, setTerm] = useState("");
  const route = useRoute();
  const [openAt, setOpenAt] = useState<string | null>(null);
  const open = openAt === route;
  const setOpen = (o: boolean) => {
    setOpenAt(o ? route : null);
  };
  const digits = /^[0-9]{1,32}$/.test(term);
  const results = useQuery({
    queryKey: ["global-search", term, canSerial, canOrder, canProduct],
    enabled: term.length >= 2,
    queryFn: async ({ signal }): Promise<Hit[]> => {
      const jobs: Promise<Hit[]>[] = [];
      if (canSerial && digits)
        jobs.push(get("/identity/serials", g.serialPage, { q: term, page_size: 5 }, signal).then((r) => r.data.items.map((s) => ({ key: `s-${s.serial_id}`, href: `#/serials/${s.serial_id}`, kind: "سریال", text: s.serial_number }))));
      if (canOrder)
        jobs.push(get("/commercial/customer-orders", g.orderPage, { q: term, page_size: 5 }, signal).then((r) => r.data.items.map((o) => ({ key: `o-${o.order_id}`, href: `#/orders/${o.order_id}`, kind: "سفارش", text: o.external_po_number ? `${o.order_no} · ${o.external_po_number}` : o.order_no }))));
      if (canProduct)
        jobs.push(get("/identity/products", g.productPage, { q: term, page_size: 5 }, signal).then((r) => r.data.items.map((p) => ({ key: `p-${p.product_id}`, href: `#/products/${p.product_id}`, kind: "محصول", text: `${p.name_fa} · ${p.product_no}` }))));
      return (await Promise.all(jobs)).flat();
    },
  });
  const none = !canSerial && !canOrder && !canProduct;
  return (
    <div className="topsearch-wrap">
      <form
        className="topsearch"
        role="search"
        aria-label="جستجوی سراسری"
        data-fid="topbar-search"
        onSubmit={(e) => {
          e.preventDefault();
          setTerm(text.trim());
          setOpen(true);
        }}
      >
        <label htmlFor={id} className="topsearch__icon">
          <Icon name="search" size={18} />
          <span className="sr-only">جستجو در سریال، سفارش یا محصول</span>
        </label>
        <input
          id={id}
          className="topsearch__input"
          type="search"
          maxLength={100}
          disabled={none}
          placeholder={none ? "جستجو: مجوز خواندن سریال، سفارش یا محصول ندارید" : "جستجو در سریال، شماره سفارش، PO یا محصول…"}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
          }}
          data-testid="global-search"
        />
        <button type="submit" className="topsearch__go" disabled={none || text.trim().length < 2} data-testid="global-search-submit">
          جستجو
        </button>
      </form>
      {open && term.length >= 2 ? (
        <div className="topsearch__pop" data-testid="global-search-results">
          <div className="topsearch__pophead">
            <span>نتیجه برای «{term}»</span>
            <button type="button" className="iconbtn" onClick={() => { setOpen(false); }} aria-label="بستن نتیجه جستجو">
              <Icon name="close" size={16} />
            </button>
          </div>
          {results.isPending ? (
            <p className="state state--loading" data-testid="state-loading">در حال جستجو…</p>
          ) : results.isError ? (
            <p className="state state--error">جستجو انجام نشد؛ دوباره تلاش کنید.</p>
          ) : results.data.length === 0 ? (
            <p className="state state--empty">موردی پیدا نشد.</p>
          ) : (
            <ul className="topsearch__list">
              {results.data.map((h) => (
                <li key={h.key}>
                  <a
                    href={h.href}
                    onClick={(e) => {
                      e.preventDefault();
                      setOpen(false);
                      navigate(h.href.slice(1));
                    }}
                  >
                    <span className="chip chip--neutral">{h.kind}</span> <bdi dir="ltr">{h.text}</bdi>
                  </a>
                </li>
              ))}
            </ul>
          )}
          {!canSerial || !canOrder || !canProduct ? <p className="field__hint">فقط منابعی جستجو می‌شوند که مجوز خواندن آن‌ها را دارید.</p> : null}
          {canSerial && !digits ? <p className="field__hint">سریال فقط با رقم لاتین (ابتدای شماره) جستجو می‌شود.</p> : null}
        </div>
      ) : null}
    </div>
  );
}

/** Phone bottom navigation (concept of pages 1/2). Items of later phases are visibly disabled with the reason. */
function BottomNav({ route, canNewOrder, onMore }: { route: string; canNewOrder: boolean; onMore: () => void }) {
  return (
    <nav className="bottomnav" aria-label="ناوبری پایین (موبایل)" data-fid="bottom-nav">
      <a href="#/" className="bottomnav__item" aria-current={route === "/" ? "page" : undefined}>
        <Icon name="home" size={18} />
        <span>خانه</span>
      </a>
      <button type="button" className="bottomnav__item" disabled title="برنامه‌ریزی در فاز ۵ ساخته می‌شود" aria-describedby="bn-later">
        <Icon name="calendar" size={18} />
        <span>برنامه‌ریزی</span>
      </button>
      {canNewOrder ? (
        <a href="#/orders/new" className="bottomnav__item bottomnav__item--main" aria-current={route === "/orders/new" ? "page" : undefined}>
          <Icon name="plus" size={18} />
          <span>ثبت</span>
        </a>
      ) : (
        <button type="button" className="bottomnav__item bottomnav__item--main" disabled title="ثبت سفارش: مجوز ندارید" aria-describedby="bn-perm">
          <Icon name="plus" size={18} />
          <span>ثبت</span>
        </button>
      )}
      <button type="button" className="bottomnav__item" disabled title="گزارش‌ها در فازهای بعد ساخته می‌شود" aria-describedby="bn-later">
        <Icon name="chart" size={18} />
        <span>گزارش‌ها</span>
      </button>
      <button type="button" className="bottomnav__item" onClick={onMore} aria-controls="main-nav" data-testid="bottomnav-more">
        <Icon name="more" size={18} />
        <span>بیشتر</span>
      </button>
      <span id="bn-later" className="sr-only">در دست ساخت — در فازهای بعد</span>
      <span id="bn-perm" className="sr-only">مجوز ثبت سفارش ندارید</span>
    </nav>
  );
}
