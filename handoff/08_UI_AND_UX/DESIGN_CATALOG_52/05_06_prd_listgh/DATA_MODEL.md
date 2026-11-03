# مشخصات مدل داده — برگه تولید، لیست برش، مواد و تیغه

## ۱. مرز موجودیت‌ها و مالکیت
- `product` → `style` → `serial`، کد ERP محصول ۱۴ رقمی **رشتهٔ ۱۴حرفی** (`char(14)`، نه عدد)؛ حروف و صفرهای ابتدایی نباید گم شوند.
- `serial_production_sheet` = نسخه برگه چاپی/اجرایی شامل `serial_id`, `sheet_revision`, `form_code`, `erp_code_snapshot`, `order_snapshot`, `approved_at`, `status`؛ بعد از تأیید Immutable.
- `serial_material_spec_line` = `id`, `serial_id`, `style_id`, `production_sheet_revision`, `role_type_id`, `display_order`, `material_id`, `material_variant_id`, `material_name_raw`, `material_code_snapshot`, `material_color_id`, `print_id`, `finish_id`, `supplier/lot_constraint`, `quality_standard_revision`, `base_uom_id`, `consumption_uom_id`, `consumption_per_unit Decimal`, `waste_rate Decimal`, `waste_rule_version`, `usage_location`, `is_active`, `source_file/sheet/cell`, `audit/version`.
- `role_type` قابل گسترش (`MAIN_LEATHER`, `EXTRA_LEATHER`, `LINING`, `BACKING`, `HARDWARE`, `ADHESIVE`, `THREAD`, ...). UI نقش «خرجکار n» یا «آستر n» را از ترکیب `role_type` و `display_order` می‌سازد، نه از ستون اختصاصی.
- `cut_part` = `id`, `sheet_revision`, `piece_id`, `piece_revision`, `sequence`, `cut_qty`, `crop_direction`, `print`, `cut_mix_id`, `die_id`, `die_revision`, `die_notes`, `lining_material_line_id`, `lining_piece_refs`, `notes`, `checked_status`, `check_by/at`.
- `material_master` با کد راهکاران، نام استاندارد، Alias و واحد پایه؛ هر متریال در برگه Reference به مستر دارد؛ متن خام فقط برای Provenance.
- `die_master` = `die_id`, `product_id`, `die_type`, `die_title_canonical`, `original_title`, `erp_code_14`, `erp_description_current`, `technical_file_id`, `revision`, `physical_status`, `custodian`, `source_provenance`.
- `die_erp_description_history`, `die_tracking_event`, `die_code_allocation` با `UNIQUE(erp_code_14)` و CodeSequence اتمیک.
- `production_sheet_print_snapshot`: فایل PDF خروجی مصوب، `source_revision`, `layout_revision`, `hash`, `generated_at`, `generated_by`.

## ۲. اعتبارسنجی و رفتارها
- تعداد `material_spec_line` برای هر نقش **نامحدود از دید Business Logic**؛ محدودیت عملی فقط Page/Query Pagination و ظرفیت زیرساخت است.
- تمام واحدها از Unit Master و Conversion Rule استفاده می‌کنند؛ تبدیل غیرمجاز خودکار نیست؛ ضریب مصرف و پرت Decimal و nonnegative، مقدار واحد با UOM validation؛ صفر/تهی از هم متمایز.
- خام‌نویسی `nim halghe 9mil` ابتدا به Suggestion می‌رود؛ Material Master یا نقش Usage بعد از تایید مشخص می‌شود. `سرزیپ ۵` با `آویز زیپ` بی‌صدا Merge نمی‌شود؛ تعارض کد/شرح Error.
- تغییر متریال بعد از تأیید Engineering Release Package نیاز به ECR/ECO و تحلیل اثر مواد رزروشده/برش‌خورده/تولیدشده دارد.
- `serial_material_spec_line` صرفاً مشخصات ساخت را نمایندگی می‌کند؛ BOM با Revision مهندسی منبع محاسبه مصرف است. اختلاف فرم و BOM باید در Validation Gate گزارش شود.
- QA: Grade Requirement مشتری و Eligible Lot کنترل شود؛ وضعیت قرنطینه همیشه از Available جدا گردد.
- کد محصول و کد تیغه مستقل‌اند؛ هر دو ۱۴رقمی و شناسه‌های تجاری، نه کلید اصلی DB.

## ۳. WH و میراث داده
- `WH!A1:M1` و `Split DB!A1:AY1` دو ساختار متفاوت هستند: اول **کاتالوگ کالا**؛ دوم **جداسازی/جزئیات مواد سریال**. آن‌ها نباید در یک Table مسطح Merge شوند.
- `Split DB` داده Quantity، Delivered، Return، GAP، WH Status را به مدل‌های MaterialRequirement, Reservation, Issuance, Return, InventoryReconciliation, GapCase نگاشت می‌کند؛ از دست‌رفتن ستون نامشخص ممنوع.
- `Kanban`, `Split Form`, `Gap` اسناد/نماهای جدا با Format/Rule Version و Print Projection.

## ۴. حفاظت از داده‌ها و QA
- همه Importها `raw_file`، `raw_cell`، `mapping_version`، `normalized_entity`, `approval_status`, `reconciliation_total` دارند.
- از `source_cell_map.csv` برای ردیابی آدرس سلول به نام و بخش UI استفاده شود. این فایل **نقشه اولیه استخراج** است و هنوز نگاشت رسمی تمام Valueهای شیت نیست.
- جدول‌های Core/FK و Unique روی Product/Style/Serial/Code/Revision/MaterialID/DieID و `idempotency_key` اعمال شوند.
- Export/Print: header اصلی را حفظ کند و Material rows و Cut parts را بسته به تعداد expand کند؛ overflow به صفحه بعد با Repeat Header.
