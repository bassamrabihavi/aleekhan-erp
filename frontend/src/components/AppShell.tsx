import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";

import type { VersionInfo } from "../api/types";
import logoUrl from "../assets/brand/aleekhan-logo.png";
import { useOnline } from "../lib/hooks";
import { ENVIRONMENT_LABELS } from "../lib/labels";

interface Props {
  version: UseQueryResult<VersionInfo>;
  children: ReactNode;
}

/**
 * Page frame: skip link, top bar, environment banner (from /version), offline banner, main, footer.
 * No navigation menu yet: PHASE_00 binds no business page (MOCK_UI_BINDING §2 rule 2 - nothing unbound shown).
 */
export function AppShell({ version, children }: Props) {
  const online = useOnline();
  const v = version.data;
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        رفتن به محتوای اصلی
      </a>
      <header className="topbar">
        <div className="brand">
          {/* Official logo (docs/ui/brand/README.md): same bytes, no recolouring; intrinsic size keeps the ratio. */}
          <img
            className="brand__logo"
            src={logoUrl}
            alt="لوگوی سراجی سنتی عالیخان"
            width={300}
            height={298}
            data-testid="brand-logo"
          />
          <span className="brand__text">
            <span className="brand__name">سراجی سنتی عالیخان</span>
            <span className="brand__sub">سامانه یکپارچه کارخانه</span>
          </span>
        </div>
      </header>

      {v && v.environment !== "production" ? (
        <p className="banner banner--env" data-testid="env-banner">
          محیط {ENVIRONMENT_LABELS[v.environment]} — داده ساختگی؛ این محیط داده واقعی کارخانه ندارد.
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
  );
}
