# Matrix تحویل هر فاز

| artefact | هر گام | Gate هر فاز | Pilot |
|---|---|---|---|
| Commit+diff+گزارش | اجباری | اجباری | اجباری |
| ERD/migrations | اگر تغییر دارد | نسخه کامل و تست | Freeze + audit |
| Engine source/golden tests | مربوط به گام | اجباری | UAT موردواقعی |
| OpenAPI + contract tests | تغییرات | اجباری | backwards compatibility |
| UI 4 viewport screenshots | مربوط به گام | تمام صفحات فاز | real operator |
| Access test / threat delta | اجباری | Security gate | Manual verification |
| source proof + reconciliation | مرتبط | اجباری در فاز داده | official reconciliation |
| Test commands + actual logs | اجباری | CI green | on site evidence |
| rollback/backup | در تغییر حساس | rehearsal | tested recovery |
| Decisions + defects | هر بار | P0 صفر | P0/P1 صفر |
| owner signoff | discovery owner | phase owner+کارفرما | چند واحد |

خروجی غیرواقعی/Mock به عنوان موفقیت نیست. ممیز می‌تواند با هر کنترل بنیادی ناقص `BLOCKED` اعلام کند.
