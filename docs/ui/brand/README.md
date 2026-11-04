# Brand assets

| File | Provenance | Size | SHA-256 |
|---|---|---|---|
| `aleekhan-logo.png` | Supplied by the employer (کارفرما) in the Claude Code session on 2026-11-04 as the official Aleekhan logo | 300×298 px, PNG RGBA, 61 750 bytes | `ef3fa9d16f433720dad7c271830b1edac9ca16091014468d94e1e24409c64b33` |

## Usage rules
- The logo replaces the placeholder emblem «ع» in the app shell header (`frontend/src/components/AppShell.tsx`). Wiring is scheduled with the next UI-touching step (00.6) and goes through implementer + reviewer.
- Always render with a Persian `alt` text: «لوگوی سراجی سنتی عالیخان».
- Do not recolour, crop or stretch; keep the aspect ratio.
- Logo colour is dark green, while the current design tokens use blue as the primary colour and gold for the emblem (`docs/ui/DESIGN_TOKENS.md`). Whether to align the palette with the logo is an open employer question, not decided by the agent.
- Source is a 300 px raster; a vector (SVG) master from the designer is preferred for print and large screens.
