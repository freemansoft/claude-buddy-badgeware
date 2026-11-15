"""Host tests for the per-badge profiles (buddy_profile)."""

import builtins
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "claude_buddy"))

import buddy_profile as bp  # noqa: E402

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

    def test_every_profile_has_every_setting(self):
        for profile in bp.PROFILES.values():
            self.assertIsInstance(profile.mode(), int)
            self.assertEqual(len(profile.fonts), 3)  # bar, title, body
            self.assertEqual(set(profile.theme), {"bg", "fg", "title", "footer", "meta"})
            for refresh in (profile.refresh(True), profile.refresh(False)):
                self.assertIsInstance(refresh, bp.Refresh)

    def test_refresh_follows_the_power_source(self):
        usb = bp.Refresh(0, 0, 0)
        battery = bp.Refresh(300, 15000, 1000)
        profile = bp.Profile("x", lambda: 0, False, False, False, ((("a",),) * 3),
                             {}, None, refresh_usb=usb, refresh_battery=battery)
        self.assertIs(profile.refresh(True), usb)
        self.assertIs(profile.refresh(False), battery)

    def test_badger_uses_the_eink_rules_on_both_power_sources(self):
        # Every e-ink refresh is a 1-2 s flash: never relax these.
        b = bp.BADGER
        for refresh in (b.refresh(True), b.refresh(False)):
            self.assertEqual((refresh.settle_ms, refresh.status_interval_ms,
                              refresh.answer_hold_ms), (300, 15000, 1000))
        self.assertTrue(b.eink)
        self.assertEqual(b.mode(), FAST_UPDATE | NON_BLOCKING)
        self.assertIsNone(b.backlight)
        self.assertFalse(b.run_clears_screen or b.run_polls_buttons)
        self.assertEqual(set(b.theme.values()) - {"white"}, {"black"})

    def test_tufty_for_now_keeps_the_badger_refresh_rules(self):
        # The live LCD profile (on USB) isn't built yet.
        t = bp.TUFTY
        self.assertIs(t.refresh(True), bp.EINK_REFRESH)
        self.assertIs(t.refresh(False), bp.EINK_REFRESH)

    def test_tufty_badgeware_quirks_and_backlight(self):
        t = bp.TUFTY
        self.assertFalse(t.eink)
        self.assertEqual(t.mode(), HIRES)
        self.assertTrue(t.run_clears_screen and t.run_polls_buttons)
        self.assertEqual((t.backlight.bright, t.backlight.dim, t.backlight.idle_ms),
                         (0.9, 0.1, 60000))


if __name__ == "__main__":
    unittest.main()
