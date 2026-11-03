# قراردادهای API پیشنهادی — صفحات ۰۹ و ۱۰

این‌ها قراردادهای پیشنهادی هستند، نه API پیاده‌سازی‌شده.

## صفحه ۰۹ — مهندسی و طراحی

| Method | Route | کاربرد / مجوز |
|---|---|---|
| GET | `/api/v1/engineering/dies/{dieId}` | خواندن پرونده فنی با مجوز نقش |
| GET | `/api/v1/engineering/dies/{dieId}/revisions` | Revisionها و فایل‌های تأییدشده |
| POST | `/api/v1/engineering/dies/{dieId}/revisions` | ایجاد Draft نسخه جدید؛ فقط مهندسی |
| POST | `/api/v1/engineering/die-revisions/{revisionId}/submit` | ارسال برای بازبینی |
| POST | `/api/v1/engineering/die-revisions/{revisionId}/approve` | تأیید با Separation of Duties |
| GET | `/api/v1/engineering/dies/{dieId}/compatibilities` | محصولات/استایل‌های تأییدشده |
| POST | `/api/v1/engineering/dies/{dieId}/fabrication-needs` | ایجاد نیاز فنی با Approval |
| GET | `/api/v1/warehouse/dies/{dieId}/instances` | فقط خواندن موجودی نسخه‌های فیزیکی |
| POST | `/api/v1/workflow/tasks` | درخواست بررسی انبارک با Context تیغه |

## صفحه ۱۰ — تأمین

| Method | Route | کاربرد / مجوز |
|---|---|---|
| GET | `/api/v1/supply/die-fabrication-orders` | لیست + جستجو + فیلتر + صفحه‌بندی |
| POST | `/api/v1/supply/die-fabrication-orders` | ساخت سفارش از نیاز فنی تأییدشده |
| GET | `/api/v1/supply/die-fabrication-orders/{id}` | جزئیات/وعده‌ها/تاریخچه |
| POST | `/api/v1/supply/die-fabrication-orders/{id}/follow-ups` | ثبت نتیجه تماس/پیگیری |
| POST | `/api/v1/supply/die-fabrication-orders/{id}/supplier-promises` | ثبت وعده جدید؛ تاریخچه حفظ شود |
| POST | `/api/v1/supply/die-fabrication-orders/{id}/announce-ready` | اعلام آماده تحویل؛ نه دریافت قطعی |
| POST | `/api/v1/warehouse/die-receipts` | شمارش/دریافت فیزیکی توسط انبارک |
| GET | `/api/v1/integrations/rahkaran/reconciliation?entity=die` | تطبیق اسناد واردشده با راهکاران |

## فیلدهای عمومی Command

`commandId` (idempotency UUID), `expectedVersion`, `actorContext`, `reason`, `attachments[]`, `occurredAt`. کلاینت هرگز Role خود را به‌عنوان مجوز قطعی به Backend تحمیل نمی‌کند؛ مجوز از Session/Backend تعیین می‌شود.

## پاسخ خطای استاندارد

```json
{
  "code": "DIE_REVISION_NOT_APPROVED",
  "message_fa": "نسخه فنی تیغه هنوز تأیید نشده است؛ درخواست ساخت جدید قابل ارسال نیست.",
  "entity": {"type": "die_revision", "id": "..."},
  "retryable": false,
  "required_action": "درخواست تأیید مهندسی"
}
```

## مرز تراکنش

- تأیید Revision + تغییر Reference جاری + Audit + Outbox: **اتمیک**.
- ثبت درخواست ساخت معتبر + جلوگیری از Duplicate Need/Qty + Workflow Task + Audit + Outbox: **اتمیک**.
- ورود سند رسمی راهکاران از `staging → validation → reconciliation → commit`; هیچ ویرایش مستقیم از Supply روی اسناد مالی مجاز نیست.
- دریافت فیزیکی + Instance/Location + Quality Hold (در صورت لزوم) + Audit + Outbox: **اتمیک**.
