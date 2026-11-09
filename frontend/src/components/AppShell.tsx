import { useState, type ReactNode } from "react";

import logoUrl from "../assets/brand/aleekhan-logo.png";
import { useAuth } from "../auth/context";
import { useOnline } from "../lib/hooks";
import { ENVIRONMENT_LABELS } from "../lib/labels";
import { NAV, useVersion } from "../lib/nav";
import { useRoute } from "../lib/router";

function isActive(route: string, path: string): boolean {
  return path === "/" ? route === "/" : route === path || route.startsWith(`${path}/`);
}

/**
 * Page frame: skip link, top bar (logo, user menu), environment banner (from /version), offline banner,
 * role-aware navigation, main, footer. Navigation items the matrix denies are hidden (cosmetic only).
 */
export function AppShell({ children, authenticated = true }: { children: ReactNode; authenticated?: boolean }) {
  const online = useOnline();
  const version = useVersion();
  const v = version.data;
  const route = useRoute();
  const { me, canAny, logout, status } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const showNav = authenticated && status === "ready";
  const items = NAV.filter((n) => !n.anyOf || canAny(n.anyOf));

  return (
    <div className={showNav ? "shell shell--nav" : "shell"}>
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>
        رفتن به محتوای اصلی
      </a>
      <header className="topbar">
        <div className="brand">
          {/* Official logo (docs/ui/brand/README.md): same bytes, no recolouring; intrinsic size keeps the ratio. */}
          <img className="brand__logo" src={logoUrl} alt="لوگوی سراجی سنتی عالیخان" width={300} height={298} data-testid="brand-logo" />
          <span className="brand__text">
            <span className="brand__name">سراجی سنتی عالیخان</span>
            <span className="brand__sub">سامانه یکپارچه کارخانه</span>
          </span>
        </div>
        {showNav ? (
          <div className="topbar__user">
            <button
              type="button"
              className="btn btn--secondary nav-toggle"
              aria-expanded={menuOpen}
              aria-controls="main-nav"
              onClick={() => {
                setMenuOpen((o) => !o);
              }}
              data-testid="nav-toggle"
            >
              منو
            </button>
            <span className="topbar__name" data-testid="current-user">
              {me?.user.display_name}
            </span>
            <button type="button" className="btn btn--secondary" onClick={() => void logout()} data-testid="logout">
              خروج
            </button>
          </div>
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

      <div className="layout">
        {showNav ? (
          <nav id="main-nav" className={menuOpen ? "nav nav--open" : "nav"} aria-label="بخش‌های سامانه" data-testid="main-nav">
            <ul>
              {items.map((n) => (
                <li key={n.path}>
                  <a
                    href={`#${n.path}`}
                    className="nav__link"
                    aria-current={isActive(route, n.path) ? "page" : undefined}
                    onClick={() => {
                      setMenuOpen(false);
                    }}
                    data-testid={`nav-${n.path === "/" ? "home" : n.path.slice(1).replace("/", "-")}`}
                  >
                    {n.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        ) : null}
        <main id="main" tabIndex={-1} className="main">
          {children}
        </main>
      </div>

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
  );
}
