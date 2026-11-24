#!/usr/bin/env python3
"""Draw the buddy, an orange blob, as one still PNG per state.

    python3 tools/make_buddy_art.py            write apps/claude_buddy/buddy_art/
    python3 tools/make_buddy_art.py --check    fail if those files are out of date
    python3 tools/make_buddy_art.py --sheet DIR
                                               also write sheet_<badge>.png previews

The blob is an original character for this project, in Claude's colours;
it isn't Anthropic's mascot. Every state has the same body width, so the
buddy takes the same room on screen whatever it's doing:

    sleep      squashed flatter, eyes closed, "zZ" above
    idle       round eyes, small smile
    busy       glancing up at two meshing gears, mouth to one side
    attention  wide eyes, small "o" mouth, "!?" above
    celebrate  happy "^ ^" eyes, open grin, a party hat and confetti

Only the Tufty has a buddy: a 96 px colour blob (BADGES). The Badger's
e-ink has none; see docs/buddies.md for why. Pixels outside the blob
are transparent, so the images sit on the screen's background.

Shapes are described on a 0..1 canvas and rasterised with 4x4
supersampling. Standard library only (zlib + struct), like
tools/make_icon.py.
"""

import argparse
import math
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "apps" / "claude_buddy" / "buddy_art"
STATES = ("sleep", "idle", "busy", "attention", "celebrate")
SS = 4  # supersampling per axis

# Per badge with a buddy: image size in pixels and a colour per shape
# role. The Badger has none (docs/buddies.md).
BADGES = {
    "tufty": {
        "size": 96,
        "colours": {
            "body": (217, 119, 87),  # Claude orange, as the Tufty theme's titles
            "face": (40, 24, 20),
            "mark": (255, 255, 255),
            "hole": None,  # see-through: the background shows
        },
    },
}

# Every state has the same body width. Sleep is squashed flatter.
WIDTH = 0.35
BODY = {"cy": 0.64, "rx": WIDTH, "ry": 0.27}
SLEEP_BODY = {"cy": 0.67, "rx": WIDTH, "ry": 0.22}


# -- shapes: (role, bbox, inside(x, y)) ----------------------------------------


def squircle(role, cx, cy, rx, ry, n=2.6):
    def inside(x, y):
        return abs((x - cx) / rx) ** n + abs((y - cy) / ry) ** n <= 1

    return role, (cx - rx, cy - ry, cx + rx, cy + ry), inside


def ellipse(role, cx, cy, rx, ry):
    return squircle(role, cx, cy, rx, ry, 2)


def capsule(role, ax, ay, bx, by, r):
    """A line from (ax, ay) to (bx, by), ``r`` thick each side, round ends."""
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy or 1e-9

    def inside(x, y):
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length2))
        px, py = ax + t * dx - x, ay + t * dy - y
        return px * px + py * py <= r * r

    return role, (min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r), inside


def polyline(role, points, r):
    return [capsule(role, *points[i], *points[i + 1], r) for i in range(len(points) - 1)]


def arc(role, cx, cy, rx, ry, a0, a1, r, steps=12):
    """An elliptical arc from angle a0 to a1 (degrees, clockwise from 3 o'clock)."""
    points = [
        (cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
         cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / steps)))
        for i in range(steps + 1)
    ]
    return polyline(role, points, r)


def polygon(role, points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]

    def inside(x, y):
        hit = False
        j = len(points) - 1
        for i, (xi, yi) in enumerate(points):
            xj, yj = points[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                hit = not hit
            j = i
        return hit

    return role, (min(xs), min(ys), max(xs), max(ys)), inside


def sparkle(role, cx, cy, s):
    """A four-pointed star."""
    t = s * 0.28
    return polygon(role, [(cx, cy - s), (cx + t, cy - t), (cx + s, cy), (cx + t, cy + t),
                          (cx, cy + s), (cx - t, cy + t), (cx - s, cy), (cx - t, cy - t)])


def gear(role, cx, cy, outer, teeth, phase=0.0, depth=0.3):
    """A disc of radius ``outer * (1 - depth)`` with square-ish teeth out
    to ``outer``."""
    base = outer * (1 - depth)

    def inside(x, y):
        dx, dy = x - cx, y - cy
        r = math.hypot(dx, dy)
        if r <= base:
            return True
        return r <= outer and math.cos(teeth * (math.atan2(dy, dx) - phase)) > 0

    return role, (cx - outer, cy - outer, cx + outer, cy + outer), inside


def letter_z(role, x, y, w, r):
    return polyline(role, [(x, y), (x + w, y), (x, y + w), (x + w, y + w)], r)


def bang(role, cx, top, h, r):
    """A "!" ``h`` tall from ``top``."""
    return polyline(role, [(cx, top + r), (cx, top + h * 0.66)], r * 1.15) + [
        ellipse(role, cx, top + h - r * 1.1, r * 1.25, r * 1.25)]


def question(role, cx, top, h, r):
    """A "?" ``h`` tall from ``top``."""
    hook = h * 0.28
    end = (cx + hook * math.cos(math.radians(405)), top + hook + hook * math.sin(math.radians(405)))
    return (arc(role, cx, top + hook, hook, hook, 180, 405, r)
            + polyline(role, [end, (cx, top + h * 0.66)], r)
            + [ellipse(role, cx, top + h - r * 1.1, r * 1.25, r * 1.25)])


# -- the buddy -------------------------------------------------------------------


def body(cx=0.5, cy=0.66, rx=WIDTH, ry=0.27):
    """The blob and its two little feet."""
    foot_y = cy + ry * 1.02  # well below the body, so they show
    return [
        ellipse("body", cx - rx * 0.48, foot_y, rx * 0.23, ry * 0.21),
        ellipse("body", cx + rx * 0.48, foot_y, rx * 0.23, ry * 0.21),
        squircle("body", cx, cy, rx, ry),
    ]


def grin(cx, cy, r):
    """An open grin: the bottom half of a disc."""
    return polygon("face", [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
                            for a in range(0, 181, 15)])


def scene(state):
    """The shapes for ``state``, back to front."""
    s = []
    if state == "sleep":
        s += body(**SLEEP_BODY)
        s += arc("face", 0.39, 0.64, 0.055, 0.035, 10, 170, 0.018)
        s += arc("face", 0.61, 0.64, 0.055, 0.035, 10, 170, 0.018)
        s += [ellipse("face", 0.5, 0.76, 0.025, 0.02)]
        s += letter_z("mark", 0.70, 0.12, 0.13, 0.022) + letter_z("mark", 0.60, 0.30, 0.08, 0.017)
    elif state == "idle":
        s += body(**BODY)
        s += [ellipse("face", 0.40, 0.60, 0.045, 0.07), ellipse("face", 0.60, 0.60, 0.045, 0.07)]
        s += arc("face", 0.5, 0.69, 0.07, 0.045, 20, 160, 0.018)
    elif state == "busy":
        s += body(**BODY)
        s += [ellipse("face", 0.45, 0.56, 0.04, 0.062), ellipse("face", 0.64, 0.56, 0.04, 0.062)]
        s += polyline("face", [(0.50, 0.715), (0.60, 0.695)], 0.016)
        big = (0.58, 0.21, 0.13)
        angle = math.radians(-35)
        dist = big[2] * 0.7 + 0.085 * 0.85  # the teeth mesh
        small = (big[0] + dist * math.cos(angle), big[1] + dist * math.sin(angle), 0.085)
        s += [gear("mark", *big, teeth=8), ellipse("hole", big[0], big[1], 0.035, 0.035)]
        s += [gear("mark", *small, teeth=6, phase=math.pi / 6), ellipse("hole", small[0], small[1], 0.022, 0.022)]
    elif state == "attention":
        s += body(**BODY)
        s += [ellipse("face", 0.40, 0.58, 0.06, 0.07), ellipse("face", 0.60, 0.58, 0.06, 0.07)]
        s += [ellipse("body", 0.42, 0.56, 0.018, 0.018), ellipse("body", 0.62, 0.56, 0.018, 0.018)]
        s += [ellipse("face", 0.5, 0.72, 0.032, 0.036)]
        s += bang("mark", 0.42, 0.05, 0.28, 0.03) + question("mark", 0.57, 0.05, 0.28, 0.03)
    elif state == "celebrate":
        s += body(**BODY)
        top = BODY["cy"] - BODY["ry"]
        s += [polygon("mark", [(0.40, top + 0.03), (0.62, top + 0.03), (0.56, 0.10)])]  # party hat
        s += polyline("hole", [(0.43, top - 0.03), (0.60, top - 0.07)], 0.012)  # its stripes
        s += polyline("hole", [(0.48, 0.24), (0.58, 0.215)], 0.011)
        s += [ellipse("mark", 0.56, 0.085, 0.045, 0.045)]  # pom-pom
        s += [polygon("mark", [(x - 0.022, y - 0.01), (x + 0.022, y - 0.022), (x + 0.022, y + 0.01),
                               (x - 0.022, y + 0.022)]) for x, y in ((0.24, 0.20), (0.80, 0.14))]
        s += [ellipse("mark", x, y, 0.016, 0.016) for x, y in ((0.30, 0.10), (0.74, 0.27), (0.36, 0.30))]
        s += [sparkle("mark", 0.80, 0.34, 0.045), sparkle("mark", 0.20, 0.34, 0.04)]
        s += polyline("face", [(0.34, 0.62), (0.40, 0.55), (0.46, 0.62)], 0.02)
        s += polyline("face", [(0.54, 0.62), (0.60, 0.55), (0.66, 0.62)], 0.02)
        s += [grin(0.5, 0.69, 0.08)]
    else:
        raise ValueError("unknown state: {}".format(state))
    return s


# -- raster and PNG ------------------------------------------------------------------


def render(state, badge):
    """Rows of (r, g, b, a) for ``state`` on ``badge``."""
    spec = BADGES[badge]
    size, colours = spec["size"], spec["colours"]
    shapes = scene(state)
    n = size * SS
    rows = []
    for py in range(size):
        row = []
        for px in range(size):
            rgb = [0, 0, 0]
            covered = 0
            for sy in range(SS):
                y = (py * SS + sy + 0.5) / n
                for sx in range(SS):
                    x = (px * SS + sx + 0.5) / n
                    colour = None
                    for role, (x0, y0, x1, y1), inside in shapes:
                        if x0 <= x <= x1 and y0 <= y <= y1 and inside(x, y):
                            colour = colours[role]
                    if colour is not None:
                        covered += 1
                        for i in range(3):
                            rgb[i] += colour[i]
            alpha = covered / (SS * SS)
            if not covered:
                row.append((0, 0, 0, 0))
            else:
                row.append(tuple(int(v / covered) for v in rgb) + (int(alpha * 255 + 0.5),))
        rows.append(row)
    return rows


def png(rows):
    """An RGBA PNG of ``rows`` (as tools/make_icon.py writes)."""
    height, width = len(rows), len(rows[0])
    raw = bytearray()
    for row in rows:
        raw.append(0)  # filter: none
        for pixel in row:
            raw.extend(pixel)

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def filename(badge, state):
    return "{}_{}.png".format(badge, state)


def sheet(images, background, gap=16):
    """The images side by side on ``background``, for previews."""
    height = max(len(i) for i in images) + 2 * gap
    width = sum(len(i[0]) for i in images) + gap * (len(images) + 1)
    out = [[background + (255,)] * width for _ in range(height)]
    x = gap
    for image in images:
        for y, row in enumerate(image):
            for dx, (r, g, b, a) in enumerate(row):
                if a:
                    k = a / 255
                    mixed = (int(c * k + bg * (1 - k)) for c, bg in zip((r, g, b), background, strict=True))
                    out[gap + y][x + dx] = (*mixed, 255)
        x += len(image[0]) + gap
    return out


def build():
    """{file name: PNG bytes} for every badge and state."""
    return {filename(badge, state): png(render(state, badge)) for badge in BADGES for state in STATES}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if the PNGs in the app are out of date")
    parser.add_argument("--sheet", metavar="DIR", help="also write preview sheets to DIR")
    args = parser.parse_args()

    files = build()
    if args.check:
        stale = [name for name, data in files.items()
                 if not (OUT / name).is_file() or (OUT / name).read_bytes() != data]
        if stale:
            sys.exit("Out of date: {}. Run python3 tools/make_buddy_art.py".format(", ".join(stale)))
        print("The buddy art matches tools/make_buddy_art.py.")
        return
    OUT.mkdir(exist_ok=True)
    for name, data in files.items():
        (OUT / name).write_bytes(data)
    print("Wrote {} images to {}".format(len(files), OUT.relative_to(ROOT)))
    if args.sheet:
        folder = Path(args.sheet)
        folder.mkdir(parents=True, exist_ok=True)
        for badge, background in (("tufty", (0, 0, 0)),):
            images = [render(state, badge) for state in STATES]
            (folder / "sheet_{}.png".format(badge)).write_bytes(png(sheet(images, background)))
        print("Wrote preview sheets to", folder)


if __name__ == "__main__":
    main()
