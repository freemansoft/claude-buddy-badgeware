"""Runs on the badge (tools/buddy_gallery.py sends it with mpremote):
shows each buddy's still poses on the real panel, to judge them by eye.

    DOWN / UP   next / previous page (a species per page, or more pages
                if its five poses don't fit)
    B / A       next / previous font
    C           stop; tools/buddy_gallery.py then restarts the badge

Uses the app's own files from /system/apps/claude_buddy (buddy_species,
buddy_sprite, buddy_profile, buddy_view), so install the app first.
Prints a GALLERY line with the RAM the species table takes, and one per
font with the cell it measured.
"""

import gc
import sys
import time

import badgeware  # noqa: F401 - sets up badge, screen, display, font, color

APP_DIR = "/system/apps/claude_buddy"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

gc.collect()
_free = gc.mem_free()
from buddy_species import SPECIES, STATES  # noqa: E402

gc.collect()
print("GALLERY species table: {} bytes of RAM, {} free".format(_free - gc.mem_free(), gc.mem_free()))

from buddy_profile import MONA, PROFILES  # noqa: E402
from buddy_sprite import cells, pitch_for, place, width_px  # noqa: E402
from buddy_view import _color, _face, _markup_active, escape  # noqa: E402

# Fonts to compare, smallest cell first (see the pitch table in
# docs/buddies.md). MonaSans is the Tufty's app font.
FONTS = {
    "badger": ("sins", "teatime", "kobold", "hungry", "nope"),
    "tufty": ("sins", "teatime", "nope", (MONA, 12), (MONA, 14), (MONA, 16)),
}
GAP = 4  # pixels between poses (4 fit a page on the Badger at 7 px cells)
NAMES = list(SPECIES)

profile = PROFILES[badge.model]
badge.mode(profile.mode())
fg = _color(profile.theme["fg"])
bg = _color(profile.theme["bg"])
markup = None


class Font:
    def __init__(self, choice):
        self.name = choice if isinstance(choice, str) else "MonaSans {}".format(choice[1])
        self.face = _face((choice,))
        self.use()
        self.pitch = pitch_for(self.measure)
        self.line_h = self.face.height
        print("GALLERY font {}: cell {} x {} px".format(self.name, self.pitch, self.line_h))

    def use(self):
        screen.font = self.face.font

    def esc(self, text):
        return escape(text) if markup else text

    def measure(self, text):
        if self.face.size:
            return screen.measure_text(self.esc(text), font_size=self.face.size)[0]
        return screen.measure_text(self.esc(text))[0]

    def text(self, text, x, y):
        if self.face.size:
            screen.text(self.esc(text), int(x), int(y), font_size=self.face.size)
        else:
            screen.text(self.esc(text), int(x), int(y))


def _cell_w(name, f):
    """Room for the widest of a species' poses in font ``f``."""
    return width_px(max(cells(name, state)[1][0] for state in STATES), f.pitch) + GAP


def pages(f):
    """[(species, [states])]: each species' poses, split into pages that
    fit the screen in font ``f``."""
    top = f.line_h + GAP
    out = []
    for name in NAMES:
        cell_w = _cell_w(name, f)
        cell_h = f.line_h + 5 * f.line_h + GAP  # label + pose
        per_row = max(1, (screen.width + GAP) // cell_w)
        per_page = per_row * max(1, (screen.height - top) // cell_h)
        for i in range(0, len(STATES), per_page):
            out.append((name, list(STATES[i:i + per_page])))
    return out


def draw(f, page, number, total):
    name, states = page
    screen.pen = bg
    screen.clear()
    screen.pen = fg
    f.use()
    f.text("{} {}/{}  {} ({}x{})".format(name, number, total, f.name, f.pitch, f.line_h), 2, 0)
    colour = color.rgb(*SPECIES[name][0]) if not profile.eink else fg
    cell_w = _cell_w(name, f)
    per_row = max(1, (screen.width + GAP) // cell_w)
    for i, state in enumerate(states):
        x = (i % per_row) * cell_w
        y = f.line_h + GAP + (i // per_row) * (6 * f.line_h + GAP)
        screen.pen = fg
        f.text(state, x, y)
        grid, _size = cells(name, state)
        screen.pen = colour
        for ch, cx, cy in place(grid, x, y + f.line_h, f.pitch, f.line_h, f.measure):
            f.text(ch, cx, cy)
    display.update()
    busy = getattr(display, "busy", None)
    while callable(busy) and busy():
        time.sleep_ms(10)


def main():
    global markup
    fonts = {}
    font_no = 0
    page_no = 0

    def font(n):
        choice = FONTS[badge.model][n]
        if n not in fonts:
            fonts[n] = Font(choice)
        return fonts[n]

    f = font(0)
    screen.font = f.face.font
    markup = _markup_active()
    all_pages = pages(f)
    draw(f, all_pages[0], 1, len(all_pages))
    while True:
        badge.poll()
        if badge.pressed(BUTTON_C):
            print("GALLERY done")
            return
        step = 1 if badge.pressed(BUTTON_DOWN) else -1 if badge.pressed(BUTTON_UP) else 0
        change = 1 if badge.pressed(BUTTON_B) else -1 if badge.pressed(BUTTON_A) else 0
        if change:
            name = all_pages[page_no][0]
            font_no = (font_no + change) % len(FONTS[badge.model])
            f = font(font_no)
            all_pages = pages(f)
            page_no = [p[0] for p in all_pages].index(name)
        elif step:
            page_no = (page_no + step) % len(all_pages)
        else:
            time.sleep_ms(20)
            continue
        draw(f, all_pages[page_no], page_no + 1, len(all_pages))


main()
