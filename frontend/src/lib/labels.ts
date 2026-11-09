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

export interface ToneLabel {
  label: string;
  tone: Tone;
}

/** Machine codes of `Problem.errors[].code` with a Persian text (unknown codes are shown as the code). */
export const FIELD_ERROR_LABELS: Record<string, string> = {
  REQUIRED: "الزامی است",
  TOO_LONG: "بیش از حد طولانی است",
  TOO_SHORT: "بیش از حد کوتاه است",
  INVALID: "نامعتبر است",
  INVALID_UUID: "شناسه نامعتبر است",
  INVALID_CHOICE: "مقدار مجاز نیست",
  UNKNOWN_FIELD: "فیلد ناشناخته",
  NOT_SUPPORTED: "هنوز پشتیبانی نمی‌شود",
  SELF_ASSIGNMENT_NOT_CONFIRMED: "انتساب نقش به خودتان باید صریحاً تأیید شود",
  TYPE_NOT_ALLOWED: "نوع فایل مجاز نیست",
};

export const USER_STATUS: Record<string, ToneLabel> = {
  CREATED: { label: "ساخته‌شده (منتظر اولین ورود)", tone: "info" },
  ACTIVE: { label: "فعال", tone: "success" },
  LOCKED: { label: "قفل", tone: "warning" },
  DISABLED: { label: "غیرفعال", tone: "neutral" },
};
export const ACCOUNT_KIND: Record<string, string> = { PERSON: "شخص", OPERATOR: "اپراتور خط" };
export const NETWORK_POLICY: Record<string, string> = {
  INTERNAL_ONLY: "فقط شبکه داخلی",
  ANY_WITH_MFA_OUTSIDE: "هر شبکه (بیرون با ورود دومرحله‌ای)",
};
export const ROLE_KIND: Record<string, string> = { TECHNICAL: "فنی", BUSINESS: "کسب‌وکار" };
export const ROLE_STATUS: Record<string, ToneLabel> = {
  DRAFT: { label: "پیش‌نویس", tone: "neutral" },
  ACTIVE: { label: "فعال", tone: "success" },
  RETIRED: { label: "بازنشسته", tone: "neutral" },
};
export const ASSIGNMENT_STATUS: Record<string, ToneLabel> = {
  PENDING_APPROVAL: { label: "در انتظار تأیید نفر دوم", tone: "warning" },
  ACTIVE: { label: "فعال", tone: "success" },
  EXPIRED: { label: "منقضی", tone: "neutral" },
  REVOKED: { label: "لغوشده", tone: "neutral" },
};
export const SCOPE_KIND: Record<string, string> = {
  GLOBAL: "سراسری",
  ORG_UNIT: "یک واحد",
  ORG_UNIT_SUBTREE: "واحد و زیرمجموعه",
  SITE: "سایت",
  WAREHOUSE: "انبار",
  LINE: "خط",
  CUSTOMER: "مشتری",
};
export const SESSION_STATE: Record<string, ToneLabel> = {
  MFA_PENDING: { label: "منتظر کد دومرحله‌ای", tone: "warning" },
  ACTIVE: { label: "فعال", tone: "success" },
  EXPIRED: { label: "منقضی", tone: "neutral" },
  REVOKED: { label: "باطل‌شده", tone: "neutral" },
  LOGGED_OUT: { label: "خارج‌شده", tone: "neutral" },
};
export const NETWORK_ZONE: Record<string, string> = { INTERNAL: "شبکه داخلی", EXTERNAL: "بیرون از کارخانه", UNKNOWN: "نامعلوم" };
export const TASK_STATUS: Record<string, ToneLabel> = {
  OPEN: { label: "باز", tone: "info" },
  ASSIGNED: { label: "واگذارشده", tone: "info" },
  IN_PROGRESS: { label: "در حال انجام", tone: "info" },
  BLOCKED: { label: "مسدود", tone: "warning" },
  DONE: { label: "انجام‌شده (منتظر تأیید)", tone: "success" },
  CLOSED: { label: "بسته", tone: "neutral" },
  CANCELLED: { label: "لغوشده", tone: "neutral" },
};
export const APPROVAL_STATUS: Record<string, ToneLabel> = {
  PENDING: { label: "در انتظار تصمیم", tone: "warning" },
  APPROVED: { label: "تأییدشده", tone: "success" },
  REJECTED: { label: "ردشده", tone: "danger" },
  WITHDRAWN: { label: "پس‌گرفته", tone: "neutral" },
  EXPIRED: { label: "منقضی", tone: "neutral" },
  SUPERSEDED: { label: "جایگزین‌شده", tone: "neutral" },
};
export const APPROVAL_ACTION: Record<string, string> = {
  "platform.identity.assignment.grant": "انتساب نقش دارای حق تأیید",
  "platform.document.approve": "تأیید نسخه سند",
  "platform.config.parameter.publish": "انتشار مقدار پارامتر",
};
export const REVISION_STATUS: Record<string, ToneLabel> = {
  WORKING: { label: "در حال کار", tone: "info" },
  IN_REVIEW: { label: "در بازبینی", tone: "warning" },
  APPROVED: { label: "تأییدشده", tone: "success" },
  REJECTED: { label: "ردشده", tone: "danger" },
  SUPERSEDED: { label: "جایگزین‌شده", tone: "neutral" },
};
export const SCAN_STATUS: Record<string, ToneLabel> = {
  QUARANTINED: { label: "قرنطینه (منتظر بررسی ضدبدافزار)", tone: "warning" },
  SCANNING: { label: "در حال بررسی", tone: "info" },
  CLEAN: { label: "پاک", tone: "success" },
  REJECTED: { label: "ردشده توسط ضدبدافزار", tone: "danger" },
};
export const CLASSIFICATION: Record<string, ToneLabel> = {
  TECHNICAL: { label: "فنی", tone: "info" },
  OWNER_POLICY: { label: "سیاست مالک", tone: "neutral" },
  BUSINESS_RULE: { label: "قاعده کسب‌وکار", tone: "warning" },
};
export const VALUE_STATUS: Record<string, ToneLabel> = {
  DRAFT: { label: "پیش‌نویس", tone: "neutral" },
  PENDING_APPROVAL: { label: "منتظر انتشار", tone: "warning" },
  PUBLISHED: { label: "منتشرشده", tone: "success" },
  SUPERSEDED: { label: "جایگزین‌شده", tone: "neutral" },
  REJECTED: { label: "ردشده", tone: "danger" },
};
export const JOB_STATE: Record<string, ToneLabel> = {
  QUEUED: { label: "در صف", tone: "info" },
  RUNNING: { label: "در حال اجرا", tone: "info" },
  CANCEL_REQUESTED: { label: "درخواست لغو", tone: "warning" },
  CANCELLED: { label: "لغوشده", tone: "neutral" },
  SUCCEEDED: { label: "موفق", tone: "success" },
  FAILED: { label: "ناموفق", tone: "danger" },
};
export const INTEGRITY_STATUS: Record<string, ToneLabel> = {
  OK: { label: "سالم", tone: "success" },
  BROKEN: { label: "شکسته", tone: "danger" },
  NEVER_RUN: { label: "هنوز اجرا نشده", tone: "neutral" },
  ERROR: { label: "خطا در بررسی", tone: "danger" },
};

export function toneLabel(map: Record<string, ToneLabel>, key: string): ToneLabel {
  return map[key] ?? { label: key, tone: "neutral" };
}
