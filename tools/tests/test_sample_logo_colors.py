"""Unit tests for tools/sample_logo_colors.py (synthetic in-memory PNGs; the real logo is only read)."""

import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sample_logo_colors as slc

LOGO = Path(__file__).resolve().parents[2] / "docs" / "ui" / "brand" / "aleekhan-logo.png"


def _chunk(kind: bytes, body: bytes) -> bytes:
    return (
        struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    )


def synthetic_png(rows: list[list[tuple[int, int, int, int]]], filters: list[int]) -> bytes:
    """RGBA 8-bit PNG; each row encoded with the given filter type (0 None, 1 Sub, 2 Up)."""
    width = len(rows[0])
    raw = bytearray()
    prev = bytes(width * 4)
    for row, ftype in zip(rows, filters, strict=True):
        line = bytes(v for px in row for v in px)
        if ftype == 1:
            enc = bytes((line[i] - (line[i - 4] if i >= 4 else 0)) & 0xFF for i in range(len(line)))
        elif ftype == 2:
            enc = bytes((line[i] - prev[i]) & 0xFF for i in range(len(line)))
        else:
            enc = line
        raw += bytes([ftype]) + enc
        prev = line
    ihdr = struct.pack(">IIBBBBB", width, len(rows), 8, 6, 0, 0, 0)
    return (
        slc.PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _chunk(b"IEND", b"")
    )


class SampleLogoColorsTest(unittest.TestCase):
    def test_decode_synthetic_png_with_filters(self) -> None:
        green, white, clear = (1, 57, 45, 255), (255, 255, 255, 255), (0, 0, 0, 0)
        rows = [[green, white, clear], [white, green, green], [clear, clear, green]]
        png = synthetic_png(rows, [0, 1, 2])
        w, h, ch, px = slc.decode_png(png)
        self.assertEqual((w, h, ch), (3, 3, 4))
        self.assertEqual(px, bytes(v for row in rows for p in row for v in p))

    def test_contrast_known_values(self) -> None:
        self.assertAlmostEqual(slc.contrast((0, 0, 0), (255, 255, 255)), 21.0, places=6)
        self.assertAlmostEqual(slc.contrast((255, 255, 255), (255, 255, 255)), 1.0, places=6)
        self.assertAlmostEqual(slc.contrast((1, 57, 45), (255, 255, 255)), 12.93, places=2)

    def test_rejects_non_png_and_unsupported(self) -> None:
        with self.assertRaises(ValueError):
            slc.decode_png(b"not a png")
        ihdr = struct.pack(">IIBBBBB", 1, 1, 16, 6, 0, 0, 0)
        with self.assertRaises(ValueError):
            slc.decode_png(slc.PNG_SIGNATURE + _chunk(b"IHDR", ihdr))

    @unittest.skipUnless(LOGO.exists(), "brand logo not present")
    def test_logo_dominant_colour_is_the_primary_token(self) -> None:
        w, h, ch, px = slc.decode_png(LOGO.read_bytes())
        self.assertEqual((w, h, ch), (300, 298, 4))
        counts: dict[tuple[int, int, int], int] = {}
        for k in range(0, len(px), ch):
            if px[k + 3] >= 250:
                key = (px[k], px[k + 1], px[k + 2])
                counts[key] = counts.get(key, 0) + 1
        self.assertEqual(max(counts, key=lambda c: counts[c]), (1, 57, 45))  # --color-primary #01392d


if __name__ == "__main__":
    unittest.main()
