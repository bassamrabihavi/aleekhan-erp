import path from "node:path";
import { fileURLToPath } from "node:url";

export const BACKEND_URL = "http://127.0.0.1:8000";
export const FRONTEND_URL = "http://127.0.0.1:5173";

const here = path.dirname(fileURLToPath(import.meta.url));
/**
 * Screenshots. Default = untracked frontend/test-results/screenshots (REV-0501: a plain run must never overwrite
 * committed evidence). Acceptance evidence is produced for the CURRENT step only: `scripts/e2e.sh` maps
 * E2E_STEP=phase-02/step-7 to ../reports/phase-02/step-7/screenshots and refuses a folder that already holds
 * committed screenshots of another run (REV-0264); E2E_SCREENSHOT_DIR may still be passed explicitly.
 */
export const SCREENSHOT_DIR = process.env.E2E_SCREENSHOT_DIR
  ? path.resolve(process.env.E2E_SCREENSHOT_DIR)
  : path.resolve(here, "../test-results/screenshots");

/** Acceptance widths (UI_HANDOFF_INSTRUCTIONS_FA: 1440, 1180, 768, 390). */
export const VIEWPORTS = [
  { name: "1440-desktop", width: 1440, height: 900 },
  { name: "1180-laptop", width: 1180, height: 820 },
  { name: "768-tablet", width: 768, height: 1024 },
  { name: "390-mobile", width: 390, height: 844 },
] as const;

export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
