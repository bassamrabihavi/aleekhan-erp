# UI polish backlog (employer requests)

The employer asked for a separate **UI polish pass after all phases are finished**. In that pass every page is reviewed one by one: look and feel, colour combinations, imagery, and everything else.

These items are **not** in the scope of the current phases, and they do not block any Gate.

| ID | Date | Page / area | Request (employer's words, summarised) | Source |
|---|---|---|---|---|
| UIP-001 | 2026-11-11 | Login cards (login, password change, MFA enrolment) | The page background behind the login cards should use images related to the company. | Employer during UAT T-003 step 1 |
| UIP-002 | 2026-11-11 | App shell layout (all pages) | Put the brand «سراجی سنتی عالیخان» (logo + name) at the top of the sidebar. The top bar should sit beside the sidebar, not across it. The top bar should show the selected section's title and description; for the dashboard that is «پیشخوان — سلام، … — بخش‌هایی که نقش‌های شما اجازه می‌دهد…». Today that text sits in the page body. | Employer during UAT T-003 step 1 (screenshot of the dashboard) |
| UIP-003 | 2026-11-16 | Pages 29 / 33 / 1-2 (full-page screenshots, PHASE_02 Gate review) | Orchestrator remarks, not the employer's: in full-page screenshots the sticky top bar appears mid-page, and the version-conflict dialog's dark backdrop covers only the first screen height. One JS chunk is about 530 kB (code-splitting). | Orchestrator screenshot review 02.8 (REV-0253) |
| UIP-004 | 2026-11-19 | Serial pages 1/2 (laptop 901–1200 px), phone tabs at 390 | Reviewer remarks, not the employer's: `zoom: 0.8` on laptops with 9–9.5 px text hurts readability; the docked tab bar may overlap content at 390. Keep DEC-061 ≥95% when fixing. | Reviewer 02.8 rework (REV-0300) |
