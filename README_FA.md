# کیت مدیریت پروژه عالیخان در Claude Code

با این کیت، Claude Code خودش نقش **مدیر پروژه** را دارد. یعنی گام بعدی را انتخاب می‌کند، کدنویسی را به یک عامل اجرا می‌سپارد، تست‌ها را خودش دوباره اجرا می‌کند، کار را به یک **ممیز مستقل** می‌دهد و نتیجه را در فایل وضعیت ثبت می‌کند. بعد به شما به فارسی گزارش می‌دهد. شما فقط سه کار دارید: **تصمیم‌ها، تأیید Gateها و تست‌های کاربری.**

## پیش‌نیاز هر دو سیستم
- **ویندوز (محل کار):** Git for Windows، Python 3.12 (هنگام نصب گزینه «Add to PATH» را بزنید)، Claude Code.
- **اوبونتو (خانه):** `sudo apt install git python3`، Claude Code.
- یک مخزن خصوصی خالی (پیشنهاد DEC-041: GitHub private)، مثلاً `https://github.com/<you>/aleekhan-erp.git`.

## راه‌اندازی سیستم اول (محل کار، ویندوز) — یک‌بار
در **PowerShell**:
```powershell
cd D:\aleekhan
Expand-Archive aleekhan-claude-control.zip -DestinationPath .
python aleekhan-claude-control\setup_repo.py new --handoff D:\aleekhan\ALEEKHAN_MASTER_HANDOFF_V1 --repo D:\aleekhan\aleekhan-erp --remote https://github.com/<you>/aleekhan-erp.git
setx ALEEKHAN_MACHINE "work-windows"
setx ALEEKHAN_PRIVATE_DIR "D:\aleekhan-private"
```
پوشه `09_PRIVATE_FACTORY_SOURCES` و فایل‌های جدید را در `D:\aleekhan-private` بگذارید، **بیرون از مخزن**. بعد یک PowerShell تازه باز کنید:
```powershell
cd D:\aleekhan\aleekhan-erp
$env:ALEEKHAN_SRC_PASSWORD = Read-Host "رمز فایل‌ها"     # فقط برای همین پنجره
claude
```
و در Claude Code: `/kickoff`

## راه‌اندازی سیستم دوم (خانه، اوبونتو) — یک‌بار
```bash
unzip aleekhan-claude-control.zip -d ~/aleekhan && cd ~/aleekhan
python3 aleekhan-claude-control/setup_repo.py clone --remote https://github.com/<you>/aleekhan-erp.git --repo ~/aleekhan/aleekhan-erp
echo 'export ALEEKHAN_MACHINE=home-ubuntu' >> ~/.bashrc && source ~/.bashrc
cd ~/aleekhan/aleekhan-erp && claude
```
و در Claude Code: `/sync`

اگر DEC-028 همین‌طور تصویب شود، سیستم خانه **پوشه خصوصی ندارد**. کار ادامه پیدا می‌کند، ولی تست‌هایی که فایل خام لازم دارند فقط در محل کار اجرا می‌شوند و Claude این را در گزارش می‌گوید.

## کار روزانه از هر دو سیستم
- **فقط دیدن وضعیت:** `/sync` یا `/status`. هیچ تغییری نمی‌دهد و هر وقت بخواهید، از هر سیستم، اجرا می‌شود.
- **جلو بردن کار:** `/next 3`. قبل از شروع قفل کار را می‌گیرد، بعد از هر گام قبول‌شده Push می‌کند و آخر کار قفل را آزاد می‌کند.
- اگر در خانه `/next` بزنید و قفل دست سیستم محل کار باشد، Claude کار نمی‌کند و می‌گوید قفل دست کیست. اگر مطمئنید آن جلسه بسته شده، بگویید «قفل را آزاد کن».
- گراف و زمان‌بندی: فایل `control/STATUS.html` را در مرورگر باز کنید (هر دو سیستم).
- هر جلسه Claude Code خودش اول `git pull` می‌کند و وضعیت را نشان می‌دهد.

## فرمان‌های شما
| فرمان | کار |
|---|---|
| `/kickoff` | اولین اجرا: بررسی هش‌ها، ثبت منابع جدید، گرفتن مجوز شروع فاز ۰ |
| `/next 3` | ادامه کار تا ۳ گام، یا تا Gate یا مانع |
| `/sync` | همگام‌سازی این سیستم با مخزن مشترک و نمایش وضعیت (بدون شروع کار) |
| `/status` | گزارش فارسی: فاز فعال، گام جاری، آماده تست، منتظر شما، برآورد پایلوت |
| `/decide DEC-001 APPROVED نام "متن تصمیم"` | ثبت تصمیم |
| `/gate PHASE_00` | ساخت بسته تأیید Gate با چک‌لیست تست |
| `/approve PHASE_00 ACCEPTED نام "توضیح"` | تأیید یا رد Gate (فقط شما) |
| `/start PHASE_01 نام` | شروع رسمی فاز بعدی |
| `/test-result T-003 FAIL "توضیح"` | ثبت نتیجه تست شما |

گراف و زمان‌بندی همیشه در `control/STATUS.html` است. آن را در مرورگر باز کنید. گزارش متنی در `control/STATUS_FA.md` است.

## قفل‌های ایمنی (با تست بررسی شده)
- شروع فاز بدون پذیرش Gate فازهای پیش‌نیاز **رد** می‌شود.
- شروع فاز بدون نام کارفرما **رد** می‌شود.
- گامی که گام‌های قبلی‌اش PASS نشده‌اند **شروع نمی‌شود**.
- ارسال به ممیزی بدون commit و فایل گزارش **رد** می‌شود.
- PASS بدون فایل REVIEW با `VERDICT: PASS` از ممیز مستقل **رد** می‌شود.
- تأیید Gate با تصمیم P0 باز **رد** می‌شود.
- بستن تصمیم بدون نام و متن تصمیم **رد** می‌شود.
- Commit فایل‌های xlsx/xlsm/dxf/zip، پوشه خصوصی یا رمز **مسدود** می‌شود (pre-commit، روی ویندوز و لینوکس).
- دو سیستم نمی‌توانند هم‌زمان کار را جلو ببرند (قفل کار، ۱۲ ساعت اعتبار).
- Claude Code اجازه ویرایش `handoff/` و ویرایش مستقیم فایل وضعیت را ندارد.

پیشنهادهای تصمیم‌های Gate-0 همراه دستور آماده `/decide` در `control/decisions/DECISION_PROPOSALS_GATE0_FA.md` است.

## اجرای بدون حضور شما (اختیاری)
`claude -p "/next 5"` کار را بدون حضور شما جلو می‌برد و در Gate یا اولین مانع متوقف می‌شود. تأیید Gate و تصمیم‌ها همیشه منتظر شما می‌ماند.
