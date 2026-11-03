# Design system و ۵۲ صفحه

این کاتالوگ تمام ۵۲ صفحه DRAFT را پوشش می‌دهد. **هیچ صفحه‌ای تأیید نهایی UI نشده است**؛ صفحات ۱ و ۲ در Manifest مسیر HTML مستقل ندارند. برای صفحات ۱۳ به بعد `?page=..` پروتوتایپ مشترک است.

روش استفاده توسعه‌دهنده: ابتدا ظاهر/جریان صفحه مرتبط را در Reference باز کن، بعد قرارداد مالکیت و API فاز را ببین، سپس کامپوننت React واقعی بساز. HTML/JS قدیمی را بی‌واسطه وارد اپلیکیشن نکن؛ هر داده و دکمه Mock باید به Contract و Endpoint وصل شود.

اصول UI: فارسی RTL؛ ناوبری سمت راست با hover+pin دسکتاپ و drawer موبایل؛ خوانایی در 1440,1180,768,390 px؛ کارت‌های موبایل به‌جای جدول فشرده؛ اطلاعات عملیاتی زمان‌مند همراه as-of؛ نمایش خطا/لودینگ/خالی/فاقد دسترسی/داده قدیمی و حالت Offline.

هر صفحه: owner, entity, data source, buttons+permission, draft/update/approval, API usage, failure handling, tests, screenshot and owner UAT must be listed. داده‌های نمایشی در کاتالوگ، Proof-of-Production نیستند.

فهرست دقیق فاز مربوط به هر صفحه: `UI_PAGE_PHASE_MAP.csv`.
