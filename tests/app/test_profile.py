"""Host tests for the per-badge profiles (buddy_profile)."""

import builtins
import unittest

import support  # noqa: F401 - puts apps/claude_buddy on sys.path
from support import ROOT

import buddy_profile as bp
import make_buddy_art

# Badgeware's display-mode flags, as builtins like on the badge, so the
# profiles' mode functions can run here.
builtins.HIRES = 0b01
builtins.FAST_UPDATE = 3 << 4
builtins.NON_BLOCKING = 0b100


class ProfileTest(unittest.TestCase):
    def test_one_profile_per_supported_model(self):
        self.assertEqual(sorted(bp.PROFILES), ["badger", "tufty"])
        for model, profile in bp.PROFILES.items():
            self.assertEqual(profile.model, model)

    def test_badger_uses_the_eink_rules_on_both_power_sources(self):
        # Every e-ink refresh is a 1-2 s flash: never live. Status
        # updates are throttled to 5 s on USB and 10 s on battery.
        b = bp.BADGER
        self.assertIs(b.refresh(True), bp.EINK_USB_REFRESH)
        self.assertIs(b.refresh(False), bp.EINK_REFRESH)
        for refresh, interval in ((b.refresh(True), 5000), (b.refresh(False), 10000)):
            self.assertEqual((refresh.settle_ms, refresh.status_interval_ms,
                              refresh.answer_hold_ms, refresh.no_sessions_delay_ms),
                             (300, interval, 1000, 5000))
            self.assertFalse(refresh.live)
        self.assertTrue(b.eink)
        self.assertEqual(b.mode(), FAST_UPDATE | NON_BLOCKING)
        self.assertIsNone(b.backlight)
        self.assertFalse(b.run_clears_screen or b.run_polls_buttons)
        self.assertEqual(set(b.theme.values()) - {"white"}, {"black"})

    def test_tufty_is_live_on_usb_and_eink_on_battery(self):
        t = bp.TUFTY
        self.assertIs(t.refresh(True), bp.LIVE_REFRESH)
        self.assertIs(t.refresh(False), bp.EINK_REFRESH)  # fewer redraws on battery

    def test_live_refresh_has_no_delays(self):
        r = bp.LIVE_REFRESH
        self.assertTrue(r.live)
        self.assertEqual((r.settle_ms, r.status_interval_ms, r.answer_hold_ms,
                          r.no_sessions_delay_ms), (0, 0, 0, 0))

    def test_tufty_badgeware_quirks_and_backlight(self):
        t = bp.TUFTY
        self.assertFalse(t.eink)
        self.assertEqual(t.mode(), HIRES)
        self.assertTrue(t.run_clears_screen and t.run_polls_buttons)
        self.assertEqual((t.backlight.bright, t.backlight.dim, t.backlight.idle_ms),
                         (0.9, 0.1, 60000))


if __name__ == "__main__":
    unittest.main()


class BuddyProfileTest(unittest.TestCase):
    def test_only_the_tufty_has_a_buddy(self):
        # The Badger stays text-only (docs/buddies.md).
        self.assertIsNone(bp.BADGER.buddy)
        self.assertIsNotNone(bp.TUFTY.buddy)

    def test_tufty_buddy_matches_the_generated_pictures(self):
        buddy = bp.TUFTY.buddy
        self.assertEqual(buddy.size, make_buddy_art.BADGES["tufty"]["size"])
        for state in make_buddy_art.STATES:
            path = buddy.path.format(state)
            self.assertTrue(path.startswith("/system/apps/claude_buddy/buddy_art/"), path)
            name = path.rsplit("/", 1)[-1]
            self.assertTrue((ROOT / "apps" / "claude_buddy" / "buddy_art" / name).is_file(), name)
