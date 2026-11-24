"""Host tests for tools/badge_info.py: reading its tagged output line
and the mpremote call it makes. No badge needed."""

import unittest

import support  # noqa: F401 - puts tools/ on sys.path

import badge_info


class ParseInfoTest(unittest.TestCase):
    def test_finds_the_info_line_among_other_output(self):
        out = 'some warning\nBADGE_INFO {"model": "tufty", "bluetooth": true}\n'
        self.assertEqual(badge_info.parse_info(out), {"model": "tufty", "bluetooth": True})

    def test_missing_line_is_an_error(self):
        with self.assertRaises(ValueError):
            badge_info.parse_info("Traceback ...")


class RestartTest(unittest.TestCase):
    def test_badge_info_restarts_the_badge_after_reading_it(self):
        # mpremote stops the running program; without a reset the badge
        # sits on a frozen screen until someone presses RESET.
        cmd = badge_info.mpremote_command("/dev/cu.usbmodem201401")
        self.assertEqual(cmd[:4], ["mpremote", "connect", "/dev/cu.usbmodem201401", "exec"])
        self.assertEqual(cmd[-1], "reset")

    def test_no_restart_leaves_it_stopped(self):
        self.assertNotIn("reset", badge_info.mpremote_command("/dev/x", restart=False))


if __name__ == "__main__":
    unittest.main()
