"""Host tests for the bootstrap tools (tools/badgeware_release.py,
tools/badge_info.py). No badge or network needed."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import badge_info  # noqa: E402
import badgeware_release as rel  # noqa: E402

# Real `mpremote devs` output with a Tufty and two other serial devices.
DEVS = """\
/dev/cu.Bluetooth-Incoming-Port None 0000:0000 None None
/dev/cu.usbmodem201401 bb713395bda7b3ab 2e8a:1101 Pimoroni Pimoroni Tufty 2350 MicroPython
/dev/cu.usbmodem20111101 e00fce68115b752338ceb4ef 2b04:c00d Particle Boron CDC Mode
"""

RELEASE = {
    "tag_name": "v3.1.1",
    "published_at": "2026-09-23T12:05:57Z",
    "assets": [
        {"name": "tufty-v3.1.1-micropython-with-filesystem.uf2", "size": 7057920},
        {"name": "tufty-v3.1.1-micropython.uf2", "size": 3576320},
    ],
}


class BadgePortsTest(unittest.TestCase):
    def test_finds_the_badge_and_ignores_other_boards(self):
        self.assertEqual(rel.badge_ports(DEVS), [("/dev/cu.usbmodem201401", "tufty")])

    def test_finds_a_badger(self):
        line = "/dev/ttyACM0 abc 2e8a:1100 Pimoroni Pimoroni Badger 2350 MicroPython"
        self.assertEqual(rel.badge_ports(line), [("/dev/ttyACM0", "badger")])

    def test_nothing_connected(self):
        self.assertEqual(rel.badge_ports(""), [])


class BuildDateTest(unittest.TestCase):
    def test_reads_the_date_from_uname_version(self):
        # As read from a Tufty on old firmware.
        version = "bw-1.27.0,   on 2026-04-10 (GNU 13.3.1 MinSizeRel)"
        self.assertEqual(rel.build_date(version), "2026-04-10")

    def test_no_date(self):
        self.assertIsNone(rel.build_date("bw-1.29.0-gc"))
        self.assertIsNone(rel.build_date(None))


class FirmwareStatusTest(unittest.TestCase):
    def test_older_build(self):
        self.assertEqual(rel.firmware_status("2026-04-10", "2026-09-23T12:05:57Z"), "older")

    def test_built_around_the_release_is_current(self):
        for built in ("2026-09-21", "2026-09-23", "2026-09-25"):
            self.assertEqual(rel.firmware_status(built, "2026-09-23"), "current", built)

    def test_newer_build(self):
        self.assertEqual(rel.firmware_status("2026-10-05", "2026-09-23"), "newer")

    def test_unknown_without_dates(self):
        self.assertEqual(rel.firmware_status(None, "2026-09-23"), "unknown")
        self.assertEqual(rel.firmware_status("2026-09-23", ""), "unknown")


class AssetTest(unittest.TestCase):
    def test_picks_each_flavour(self):
        self.assertEqual(rel.pick_asset(RELEASE, "tufty", False)["size"], 3576320)
        self.assertEqual(rel.pick_asset(RELEASE, "tufty", True)["size"], 7057920)

    def test_wrong_model_is_an_error(self):
        with self.assertRaises(LookupError):
            rel.pick_asset(RELEASE, "badger", False)

    def test_repo_per_model(self):
        self.assertEqual(rel.repo_for("tufty"), "pimoroni/tufty2350")
        self.assertEqual(rel.repo_for("badger"), "pimoroni/badger2350")


class Uf2Test(unittest.TestCase):
    def test_magic(self):
        self.assertTrue(rel.is_uf2(b"UF2\nWQ]\x9e" + b"\x00" * 24))
        self.assertFalse(rel.is_uf2(b"<!DOCTYPE html>"))  # an error page
        self.assertFalse(rel.is_uf2(b""))


class ParseInfoTest(unittest.TestCase):
    def test_finds_the_info_line_among_other_output(self):
        out = 'some warning\nBADGE_INFO {"model": "tufty", "bluetooth": true}\n'
        self.assertEqual(badge_info.parse_info(out), {"model": "tufty", "bluetooth": True})

    def test_missing_line_is_an_error(self):
        with self.assertRaises(ValueError):
            badge_info.parse_info("Traceback ...")


if __name__ == "__main__":
    unittest.main()
