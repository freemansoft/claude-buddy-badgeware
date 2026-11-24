"""Runs on the badge (tools/buddy_gallery.py sends it with mpremote):
shows the buddy images on the real screen, to judge them by eye.

    page 1      all six states side by side, at half size
    pages 2-7   one state at full size, beside sample text, roughly
                where the app would put it
    DOWN / UP   next / previous page
    C           stop; tools/buddy_gallery.py then restarts the badge

Reads the images the app ships, /system/apps/claude_buddy/buddy_art/
<model>_<state>.png, so install the app first. Prints a GALLERY line
with each image's size and the RAM the six take. Only the Tufty has a
buddy; on a Badger it says so and stops.
"""

import gc
import os
import sys
import time

import badgeware  # noqa: F401 - sets up badge, screen, display, font, color, image

APP_DIR = "/system/apps/claude_buddy"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from buddy_profile import PROFILES  # noqa: E402
from buddy_view import _color, _face  # noqa: E402

STATES = ("sleep", "idle", "busy", "attention", "celebrate", "denied")
TITLES = {"sleep": "No sessions", "idle": "Idle", "busy": "Working", "attention": "Allow Bash?",
          "celebrate": "Approved Bash", "denied": "Denied Bash"}
SAMPLE = ("Claude's latest reply, wrapped", "beside the buddy so you can", "judge the balance.")
PAD = 4

profile = PROFILES[badge.model]
badge.mode(profile.mode())
fg = _color(profile.theme["fg"])
bg = _color(profile.theme["bg"])
title_pen = _color(profile.theme["title"])
body_face = _face(profile.fonts[2])
title_face = _face(profile.fonts[1])


def _has_art():
    try:
        os.stat("{}/buddy_art/{}_idle.png".format(APP_DIR, badge.model))
        return True
    except OSError:
        return False


art = {}
size = 0


def load_art():
    global size
    gc.collect()
    free = gc.mem_free()
    for state in STATES:
        art[state] = image.load("{}/buddy_art/{}_{}.png".format(APP_DIR, badge.model, state))
    gc.collect()
    size = art["idle"].width
    print("GALLERY {} images, {} x {} px, {} bytes of RAM".format(
        len(art), size, art["idle"].height, free - gc.mem_free()))


def text(face, s, x, y):
    screen.font = face.font
    if face.size:
        screen.text(s, int(x), int(y), font_size=face.size)
    else:
        screen.text(s, int(x), int(y))


def overview():
    """All six, scaled to half size or smaller so they fit in a row
    with gaps between. Every other label sits a line lower, so long
    names don't run into each other."""
    n = len(STATES)
    thumb = min(size // 2, (screen.width - (n + 1) * PAD) // n)
    gap = (screen.width - thumb * n) // (n + 1)
    y = (screen.height - thumb) // 2
    for i, state in enumerate(STATES):
        x = gap + i * (thumb + gap)
        screen.blit(art[state], rect(0, 0, size, size), rect(x, y, thumb, thumb))
        screen.pen = fg
        text(body_face, state, x, y + thumb + PAD + (i % 2) * body_face.height)


def one(state):
    """The image at full size on the right, a title and sample text on
    the left, as the app might lay out a status screen."""
    x = screen.width - size - PAD
    y = (screen.height - size) // 2
    screen.blit(art[state], vec2(x, y))
    screen.pen = title_pen
    text(title_face, TITLES[state], PAD, PAD)
    screen.pen = fg
    for i, line in enumerate(SAMPLE):
        text(body_face, line, PAD, PAD + title_face.height + 6 + i * body_face.height)
    text(body_face, state, PAD, screen.height - body_face.height - PAD)


def draw(page):
    screen.pen = bg
    screen.clear()
    if page == 0:
        overview()
    else:
        one(STATES[page - 1])
    display.update()
    busy = getattr(display, "busy", None)
    while callable(busy) and busy():
        time.sleep_ms(10)


def main():
    if not _has_art():
        print("GALLERY no buddy pictures for the {} (only the Tufty has a buddy)".format(badge.model))
        return
    load_art()
    page = 0
    pages = 1 + len(STATES)
    draw(page)
    while True:
        badge.poll()
        if badge.pressed(BUTTON_C):
            print("GALLERY done")
            return
        step = 1 if badge.pressed(BUTTON_DOWN) else -1 if badge.pressed(BUTTON_UP) else 0
        if step:
            page = (page + step) % pages
            draw(page)
        else:
            time.sleep_ms(20)


main()
