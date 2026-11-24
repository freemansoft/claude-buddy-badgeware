"""Host tests for tools/buddy_gallery.py and the script it runs on the
badge (tools/buddy_gallery_device.py). The device script can only be
judged on a real panel, so this runs it once against stand-ins for the
Badgeware builtins, pressing every button, to catch mistakes that would
otherwise only show on the badge."""

import builtins
import gc
import runpy
import sys
import time
import types
import unittest
from unittest import mock

import support  # noqa: F401 - puts tools/ and the app on sys.path
from app.display.test_view import FakeScreen, install_badgeware_stubs

import buddy_gallery
import buddy_species

BUTTONS = ("BUTTON_A", "BUTTON_B", "BUTTON_C", "BUTTON_UP", "BUTTON_DOWN")


class FakeBadge:
    """Presses ``presses`` one per poll (None for a poll with nothing
    pressed)."""

    def __init__(self, model, presses):
        self.model = model
        self.presses = list(presses)
        self.current = None
        self.modes = []

    def mode(self, value=None):
        self.modes.append(value)

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
        badge = FakeBadge(model, presses)
        updates = []
        stubs = {name: name for name in BUTTONS}
        stubs.update(
            badge=badge,
            display=types.SimpleNamespace(update=lambda: updates.append(list(builtins.screen.drawn)),
                                          busy=lambda: False),
            FAST_UPDATE=3 << 4, NON_BLOCKING=1 << 9, HIRES=1,
        )
        if model == "tufty":
            builtins.screen = FakeScreen()
            builtins.screen.width, builtins.screen.height = 320, 240
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
        return updates

    def test_pages_fonts_and_stops(self):
        presses = ["BUTTON_DOWN", None, "BUTTON_UP", "BUTTON_UP", "BUTTON_B", "BUTTON_A", "BUTTON_C"]
        updates = self.run_gallery("badger", presses)
        self.assertEqual(len(updates), 6)  # first page, then one per press before C
        first = updates[0]
        self.assertTrue(first[0][0].startswith("axolotl 1/"))
        self.assertIn(("sleep", 0, first[1][2]), first)  # the first label, left edge
        self.assertTrue(updates[2][0][0].startswith("axolotl 1/"))  # back up
        self.assertTrue(updates[3][0][0].startswith("turtle"))  # UP from the first page wraps

    def test_runs_on_the_tufty(self):
        updates = self.run_gallery("tufty", ["BUTTON_B", "BUTTON_B", "BUTTON_B", "BUTTON_C"])
        self.assertEqual(len(updates), 4)

    def test_every_page_draws(self):
        # Including the robot's "[", which must be escaped for the
        # firmware's text markup (FakeScreen fails on a bare one).
        updates = self.run_gallery("badger", ["BUTTON_DOWN"] * 100 + ["BUTTON_C"])
        headers = [u[0][0] for u in updates]
        total = int(headers[0].split()[1].split("/")[1])
        self.assertEqual(len({h.split()[0] for h in headers}), 18)
        labels = [text for u in updates[:total] for text, _x, _y in u if text in buddy_species.STATES]
        self.assertEqual(len(labels), 18 * 5)  # every pose once per round


if __name__ == "__main__":
    unittest.main()
