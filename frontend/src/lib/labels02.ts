// Persian labels of the PHASE_02 contract enums (machine values stay in the API). Order types, units and
// external reference types are the DEC-058 seed (migration 0021); an unknown value is shown as its code.
import type { ToneLabel } from "./labels";

export const ORDER_TYPES: Record<string, string> = {
  pre_production: "پیش تولید",
  series_production: "سری تولید",
  sampling: "نمونه‌سازی",
  trial_production: "تولید آزمایشی",
};
export const UOM: Record<string, string> = { PIECE: "عدد", PAIR: "جفت" };
export const REF_TYPES: Record<string, string> = {
  rahkaran_project_code: "کد پروژه راهکاران",
  contract_no: "شماره قرارداد",
  customer_style_code: "کد استایل مشتری",
  customer_serial: "سریال مشتری (هرگز سریال ما نیست)",
};
export const REF_SYSTEMS: Record<string, string> = {
  RAHKARAN: "راهکاران",
  CUSTOMER: "مشتری",
  LEGACY_PLANNING: "برنامه‌ریزی قدیم",
  OTHER: "سایر",
};
export const PARTY_STATUS: Record<string, ToneLabel> = {
  ACTIVE: { label: "فعال", tone: "success" },
  INACTIVE: { label: "غیرفعال", tone: "neutral" },
};
export const MASTER_STATUS: Record<string, ToneLabel> = {
  DRAFT: { label: "پیش‌نویس", tone: "neutral" },
  ACTIVE: { label: "فعال", tone: "success" },
  RETIRED: { label: "بازنشسته", tone: "neutral" },
  SUPERSEDED: { label: "جایگزین‌شده", tone: "neutral" },
};
export const CODE_STATUS: Record<string, ToneLabel> = {
  RESERVED: { label: "رزروشده", tone: "info" },
  ACTIVE: { label: "فعال", tone: "success" },
  DISPUTED: { label: "مورد اختلاف", tone: "warning" },
  RETIRED: { label: "بازنشسته", tone: "neutral" },
  CANCELLED: { label: "لغوشده", tone: "neutral" },
};
export const ERP_STATUS: Record<string, string> = {
  ERP_PENDING: "منتظر ثبت دستی در راهکاران",
  ERP_MATCHED: "در راهکاران تطبیق شد",
  ERP_MISSING: "در راهکاران پیدا نشد",
};
export const RULE_STATUS: Record<string, ToneLabel> = {
  DRAFT: { label: "پیش‌نویس", tone: "neutral" },
  IN_REVIEW: { label: "در بازبینی (منتظر تأیید)", tone: "warning" },
  APPROVED: { label: "تأییدشده (هنوز فعال نیست)", tone: "info" },
  ACTIVE: { label: "فعال", tone: "success" },
  RETIRED: { label: "بازنشسته", tone: "neutral" },
  REJECTED: { label: "ردشده", tone: "danger" },
};
export const SERIAL_STATUS: Record<string, ToneLabel> = {
  ALLOCATED: { label: "تخصیص‌یافته", tone: "success" },
  CANCELLED: { label: "لغوشده (شماره دوباره استفاده نمی‌شود)", tone: "neutral" },
};
export const ORDER_STATUS: Record<string, ToneLabel> = {
  DRAFT: { label: "پیش‌نویس", tone: "neutral" },
  VALIDATED: { label: "بررسی‌شده (منتظر تأیید برنامه‌ریزی)", tone: "warning" },
  CONFIRMED: { label: "تأییدشده (سریال تخصیص یافت)", tone: "success" },
  RELEASED_TO_PLAN: { label: "ارسال‌شده به برنامه‌ریزی", tone: "info" },
  ON_HOLD: { label: "متوقف", tone: "warning" },
  CANCELLED: { label: "لغوشده", tone: "neutral" },
  PARTIAL_FULFILLED: { label: "تحویل بخشی", tone: "info" },
  FULFILLED: { label: "تحویل کامل", tone: "success" },
  CLOSED: { label: "بسته", tone: "neutral" },
};
export const LINE_STATUS: Record<string, ToneLabel> = {
  OPEN: { label: "باز (پیش‌نویس)", tone: "neutral" },
  CONFIRMED: { label: "تأییدشده", tone: "success" },
  REMOVED: { label: "حذف‌شده از پیش‌نویس", tone: "neutral" },
  CANCELLED: { label: "لغوشده", tone: "neutral" },
};
export const CHANGE_KIND: Record<string, string> = {
  QTY_CHANGE: "تغییر تعداد",
  DUE_DATE_CHANGE: "تغییر تاریخ تحویل",
  ADD_LINE: "افزودن ردیف",
  CANCEL_LINE: "لغو ردیف",
  CANCEL_ORDER: "لغو کل سفارش",
  HOLD: "توقف سفارش",
  RESUME: "ادامه سفارش",
};
export const CHANGE_STATUS: Record<string, ToneLabel> = {
  DRAFT: { label: "پیش‌نویس", tone: "neutral" },
  SUBMITTED: { label: "ارسال‌شده (منتظر تصمیم)", tone: "warning" },
  APPROVED: { label: "تأییدشده (منتظر اعمال)", tone: "info" },
  REJECTED: { label: "ردشده", tone: "danger" },
  APPLIED: { label: "اعمال‌شده (نسخه جدید سفارش)", tone: "success" },
  WITHDRAWN: { label: "پس‌گرفته", tone: "neutral" },
  EXPIRED: { label: "منقضی", tone: "neutral" },
};
export const VERSION_REASON: Record<string, string> = {
  CONFIRMED: "تأیید سفارش",
  CHANGE_APPLIED: "اعمال درخواست تغییر",
  ALLOCATED: "تخصیص سریال",
  CANCELLED: "لغو با درخواست تغییر",
  TECH_PACKAGE_LINKED: "اتصال بسته فنی",
};
export const TRACKING_EVENT: Record<string, string> = {
  ORDER_DRAFTED: "پیش‌نویس سفارش ساخته شد",
  ORDER_VALIDATED: "سفارش بررسی شد",
  ORDER_CONFIRMED: "سفارش تأیید شد",
  SERIAL_ALLOCATED: "سریال تخصیص یافت",
  ORDER_RELEASED_TO_PLAN: "سفارش به برنامه‌ریزی ارسال شد",
  CHANGE_REQUESTED: "درخواست تغییر ثبت شد",
  CHANGE_DECIDED: "درباره درخواست تغییر تصمیم گرفته شد",
  CHANGE_APPLIED: "درخواست تغییر اعمال شد",
  ORDER_CANCELLED: "سفارش لغو شد",
  SERIAL_CANCELLED: "سریال لغو شد",
};
export const DECISION_KIND: Record<string, string> = {
  ORDER_CONFIRM: "تأیید سفارش و تخصیص سریال",
  CHANGE_DECIDE: "تصمیم درباره درخواست تغییر سفارش",
  CHANGE_PLANNING_DECISION: "تصمیم برنامه‌ریزی برای تغییر تاریخ تحویل",
  CODE_RULE_APPROVE: "تأیید نسخه قاعده کد ۱۴رقمی",
};
export const SECTION_LABEL: Record<string, string> = {
  materials: "مواد و انبار",
  wip: "کار در جریان (WIP)",
  production: "مراحل تولید",
  quality: "کیفیت و گرید",
  dispatch: "ارسال و محصول نهایی",
  capacity: "ظرفیت",
  cost: "هزینه",
};
export const ATTRIBUTE_LABEL: Record<string, string> = {
  colour_fa: "رنگ",
  main_material_fa: "جنس اصلی",
  lining_fa: "آستر",
  hardware_colour_fa: "رنگ یراق",
  notes_fa: "یادداشت",
};
/** Refusal reasons (errors[].code of PHASE_02) with a Persian text; unknown codes are shown as the code. */
export const REASON_LABELS: Record<string, string> = {
  DUPLICATE_PO_NUMBER: "شماره سفارش مشتری (PO) برای این مشتری تکراری است",
  DUPLICATE_CUSTOMER_NAME: "مشتری دیگری با همین نام وجود دارد",
  BELT_SEGMENTS_REQUIRED: "برای کمربند نوع سگک و عرض دو رقمی لازم است",
  BELT_SEGMENTS_NOT_ALLOWED: "نوع سگک و عرض فقط برای کمربند است",
  SEGMENT_FORMAT: "قالب بخش کد درست نیست (دو رقم)",
  MASTER_NOT_ACTIVE: "داده پایه (مشتری/محصول/استایل/نسخه) فعال نیست",
  ORDER_HAS_NO_LINES: "سفارش هیچ ردیفی ندارد",
  CONFIRMER_IS_CREATOR: "سازنده سفارش نمی‌تواند آن را تأیید کند",
  DECIDER_IS_REQUESTER: "درخواست‌کننده نمی‌تواند درباره درخواست خودش تصمیم بگیرد",
  DECIDER_IS_PLANNING_APPROVER: "تأییدکننده برنامه‌ریزی نمی‌تواند تصمیم بازرگانی را هم بگیرد",
  PLANNING_APPROVER_IS_REQUESTER: "درخواست‌کننده نمی‌تواند تأیید برنامه‌ریزی بدهد",
  PLANNING_APPROVER_IS_DECIDER: "مدیری که تصمیم گرفته نمی‌تواند تأیید برنامه‌ریزی هم بدهد",
  APPROVER_IS_MAKER: "سازنده قاعده نمی‌تواند آن را تأیید کند",
  PLANNING_APPROVAL_REQUIRED: "تغییر تاریخ تحویل تأیید برنامه‌ریزی هم لازم دارد",
  STALE_BASE_VERSION: "سفارش پس از ثبت این درخواست تغییر کرده است",
  OPEN_CHANGE_REQUEST_EXISTS: "این سفارش یک درخواست تغییر باز دارد؛ تا تعیین تکلیف آن، درخواست دیگری ارسال نمی‌شود",
  CHANGE_REQUEST_EXPIRED: "مهلت ۳۰ روزه این درخواست تغییر تمام شده است",
  STATE_NOT_ALLOWED: "در وضعیت کنونی این اقدام مجاز نیست",
  RELEASED_KIND_NOT_ALLOWED: "پس از ارسال به برنامه‌ریزی فقط تغییر تاریخ و توقف/ادامه مجاز است",
  CANCEL_AFTER_RELEASE: "لغو پس از ارسال به برنامه‌ریزی تا فاز ۵ مسدود است",
  ORDER_ON_HOLD: "سفارش متوقف است؛ فقط ادامه یا لغو (پیش از ارسال) مجاز است",
  CODE_ALREADY_ISSUED: "این استایل کد زنده دارد",
  STYLE_0000_LEGACY_ONLY: "استایل ۰۰۰۰ فقط سابقه است و صادر نمی‌شود",
  NO_ACTIVE_CODE_RULE: "قاعده کد فعالی وجود ندارد",
  TYPE_NOT_IN_RULE_SCOPE: "این نوع محصول در محدوده قاعده فعال نیست",
  GOLDEN_CASES_INSUFFICIENT: "نمونه‌های طلایی کافی نیست (حداقل ۲۰ برای هر خانواده)",
  GOLDEN_CASE_MISMATCH: "یک نمونه طلایی بازتولید نمی‌شود",
  QUANTITY_UNCHANGED: "تعداد تغییری نکرده است",
  DUE_DATE_UNCHANGED: "تاریخ تحویل تغییری نکرده است",
  DUE_BEFORE_ORDER_DATE: "تاریخ تحویل پیش از تاریخ سفارش است",
  LAST_LINE_CANCEL: "برای لغو آخرین ردیف، کل سفارش را لغو کنید",
  REQUIRED: "الزامی است",
  INVALID: "نامعتبر است",
  INVALID_DATE: "تاریخ نامعتبر است",
};
/** Validation reasons of validateProductCode. */
export const CODE_CHECK_REASONS: Record<string, string> = {
  LENGTH_NOT_14: "طول کد ۱۴ نویسه نیست",
  NON_ASCII_DIGIT: "رقم فارسی/عربی دارد (فقط رقم لاتین پذیرفته است؛ تبدیل خودکار انجام نمی‌شود)",
  NON_DIGIT_CHARACTER: "نویسه غیررقمی دارد",
  SURROUNDING_WHITESPACE: "فاصله اضافه در ابتدا یا انتها",
  NOT_PRODUCT_PREFIX: "با ۰۲ (ماهیت محصول) شروع نمی‌شود",
  LEGACY_ONLY_STYLE_0000: "استایل ۰۰۰۰: فقط سابقه",
  NOT_IN_REGISTRY: "در ثبت کدها نیست",
  DISPUTED_IN_REGISTRY: "در ثبت کدها مورد اختلاف است",
  WRONG_NAMESPACE: "فضای نام کد درست نیست",
};
