"""Host tests for tools/buddy_gallery.py and the script it runs on the
badge (tools/buddy_gallery_device.py). The images can only be judged
on a real screen, so this runs the device script once against
stand-ins for the Badgeware builtins, paging through everything, to
catch mistakes that would otherwise only show on the badge."""

import builtins
import gc
import runpy
import sys
import time
import types
import unittest
from unittest import mock

import support  # noqa: F401 - puts tools/ and the app on sys.path
from app.display.test_view import install_badgeware_stubs

import buddy_gallery
import make_buddy_art

BUTTONS = ("BUTTON_A", "BUTTON_B", "BUTTON_C", "BUTTON_UP", "BUTTON_DOWN")


class FakeBadge:
    """Presses ``presses`` one per poll (None for a poll with nothing
    pressed), then C."""

    def __init__(self, model, presses):
        self.model = model
        self.presses = list(presses)
        self.current = None

    def mode(self, value=None):
        pass

    def poll(self):
        self.current = self.presses.pop(0) if self.presses else "BUTTON_C"

    def pressed(self, button):
        return button == self.current


class CommandTest(unittest.TestCase):
    def test_runs_the_device_script_then_restarts(self):
        cmd = buddy_gallery.mpremote_command("/dev/ttyACM0")
        self.assertEqual(cmd[:4], ["mpremote", "connect", "/dev/ttyACM0", "run"])
        self.assertTrue(cmd[4].endswith("buddy_gallery_device.py"))
        self.assertEqual(cmd[-1], "reset")


class DeviceScriptTest(unittest.TestCase):
    def run_gallery(self, model, presses):
        install_badgeware_stubs()
        if model == "tufty":
            builtins.screen.width, builtins.screen.height = 320, 240
        size = make_buddy_art.BADGES.get(model, {}).get("size", 0)
        loaded, blits, updates = [], [], []

        def load(path):
            loaded.append(path)
            return types.SimpleNamespace(path=path, width=size, height=size)

        builtins.screen.blit = lambda img, *where: blits.append((img.path, where))
        builtins.image.load = load
        has_art = model in make_buddy_art.BADGES

        def stat(_path):
            if not has_art:
                raise OSError(2, "no such file")
            return (0,) * 10

        stubs = {name: name for name in BUTTONS}
        stubs.update(
            badge=FakeBadge(model, presses),
            display=types.SimpleNamespace(update=lambda: updates.append(len(blits)), busy=lambda: False),
            rect=lambda *a: ("rect", *a),
            vec2=lambda *a: ("vec2", *a),
            FAST_UPDATE=3 << 4, NON_BLOCKING=1 << 9, HIRES=1,
        )
        patches = [mock.patch.object(builtins, name, value, create=True) for name, value in stubs.items()]
        patches += [
            mock.patch.dict(sys.modules, {"badgeware": types.ModuleType("badgeware")}),
            mock.patch.object(gc, "mem_free", lambda: 100000, create=True),
            mock.patch.object(time, "sleep_ms", lambda _ms: None, create=True),
            mock.patch("os.stat", stat),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        runpy.run_path(str(buddy_gallery.DEVICE_SCRIPT), run_name="__main__")
        return loaded, blits, updates

    def test_loads_the_tufty_images(self):
        loaded, _blits, _updates = self.run_gallery("tufty", [])
        self.assertEqual(loaded, ["/system/apps/claude_buddy/buddy_art/tufty_{}.png".format(state)
                                  for state in make_buddy_art.STATES])

    def test_stops_on_a_badger(self):
        # Only the Tufty has a buddy: nothing is loaded or drawn.
        loaded, blits, updates = self.run_gallery("badger", ["BUTTON_DOWN"])
        self.assertEqual((loaded, blits, updates), ([], [], []))

    def test_overview_then_each_state(self):
        n = len(make_buddy_art.STATES)
        _loaded, blits, updates = self.run_gallery("tufty", ["BUTTON_DOWN"] * n + [None, "BUTTON_UP"])
        self.assertEqual(updates, list(range(n, 2 * n + 2)))  # n thumbnails, then one per page
        size = make_buddy_art.BADGES["tufty"]["size"]
        thumb = min(size // 2, (320 - (n + 1) * 4) // n)  # half size, or less to leave gaps
        self.assertEqual(blits[0][1][0], ("rect", 0, 0, size, size))
        self.assertEqual(blits[0][1][1][3:], (thumb, thumb))
        self.assertEqual([path.rsplit("/", 1)[-1] for path, _ in blits[n:2 * n]],
                         ["tufty_{}.png".format(state) for state in make_buddy_art.STATES])
        self.assertTrue(blits[-1][0].endswith(make_buddy_art.filename("tufty", make_buddy_art.STATES[-2])))  # UP goes back one

    def test_every_page_fits_the_screen(self):
        w, h = 320, 240
        n = len(make_buddy_art.STATES)
        size = make_buddy_art.BADGES["tufty"]["size"]
        _loaded, blits, _updates = self.run_gallery("tufty", ["BUTTON_DOWN"] * (n - 1))
        for _path, where in blits[:n]:  # the overview's thumbnails
            _tag, x, y, tw, th = where[1]
            self.assertTrue(0 < x and x + tw < w and 0 <= y and y + th <= h, where)
        for _path, where in blits[n:]:  # full size
            _tag, x, y = where[0]
            self.assertTrue(0 <= x and x + size <= w and 0 <= y and y + size <= h, where)

if __name__ == "__main__":
    unittest.main()
