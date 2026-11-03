# مدل منطقی داده — مدیریت تیغه و درخواست ساخت

## تفکیک هویت فنی و نسخه فیزیکی

- `engineering.die_definitions` (`die_id`, `die_type_id`, `original_product_id`, `canonical_description_id`, `original_description`, `created_at`, `status`): **هویت منطقی تیغه**.
- `engineering.die_erp_references` (`die_erp_reference_id`, `die_id`, `erp_item_code CHAR(14)`, `erp_description_raw`, `erp_description_normalized`, `source_file_id`, `source_sheet`, `source_row`, `verification_status`, `verified_by`): ارتباط با **کد ۱۴رقمی راهکاران**. کد به‌صورت رشته ذخیره می‌شود؛ صفر آغازین حذف نمی‌شود. یکتایی کد باید در Scope فعال و با کنترل سوابق تاریخی اعمال شود.
- `engineering.die_revisions` (`die_revision_id`, `die_id`, `revision_code`, `parent_revision_id`, `technical_file_id`, `geometry_fingerprint`, `dimensions_json`, `tolerances_json`, `change_reason`, `approval_status`, `approved_by`, `approved_at`): فایل و هندسه، Revision ثابت پس از تأیید.
- `engineering.die_compatibility` (`die_id`, `product_id`, `style_id NULL`, `pattern_revision_id`, `status`, `approval_id`, `test_result_id`): استفاده از تیغه برای محصول یا استایل دیگر تنها پس از تأیید فنی.
- `warehouse.die_instances` (`die_instance_id`, `die_id`, `physical_tag`, `warehouse_location_id`, `health_status`, `custodian_id`, `last_counted_at`, `version`): **هر نمونه واقعی** از تیغه مستقل؛ ممکن است یک کد راهکاران چند نسخه فیزیکی داشته باشد.
- `warehouse.die_movements` (`movement_id`, `die_instance_id`, `from_location`, `to_location`, `serial_id`, `issued_at`, `returned_at`, `condition_on_return`, `source_document_id`): خروج/بازگشت انبارک.

## استخراج از DXF و ردیابی منبع

- `engineering.dxf_scan_runs` (`scan_id`, `source_file_id`, `source_hash`, `scan_mode` [manual/watched_folder], `parser_version`, `status`, `started_at`, `completed_at`, `error_report_id`): هر Scan با فایل، هش و نسخه الگوریتم.
- `engineering.dxf_detected_candidates` (`candidate_id`, `scan_id`, `layer_name`, `entity_handle`, `geometry_fingerprint`, `suggested_die_id NULL`, `similarity_score NULL`, `status` [unreviewed/accepted/rejected], `reviewer_id`, `review_reason`): هر مسیر DXF به‌صورت خودکار «تیغه» محسوب نمی‌شود.
- `engineering.die_source_imports` (`import_id`, `file_hash`, `sheet_name`, `cell_address`, `raw_value`, `canonical_value`, `mapping_status`): حفظ Cell Provenance برای «جدول پیگیری تیغه».

## ساخت و تأمین

- `engineering.die_fabrication_needs` (`need_id`, `die_id NULL`, `requested_revision_id`, `quantity`, `need_type` [new/additional_copy/repair], `reason`, `needed_by`, `compatibility_check_id`, `created_by`, `approval_status`): تعریف **نیاز فنی** با مالکیت مهندسی.
- `supply.die_fabrication_orders` (`fabrication_order_id`, `need_id`, `supplier_id`, `ordered_qty`, `quotation_id`, `status`, `planned_delivery_date`, `rahkaran_document_ref NULL`, `created_at`): سفارش ساخت/پیگیری تأمین؛ ثبت سند رسمی مالی همچنان در راهکاران.
- `supply.supplier_promise_history` (`promise_id`, `fabrication_order_id`, `promised_date`, `notified_at`, `reason`, `person_id`, `source`): سابقه وعده‌های سازنده **Append-only**.
- `warehouse.die_receipts` (`receipt_id`, `fabrication_order_id`, `received_qty`, `accepted_qty`, `quarantined_qty`, `receiving_user_id`, `inspection_id`, `rahkaran_receipt_ref NULL`): دریافت فیزیکی، شمارش و تأیید انبارک.

## قواعد محافظ داده

1. هیچ `die_erp_references.erp_item_code` نباید از روی فرمول کد محصول ساخته شود؛ قواعد اختصاص تیغه تا زمان تطبیق اسکریپت و جدول تاریخی **معلق** است.
2. جدا بودن `die_definitions` و `die_instances` اجباری است؛ موجودی «کد تیغه» با تعداد فیزیکی یکی نیست.
3. هر Revision تأییدشده Immutable است؛ نسخه جدید `parent_revision_id` و `change_reason` دارد.
4. یک Physical Instance در یک بازه زمانی نمی‌تواند هم‌زمان در دو محل/دو تحویل فعال باشد.
5. درخواست ساخت به Approval مهندسی و بررسی تیغه مشابه وابسته است؛ Supply حق تغییر نقشه یا کد فنی را ندارد.
6. پذیرش از سازنده مساوی `Ready` نیست؛ انبارک دریافت و مهندسی در صورت نیاز تأیید ساخت/ابعاد می‌دهد.
7. در مهاجرت رکوردهای نامطمئن باید `unverified` بمانند؛ «شرح مشابه» دلیل خودکار Merge نیست.
8. رویدادهای `DieRevisionApproved`, `DieFabricationRequested`, `SupplierPromiseChanged`, `DiePhysicallyReceived`, `DieHealthChanged` در همان تراکنش کسب‌وکاری به Outbox وارد شوند.
