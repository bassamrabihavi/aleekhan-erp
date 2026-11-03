# تصمیم‌ها و وابستگی‌ها

فهرست `DECISION_REGISTER.csv` شامل موارد `OPEN`, `PROPOSED` است. فاز ۰ حق دارد تصمیم‌های مربوط به آن را برای تصویب صورت‌جلسه کند؛ سایر فازها روی مرزهای مستقل می‌توانند ادامه دهند اما **Publish/Commit حساس با تصمیم P0 باز ممنوع است**.

برای تصویب، در repository توسعه: decision_id, chosen option, signer, timestamp UTC, reference, impact, test cases, next action را ثبت کن. هیچ status `APPROVED` تنها با پاسخ ChatGPT یا پیشنهاد Agent ایجاد نشود؛ تصویب با مالک انسانی است.
