# frontend — Aleekhan web UI (React + TypeScript strict + Vite)

PHASE_00 / 00.5 smoke shell: one page, "وضعیت سامانه", bound to the real `/api/v1/health/*`, `/version` and
`/access-gate/check` endpoints (docs/discovery/MOCK_UI_BINDING.md §5). Design tokens: docs/ui/DESIGN_TOKENS.md.

Requirements: Node.js 24 LTS (`engines`), npm 11. Versions are exact pins (`package.json` + committed
`package-lock.json`), resolved with `npm install --before=<pin date - 14 days>`.

```bash
npm ci                       # install exactly the lock file
npm run dev                  # Vite on 127.0.0.1:5173, proxies /api -> Django 127.0.0.1:8000 (ALEEKHAN_BACKEND_URL)
npm run lint                 # eslint (typescript-eslint strict-type-checked + jsx-a11y strict + react-hooks), 0 warnings
npm run typecheck            # tsc --noEmit (app + node/e2e configs)
npm test                     # vitest + testing-library (state rendering, client, formatting)
npm run build                # typecheck + production bundle in dist/ (font bundled, no CDN)
npm run e2e                  # scripts/e2e.sh: throwaway PostgreSQL DB + migrate + runserver + Vite + Playwright
```

E2E environment: libpq variables (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`; never committed), optional
`PG_BIN` (dir with `psql`), `PLAYWRIGHT_BROWSERS_PATH` (browsers outside the repo). If the Playwright browser
CDN is unreachable, `E2E_BROWSER_CHANNEL=msedge` (or `chrome`) uses an installed Chromium browser.
`E2E_HTML_REPORT` / `E2E_OUTPUT_DIR` move Playwright artefacts outside the repo. Screenshots go to the
untracked `frontend/test-results/screenshots/` by default (REV-0501: a plain run never overwrites committed
evidence); for acceptance evidence pass the report folder explicitly, e.g.
`E2E_SCREENSHOT_DIR=../reports/phase-00/step-6/screenshots bash scripts/e2e.sh` (relative to `frontend/`).

Tests named `[simulated failure] …` intercept network traffic to produce error/stale states; every other E2E
test reads real backend responses. The `@backend-down` test runs with Django stopped (real failure).
