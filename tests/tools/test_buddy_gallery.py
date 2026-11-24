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
        size = make_buddy_art.BADGES[model]["size"]
        loaded, blits, updates = [], [], []

        def load(path):
            loaded.append(path)
            return types.SimpleNamespace(path=path, width=size, height=size)

        builtins.screen.blit = lambda img, *where: blits.append((img.path, where))
        builtins.image.load = load
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
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        runpy.run_path(str(buddy_gallery.DEVICE_SCRIPT), run_name="__main__")
        return loaded, blits, updates

    def test_loads_this_badges_images(self):
        for model in ("badger", "tufty"):
            loaded, _blits, _updates = self.run_gallery(model, [])
            self.assertEqual(loaded, ["/system/apps/claude_buddy/buddy_art/{}_{}.png".format(model, state)
                                      for state in make_buddy_art.STATES])

    def test_overview_then_each_state(self):
        _loaded, blits, updates = self.run_gallery("tufty", ["BUTTON_DOWN"] * 5 + [None, "BUTTON_UP"])
        self.assertEqual(updates, [5, 6, 7, 8, 9, 10, 11])  # 5 halves, then one per page
        # Five half-size thumbnails would fill the 320 px exactly, so they
        # shrink to leave gaps: (320 - 6 * 4) // 5 = 59 px.
        self.assertEqual(blits[0][1], (("rect", 0, 0, 128, 128), ("rect", 4, 90, 59, 59)))
        self.assertEqual([path.rsplit("/", 1)[-1] for path, _ in blits[5:10]],
                         ["tufty_{}.png".format(state) for state in make_buddy_art.STATES])
        self.assertTrue(blits[10][0].endswith("tufty_attention.png"))  # UP goes back one

    def test_every_page_fits_the_screen(self):
        for model, (w, h) in (("badger", (264, 176)), ("tufty", (320, 240))):
            size = make_buddy_art.BADGES[model]["size"]
            _loaded, blits, _updates = self.run_gallery(model, ["BUTTON_DOWN"] * 5)
            for _path, where in blits[:5]:  # the overview's thumbnails
                _tag, x, y, tw, th = where[1]
                self.assertTrue(0 < x and x + tw < w and 0 <= y and y + th <= h, (model, where))
            for _path, where in blits[5:]:  # full size
                _tag, x, y = where[0]
                self.assertTrue(0 <= x and x + size <= w and 0 <= y and y + size <= h, (model, where))


if __name__ == "__main__":
    unittest.main()
