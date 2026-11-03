// Persian labels for contract enums. Machine values stay in the API; only the display text lives here.
import type { ComponentName, ComponentState, EnvironmentName } from "../api/types";

export type Tone = "success" | "warning" | "danger" | "neutral" | "info";

export const COMPONENT_LABELS: Record<ComponentName, string> = {
  database: "پایگاه داده",
  migrations: "مهاجرت‌های پایگاه داده",
  cache: "حافظه نهان",
  object_storage: "ذخیره‌ساز فایل",
  worker: "پردازشگر پس‌زمینه",
};

export const COMPONENT_STATE: Record<ComponentState, { label: string; tone: Tone }> = {
  up: { label: "سالم", tone: "success" },
  down: { label: "از کار افتاده", tone: "danger" },
  unknown: { label: "نامعلوم", tone: "neutral" },
};

export const ENVIRONMENT_LABELS: Record<EnvironmentName, string> = {
  dev: "توسعه",
  test: "آزمون",
  staging: "پیش‌تولید",
  production: "عملیاتی",
};
