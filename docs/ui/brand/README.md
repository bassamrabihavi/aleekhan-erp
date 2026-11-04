# Brand assets

| File | Provenance | Size | SHA-256 |
|---|---|---|---|
| `aleekhan-logo.png` | Supplied by the employer (کارفرما) in the Claude Code session on 2026-11-04 as the official Aleekhan logo | 300×298 px, PNG RGBA, 61 750 bytes | `ef3fa9d16f433720dad7c271830b1edac9ca16091014468d94e1e24409c64b33` |

## Usage rules
- The logo replaces the placeholder emblem «ع» in the app shell header (`frontend/src/components/AppShell.tsx`), wired in step 00.6 from the byte-identical copy `frontend/src/assets/brand/aleekhan-logo.png` (same SHA-256).
- Always render with a Persian `alt` text: «لوگوی سراجی سنتی عالیخان».
- Do not recolour, crop or stretch; keep the aspect ratio.
- Palette (employer choice, 2026-11-04): the logo's dark green becomes the primary brand colour (buttons, links, active nav, focus), replacing the former blue `--color-primary`. Done in 00.6: sampled value `#01392d` (`tools/sample_logo_colors.py`), contrast table and the success-colour change in `docs/ui/DESIGN_TOKENS.md` §5 / D4.
- Source is a 300 px raster; a vector (SVG) master from the designer is preferred for print and large screens.
