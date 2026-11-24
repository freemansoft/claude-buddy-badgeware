"""Host-side tests for the case-light patterns (buddy_lights)."""

import unittest

import support  # noqa: F401 - puts apps/claude_buddy on sys.path

from buddy_lights import CaseLights

ON = 0.6


class CaseLightsTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.lights = CaseLights(
            self.calls.append, level=ON, ack_ms=150, blip_ms=120, gap_ms=120, repeat_ms=5000
        )

    def levels(self, times, attention=True):
        return [self.lights.tick(t, attention) for t in times]

    def test_dark_when_nothing_waiting(self):
        self.assertEqual(self.levels(range(0, 6000, 100), attention=False), [0] * 60)
        self.assertEqual(self.calls, [])  # never touched the hardware

    def test_double_blink_then_repeats_every_5s(self):
        # blip 0-119, gap 120-239, blip 240-359, dark until 5000.
        times = [0, 119, 120, 239, 240, 359, 360, 4999, 5000, 5240, 5360]
        self.assertEqual(
            self.levels(times), [ON, ON, 0, 0, ON, ON, 0, 0, ON, ON, 0]
        )

    def test_cycle_starts_when_waiting_starts(self):
        self.lights.tick(0, False)
        self.assertEqual(self.levels([1000, 1119, 1120, 1240]), [ON, ON, 0, ON])

    def test_stops_as_soon_as_answered(self):
        self.lights.tick(0, True)
        self.assertEqual(self.lights.tick(50, False), 0)
        self.assertEqual(self.calls, [ON, 0])
        # Waiting again later starts a fresh double blink right away.
        self.assertEqual(self.lights.tick(7000, True), ON)

    def test_ack_blink(self):
        self.lights.ack(1000)
        self.assertEqual(self.levels([1000, 1149, 1150], attention=False), [ON, ON, 0])

    def test_only_changes_reach_hardware(self):
        self.levels(range(0, 400, 10))
        self.assertEqual(self.calls, [ON, 0, ON, 0])

    def test_long_wait_keeps_cycling(self):
        # A day of waiting: still on the 5 s grid.
        day = 24 * 60 * 60 * 1000
        self.lights.tick(0, True)
        self.assertEqual(self.levels([day, day + 120, day + 240]), [ON, 0, ON])


if __name__ == "__main__":
    unittest.main()
