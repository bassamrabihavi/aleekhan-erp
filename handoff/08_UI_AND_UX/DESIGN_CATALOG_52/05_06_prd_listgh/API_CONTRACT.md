# API Contract اولیه (غیر اجرایی)

- `GET /api/v1/serials/{serialId}/production-sheet?revision=...`: دسترسی role-scope، وضعیت فنی، header از Snapshot، `materials[]`, `cuts[]`, `source_refs[]`, `warnings[]`.
- `POST /api/v1/serials/{serialId}/production-sheet/draft`: ایجاد پیشنویس نسخه با idempotency-key.
- `PATCH /api/v1/production-sheets/{id}/material-lines/{lineId}`: ویرایش مقادیر Typed، `If-Match` برای جلوگیری از overwrite.
- `POST /api/v1/production-sheets/{id}/material-lines`: افزودن Role/Material بدون حد ثابت؛ نتیجه ID و شماره نمایش.
- `PATCH /api/v1/production-sheets/{id}/material-line-order`: تغییر ترتیب بدون تغییر هویت Line.
- `POST /api/v1/production-sheets/{id}/validate`: Unit, Waste, Material Master, Quality, BOM/Revision, Die, CutMix.
- `POST /api/v1/production-sheets/{id}/submit`: QA/Engineering/Planning Approval Workflow؛ تغییر Approval → Event/Audit.
- `POST /api/v1/production-sheets/{id}/print`: snapshot چاپی immutable + لینک؛ ساخت PDF در Backend.
- `GET /api/v1/serials/{serialId}/cut-list`: Header listGH و `cut_part[]`.
- `POST /api/v1/serials/{serialId}/cut-list/items`: ایجاد ردیف قطعه؛ باید با PieceRev/DieRev معتبر سازگار باشد.
- `GET /api/v1/erp/materials?query=...` و `GET /api/v1/dies?productCode=...`؛ Search normalized + code exact-match.
- `POST /api/v1/integrations/wh/imports`: Upload→Staging→Validation→Reconciliation→Approval→Commit.
- `GET /api/v1/imports/{id}/unmapped-cells`: نامشخص‌ها با file/sheet/address/raw-value.

**Contract Fail:** ذخیره واقعی زمانی مجاز است که تمام کدهای راهکاران و مرجع ماده Validator را پاس کرده باشند؛ فرض فرم UI هرگز جای Rule Engine نیست.
