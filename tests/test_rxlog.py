"""Host-side tests for the optional receive log (buddy_rxlog)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "claude_buddy"))

from buddy_rxlog import RxLog  # noqa: E402


class RxLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "rx.log")

    def tearDown(self):
        self.tmp.cleanup()

    def enable(self):
        open(self.path, "w").close()

    def read(self):
        with open(self.path) as f:
            return f.read().splitlines()

    def test_off_when_file_missing(self):
        log = RxLog(self.path)
        self.assertFalse(log.enabled)
        log.note(0, "RX", b'{"total":1}')
        self.assertFalse(log.service(10000, force=True))
        self.assertFalse(os.path.exists(self.path))  # never creates it

    def test_buffers_until_flush_interval(self):
        self.enable()
        log = RxLog(self.path, flush_ms=2000)
        log.note(100, "RX", b'{"total":1}')
        log.note(500, "--", "connect")
        self.assertFalse(log.service(2099))
        self.assertEqual(self.read(), [])
        self.assertTrue(log.service(2100))
        self.assertEqual(self.read(), ['100 RX {"total":1}', "500 -- connect"])

    def test_force_flushes_now(self):
        self.enable()
        log = RxLog(self.path)
        log.note(0, "TX", {"cmd": "permission", "id": "r1", "decision": "once"})
        self.assertTrue(log.service(1, force=True))
        self.assertEqual(len(self.read()), 1)
        self.assertIn("'decision': 'once'", self.read()[0])

    def test_line_cut_and_newlines_escaped(self):
        self.enable()
        log = RxLog(self.path, line_max=10)
        log.note(0, "RX", b"abcdefghijKLMNOP")
        log.note(0, "RX", "a\nb\rc")
        log.service(0, force=True)
        self.assertEqual(self.read(), ["0 RX abcdefghij", "0 RX a\\nb\\rc"])

    def test_bad_utf8_logged_as_repr(self):
        self.enable()
        log = RxLog(self.path)
        log.note(0, "RX", b"\xff\xfe")
        log.service(0, force=True)
        self.assertEqual(self.read(), ["0 RX b'\\xff\\xfe'"])

    def test_overflow_counts_dropped_lines(self):
        self.enable()
        log = RxLog(self.path, max_pending=2)
        for i in range(5):
            log.note(i, "RX", str(i))
        log.service(9, force=True)
        self.assertEqual(
            self.read(), ["0 RX 0", "1 RX 1", "9 -- 3 lines dropped (buffer full)"]
        )

    def test_repeated_lines_skipped_and_counted(self):
        self.enable()
        log = RxLog(self.path)
        hb = b'{"total":1,"waiting":0}'
        status = b'{"cmd":"status"}'
        # Heartbeats repeat, interleaved with status polls.
        for i, line in enumerate((hb, hb, status, hb, hb, status, hb)):
            log.note(i, "RX", line)
        log.note(7, "RX", b'{"total":1,"waiting":1}')
        log.note(8, "TX", "decision")  # TX is never skipped
        log.note(9, "TX", "decision")
        log.service(9, force=True)
        self.assertEqual(
            self.read(),
            [
                '0 RX {"total":1,"waiting":0}',
                "2 -- 1 repeated lines skipped",
                '2 RX {"cmd":"status"}',
                "7 -- 4 repeated lines skipped",
                '7 RX {"total":1,"waiting":1}',
                "8 TX decision",
                "9 TX decision",
            ],
        )

    def test_line_seen_long_ago_is_logged_again(self):
        self.enable()
        log = RxLog(self.path, recent_max=2)
        for i, text in enumerate(("a", "b", "c", "a")):
            log.note(i, "RX", text)
        log.service(9, force=True)
        self.assertEqual(self.read(), ["0 RX a", "1 RX b", "2 RX c", "3 RX a"])

    def test_full_file_moved_to_old(self):
        with open(self.path, "w") as f:
            f.write("x" * 100)
        with open(self.path + ".old", "w") as f:
            f.write("older")
        log = RxLog(self.path, max_bytes=50)
        log.note(0, "RX", "new")
        log.service(0, force=True)
        self.assertEqual(self.read(), ["0 RX new"])
        with open(self.path + ".old") as f:
            self.assertEqual(f.read(), "x" * 100)

    def test_deleting_file_turns_logging_off(self):
        self.enable()
        log = RxLog(self.path)
        log.note(0, "RX", "one")
        os.remove(self.path)
        self.assertFalse(log.service(0, force=True))
        self.assertFalse(log.enabled)
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
