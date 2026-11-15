"""Host tests for the Tufty backlight dimming (buddy_backlight)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "claude_buddy"))

from buddy_backlight import Backlight  # noqa: E402

IDLE = 60000


class BacklightTest(unittest.TestCase):
    def setUp(self):
        self.levels = []
        self.bl = Backlight(self.levels.append, bright=0.9, dim=0.1, idle_ms=IDLE, now=0)

    def test_starts_bright(self):
        self.assertEqual(self.levels, [0.9])
        self.assertFalse(self.bl.dimmed)

    def test_dims_after_idle_on_battery(self):
        self.bl.tick(IDLE - 1, on_usb=False, keep_on=False)
        self.assertFalse(self.bl.dimmed)
        self.bl.tick(IDLE, on_usb=False, keep_on=False)
        self.assertTrue(self.bl.dimmed)
        self.assertEqual(self.levels, [0.9, 0.1])

    def test_never_dims_on_usb(self):
        for now in range(0, 5 * IDLE, 1000):
            self.bl.tick(now, on_usb=True, keep_on=False)
        self.assertFalse(self.bl.dimmed)
        self.assertEqual(self.levels, [0.9])

    def test_stays_bright_while_something_needs_the_user(self):
        for now in range(0, 5 * IDLE, 1000):
            self.bl.tick(now, on_usb=False, keep_on=True)
        self.assertFalse(self.bl.dimmed)
        # ...and the idle time counts from the last keep_on tick
        # (5 * IDLE - 1000).
        self.bl.tick(6 * IDLE - 1001, on_usb=False, keep_on=False)
        self.assertFalse(self.bl.dimmed)
        self.bl.tick(6 * IDLE - 1000, on_usb=False, keep_on=False)
        self.assertTrue(self.bl.dimmed)

    def test_keep_on_wakes_a_dim_screen(self):
        self.bl.tick(IDLE, on_usb=False, keep_on=False)
        self.bl.tick(IDLE + 10, on_usb=False, keep_on=True)  # a prompt arrives
        self.assertFalse(self.bl.dimmed)
        self.assertEqual(self.levels, [0.9, 0.1, 0.9])

    def test_plugging_in_usb_wakes_it(self):
        self.bl.tick(IDLE, on_usb=False, keep_on=False)
        self.bl.tick(IDLE + 10, on_usb=True, keep_on=False)
        self.assertFalse(self.bl.dimmed)

    def test_first_press_while_dim_only_wakes(self):
        self.bl.tick(IDLE, on_usb=False, keep_on=False)
        self.assertTrue(self.bl.press(IDLE + 10))  # swallowed
        self.assertFalse(self.bl.dimmed)
        self.assertFalse(self.bl.press(IDLE + 20))  # acts normally

    def test_press_resets_the_idle_time(self):
        self.bl.press(IDLE - 1000)
        self.bl.tick(IDLE + 1000, on_usb=False, keep_on=False)
        self.assertFalse(self.bl.dimmed)
        self.bl.tick(2 * IDLE - 1000, on_usb=False, keep_on=False)
        self.assertTrue(self.bl.dimmed)

    def test_only_changes_reach_the_hardware(self):
        for now in range(0, 3 * IDLE, 20):  # 50 ticks a second
            self.bl.tick(now, on_usb=False, keep_on=False)
        self.assertEqual(self.levels, [0.9, 0.1])

    def test_restore_on_exit(self):
        self.bl.tick(IDLE, on_usb=False, keep_on=False)
        self.bl.restore()
        self.assertEqual(self.levels[-1], 0.9)

    def test_no_backlight_is_a_no_op(self):
        bl = Backlight(None, bright=0.9, dim=0.1, idle_ms=IDLE)
        self.assertFalse(bl.enabled)
        bl.tick(10 * IDLE, on_usb=False, keep_on=False)
        self.assertFalse(bl.dimmed)
        self.assertFalse(bl.press(10 * IDLE))
        bl.restore()


if __name__ == "__main__":
    unittest.main()
