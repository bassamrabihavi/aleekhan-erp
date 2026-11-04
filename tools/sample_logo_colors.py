"""Sample the dominant colours of the brand logo (stdlib only: zlib + struct; no Pillow).

Usage:  python tools/sample_logo_colors.py [docs/ui/brand/aleekhan-logo.png]

Decodes 8-bit non-interlaced PNG (colour types 2 = RGB and 6 = RGBA; all five filter types), keeps opaque
pixels (alpha >= 250), drops near-white / near-grey pixels, quantises to 4-bit-per-channel buckets and prints
the most frequent buckets with the average exact colour of each bucket, its HSL and its WCAG contrast against
white. Read-only: it never writes or modifies the image. Used for docs/ui/DESIGN_TOKENS.md section 5.
"""

from __future__ import annotations

import colorsys
import struct
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode_png(data: bytes) -> tuple[int, int, int, bytes]:
    """Return (width, height, channels, raw pixel bytes) for 8-bit RGB/RGBA non-interlaced PNG."""
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file")
    pos = len(PNG_SIGNATURE)
    idat = bytearray()
    width = height = channels = 0
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        ctype = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, depth, colour, _comp, _filt, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or colour not in (2, 6) or interlace != 0:
                raise ValueError(f"unsupported PNG: depth={depth} colour={colour} interlace={interlace}")
            channels = 3 if colour == 2 else 4
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    out = bytearray(height * stride)
    prev = bytearray(stride)
    i = 0
    for y in range(height):
        ftype = raw[i]
        line = bytearray(raw[i + 1 : i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if ftype == 1:
                line[x] = (line[x] + a) & 0xFF
            elif ftype == 2:
                line[x] = (line[x] + b) & 0xFF
            elif ftype == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 0xFF
            elif ftype == 4:
                line[x] = (line[x] + _paeth(a, b, c)) & 0xFF
            elif ftype != 0:
                raise ValueError(f"bad filter type {ftype}")
        out[y * stride : (y + 1) * stride] = line
        prev = line
    return width, height, channels, bytes(out)


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def main(path: str) -> None:
    width, height, ch, px = decode_png(Path(path).read_bytes())
    buckets: Counter[tuple[int, int, int]] = Counter()
    sums: dict[tuple[int, int, int], list[int]] = defaultdict(lambda: [0, 0, 0])
    opaque = 0
    for k in range(0, len(px), ch):
        r, g, b = px[k], px[k + 1], px[k + 2]
        alpha = px[k + 3] if ch == 4 else 255
        if alpha < 250:
            continue
        opaque += 1
        if max(r, g, b) - min(r, g, b) < 24:  # white / grey / black (anti-aliasing, background)
            continue
        key = (r >> 4, g >> 4, b >> 4)
        buckets[key] += 1
        s = sums[key]
        s[0] += r
        s[1] += g
        s[2] += b
    print(f"{width}x{height} px, {ch} channels, {opaque} opaque pixels, {sum(buckets.values())} chromatic")
    for key, n in buckets.most_common(12):
        s = sums[key]
        avg = (round(s[0] / n), round(s[1] / n), round(s[2] / n))
        h, lt, sat = colorsys.rgb_to_hls(*(v / 255 for v in avg))
        print(
            f"#{avg[0]:02x}{avg[1]:02x}{avg[2]:02x}  n={n:6d}  "
            f"hsl({h * 360:5.1f}, {sat * 100:4.1f}%, {lt * 100:4.1f}%)  "
            f"contrast vs white {contrast(avg, (255, 255, 255)):.2f}:1"
        )


if __name__ == "__main__":
    main(
        sys.argv[1]
        if len(sys.argv) > 1
        else str(Path(__file__).resolve().parents[1] / "docs" / "ui" / "brand" / "aleekhan-logo.png")
    )
