# راهبرد تست سرتاسری، CI و کیفیت داده

**Test pyramid:** Unit/property 60%, Integration/API/DB 25%, End-to-End/UX/Operational 15% (نسبت پیشنهادی، معیار اجباری نیست). تست امنیت و DB/Migration هر فاز مستقل و mandatory است.

## نوع آزمون
- Domain invariants and property-based: code textual identity, serial uniqueness, qty non-negative, closed serial rules, idempotency, schema ref integrity.
- Data golden test: Planning 14-digit representative categories; WH inventory import and formula preservation; die candidates from source DXF to tracker; cliche conflicts; family time study with no invented standards.
- Concurrency: 100+ parallel serial creations; reserve same lot simultaneously; operator multi-device duplicate writes; supplier ETA event replay; QC double-click.
- Failures: database rollback, outbox consumer crash after commit, job timeout & cancellation, stale snapshot, partial import, network partition, depleted object store.
- Security: IDOR/BOLA every CRUD, tenant/scope, field redaction price/wage, MFA sensitive actions, CSRF/XSS/SSRF, upload executable reject/quarantine, prompt injection AI.
- UI: Persian RTL, 1440/1180/768/390 px, browser variations, keyboard, focus, color contrast, loading/empty/error/stale statuses, no body horizontal overflow.
- MES: input/output exact, grade quarantine, rework no double-credit, partial shipment, line resource transfer donor cost, foot unit conversion.
- Operations: backup restore, migration rollback/compensation, alerts, audit integrity, logs redact, performance with realistic volume.

## شواهد CI
Automated test command/version and count recorded in REPORT; snapshots/screenshots link to the tested Commit; fake status GREEN forbidden. Golden datasets must have approved source/expected results and anonymized public test versions.

## Pilot
Before Go-Live: parallel comparison with Excel and Rahkaran export; one real lifecycle order→engineering→material→production→QC→partial dispatch; signed owner UAT; rollback and recovery demonstration.
