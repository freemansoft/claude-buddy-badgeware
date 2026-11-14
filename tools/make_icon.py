#!/usr/bin/env python3
"""Generate apps/claude_buddy/icon.png (24x24 RGBA) for the Badgeware menu.

Standard library only (zlib + struct), so no Pillow is needed. Edit the
ART grid and re-run:

    python3 tools/make_icon.py

Legend: "#" black, "+" mid grey (one of the Badger's 4 levels),
"." transparent.
"""

import struct
import zlib
from pathlib import Path

# A speech bubble with a bold sparkle: 2 px outlines and a grey fill,
# matching the weight of the stock Badgeware launcher icons.
ART = [
    "........................",
    "..####################..",
    ".######################.",
    ".##++++++++++++++++++##.",
    ".##++++##++##++##++++##.",
    ".##+++++##+##+##+++++##.",
    ".##++++++######++++++##.",
    ".##+++++++####+++++++##.",
    ".##+++############+++##.",
    ".##+++############+++##.",
    ".##+++++++####+++++++##.",
    ".##++++++######++++++##.",
    ".##+++++##+##+##+++++##.",
    ".##++++##++##++##++++##.",
    ".##++++++++++++++++++##.",
    ".##++++++++++++++++++##.",
    ".######################.",
    "..####++##############..",
    ".....#+##...............",
    ".....###................",
    ".....##.................",
    ".....#..................",
    "........................",
    "........................",
]

PALETTE = {
    "#": (0, 0, 0, 255),
    "+": (128, 128, 128, 255),
    ".": (0, 0, 0, 0),
}


def _chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def build_png(rows):
    height = len(rows)
    width = len(rows[0])
    raw = bytearray()
    for row in rows:
        if len(row) != width:
            raise ValueError("ragged row: {!r}".format(row))
        raw.append(0)  # filter: none
        for ch in row:
            raw.extend(PALETTE[ch])
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def main():
    out = Path(__file__).resolve().parent.parent / "apps" / "claude_buddy" / "icon.png"
    out.write_bytes(build_png(ART))
    print("wrote", out)


if __name__ == "__main__":
    main()
