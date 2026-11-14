"""Host-side tests for device modules, using stand-ins for the Badgeware
builtins (screen, font, ...) and MicroPython's bluetooth module.

Covers the parts that don't need hardware: text wrapping in the view,
and line framing in the BLE layer.
"""

import builtins
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "claude_buddy"))

CHAR_W = 6


class FakeScreen:
    width = 264
    height = 176

    def __init__(self):
        self.drawn = []
        self.font = None
        self.pen = None

    def measure_text(self, text):
        # "[[" is one literal "[" once markup is parsed.
        return (len(text.replace("[[", "[")) * CHAR_W, 12)

    def text(self, text, x, y):
        self.drawn.append((text, x, y))

    def clear(self):
        self.drawn = []

    def rectangle(self, *args):
        pass


def install_badgeware_stubs():
    builtins.screen = FakeScreen()
    builtins.font = types.SimpleNamespace(
        sins=types.SimpleNamespace(height=12),
        nope=types.SimpleNamespace(height=13),
        winds=types.SimpleNamespace(height=12),
        absolute=types.SimpleNamespace(height=16),
    )
    builtins.color = types.SimpleNamespace(
        white="white", black="black", dark_grey="dark_grey", rgb=lambda *a: a
    )
    builtins.badge = types.SimpleNamespace(model="badger")
    builtins.image = types.SimpleNamespace(OFF=0)


def install_bluetooth_stub():
    class UUID:
        def __init__(self, s):
            self.s = s

        def __bytes__(self):
            return bytes(16)

    class BLE:
        def active(self, *a):
            return True

        def config(self, *a, **k):
            if a == ("mac",):
                return (0, b"\x00\x11\x22\xa1\xb2\xc3")
            return None

        def gatts_register_services(self, services):
            return ((10, 11),)

        def gatts_set_buffer(self, *a):
            pass

        def irq(self, handler):
            self.handler = handler

        def gap_advertise(self, *a, **k):
            pass

    bt = types.ModuleType("bluetooth")
    bt.UUID = UUID
    bt.BLE = BLE
    mp = types.ModuleType("micropython")
    mp.const = lambda x: x
    machine = types.ModuleType("machine")
    # Folds to A1B2C3: bytes 3..7 XOR to zero in each lane.
    machine.unique_id = lambda: bytes([0xA1, 0xB2, 0xC3, 0x5A, 0x3C, 0x00, 0x5A, 0x3C])
    sys.modules["bluetooth"] = bt
    sys.modules["micropython"] = mp
    sys.modules["machine"] = machine


install_badgeware_stubs()
install_bluetooth_stub()

import buddy_ble  # noqa: E402
import buddy_view  # noqa: E402


def make_scr(kind="status", title="Allow Bash?", lines=(), actionable=False,
             name="Claude_A1B2C3", status="Connected", battery="75%", tokens="", doc="d"):
    """A screen tuple in buddy_model's layout (see BuddyModel.screen)."""
    if kind == "status" and title == "Allow Bash?":
        title = "Idle"
    return (name, status, kind, actionable, title, tuple(lines), actionable,
            False, doc, battery == "USB", battery, tokens)


class WrapTest(unittest.TestCase):
    def setUp(self):
        self.view = buddy_view.BuddyView()
        self.width = 60  # 10 chars at CHAR_W

    def wrap(self, text, max_lines=10):
        return self.view.wrap(text, self.width, max_lines)

    def test_words_wrap(self):
        self.assertEqual(self.wrap("one two three four"), ["one two", "three four"])

    def test_long_token_hard_breaks_without_adding_characters(self):
        token = "/usr/local/bin/something"
        lines = self.wrap("rm " + token)
        self.assertEqual("".join(lines[1:]), token)
        for line in lines:
            self.assertLessEqual(len(line) * CHAR_W, self.width)

    def test_truncates_with_ellipsis(self):
        lines = self.wrap("aaaa bbbb cccc dddd eeee", max_lines=2)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("..."))
        self.assertLessEqual(len(lines[-1]) * CHAR_W, self.width)

    def test_exact_fit_has_no_ellipsis(self):
        self.assertEqual(self.wrap("aaaa bbbb", max_lines=1), ["aaaa bbbb"])

    def test_long_token_truncated_to_max_lines(self):
        lines = self.wrap("x" * 100, max_lines=2)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("..."))

    def test_empty(self):
        self.assertEqual(self.wrap(""), [])
        self.assertEqual(self.wrap("   "), [])

    def test_brackets_measured_as_one_char(self):
        # "[abcdefgh]" is 10 visible chars: fits exactly.
        self.assertEqual(self.wrap("[abcdefgh]", 1), ["[abcdefgh]"])

    def test_plain_maps_unicode(self):
        self.assertEqual(buddy_view.plain("it’s “ok” …"), "it's \"ok\" ...")
        self.assertEqual(buddy_view.plain("café \U0001f600"), "café ?")
        self.assertEqual(buddy_view.plain("a\tb\nc"), "a b c")

    def test_escape(self):
        self.assertEqual(buddy_view.escape("[pen:1,2,3]x"), "[[pen:1,2,3]x")

    def test_draw_escapes_markup(self):
        scr = make_scr(kind="prompt", title="Allow Bash?",
                       lines=(("w", "echo [pen:0,0,0]"),), actionable=True)
        texts = self.draw_texts(scr)
        self.assertIn("A: Accept", texts)
        self.assertTrue(any("[[pen" in t for t in texts))
        self.assertFalse(any("[pen" in t.replace("[[", "") for t in texts))

    def draw_texts(self, scr, page=0):
        self.view.draw(scr, page)
        return [t for t, _, _ in screen.drawn]

    def test_header_shows_identifier_battery_status(self):
        scr = make_scr(lines=(("c", "0 running, 0 waiting"),), tokens="31k today")
        texts = self.draw_texts(scr)
        for expected in ("Claude_A1B2C3", "75%", "Connected", "0 running, 0 waiting, 31k today"):
            self.assertIn(expected, texts)

    def test_accept_deny_labels_only_when_answerable(self):
        texts = self.draw_texts(make_scr(kind="prompt", lines=(("w", "ls"),), actionable=True))
        for label in ("A: Accept", "B: Deny", "C: Exit"):
            self.assertIn(label, texts)
        texts = self.draw_texts(make_scr(lines=(("c", "0 running, 0 waiting"),)))
        self.assertNotIn("A: Accept", texts)
        self.assertNotIn("B: Deny", texts)
        self.assertIn("C: Exit", texts)

    def test_app_only_note_when_waiting_without_answerable_prompt(self):
        texts = self.draw_texts(make_scr(kind="waiting", title="Approval needed"))
        self.assertIn(buddy_view.APP_ONLY_NOTE, texts)
        self.assertIn("C: Exit", texts)
        self.assertNotIn("A: Accept", texts)
        (note_x,) = [x for t, x, _ in screen.drawn if t == buddy_view.APP_ONLY_NOTE]
        (exit_x,) = [x for t, x, _ in screen.drawn if t == "C: Exit"]
        note_w = len(buddy_view.APP_ONLY_NOTE) * CHAR_W
        self.assertLess(note_x + note_w, exit_x)  # never overlaps C: Exit

    def test_app_only_note_on_unanswerable_prompt(self):
        scr = make_scr(kind="prompt", status="No data", lines=(("w", "ls"),), actionable=False)
        texts = self.draw_texts(scr)
        self.assertIn(buddy_view.APP_ONLY_NOTE, texts)
        self.assertNotIn("A: Accept", texts)

    def test_app_only_note_not_on_other_screens(self):
        for scr in (make_scr(kind="prompt", lines=(("w", "ls"),), actionable=True),
                    make_scr(kind="status"), make_scr(kind="pair", title="")):
            self.assertNotIn(buddy_view.APP_ONLY_NOTE, self.draw_texts(scr), scr[2])

    def test_exit_label_stays_in_right_third(self):
        self.view.draw(make_scr(battery=""))
        (x,) = [x for t, x, _ in screen.drawn if t == "C: Exit"]
        self.assertGreaterEqual(x, 2 * (264 // 3))

    def test_tokens_only_on_counts_line(self):
        scr = make_scr(kind="prompt", lines=(("w", "ls"),), actionable=True, tokens="31k today")
        self.assertFalse(any("31k" in t for t in self.draw_texts(scr)))

    def test_identifier_never_truncated_when_header_is_tight(self):
        # 264 px / 6 px per char = 44 chars across; make it overflow.
        scr = make_scr(kind="pair", status="Not connected to anything at all",
                       title="", battery="100%")
        texts = self.draw_texts(scr)
        self.assertIn("Claude_A1B2C3", texts)
        self.assertNotIn("100%", texts)  # battery dropped first
        self.assertTrue(any(t.endswith("...") for t in texts))  # then status shortened


# Long prompt: 60 words of 9 chars -> ~5 words per 256 px line -> ~12 lines.
LONG = " ".join("word{:05d}".format(i) for i in range(60))


class PagingTest(unittest.TestCase):
    def setUp(self):
        self.view = buddy_view.BuddyView()

    def body_texts(self, scr, page):
        self.view.draw(scr, page)
        return [t for t, _, _ in screen.drawn]

    def test_short_content_is_one_page_without_marker(self):
        scr = make_scr(kind="prompt", lines=(("w", "ls -la"),), actionable=True)
        self.assertEqual(self.view.page_count(scr), 1)
        self.assertNotIn(buddy_view.PAGE_HINT, self.body_texts(scr, 0))

    def test_long_prompt_pages_show_everything_once(self):
        scr = make_scr(kind="prompt", lines=(("w", LONG),), actionable=True)
        pages = self.view.page_count(scr)
        self.assertGreater(pages, 1)
        seen = []
        for page in range(pages):
            texts = self.body_texts(scr, page)
            self.assertIn("Allow Bash?", texts)  # title on every page
            self.assertIn("{}/{}".format(page + 1, pages), texts)
            self.assertIn(buddy_view.PAGE_HINT, texts)
            seen += [w for t in texts for w in t.split() if w.startswith("word")]
        self.assertEqual(seen, LONG.split())  # nothing lost or repeated

    def test_rows_stay_above_footer_and_marker(self):
        scr = make_scr(kind="prompt", lines=(("w", LONG),), actionable=True)
        for page in range(self.view.page_count(scr)):
            self.view.draw(scr, page)
            for text, _, y in screen.drawn:
                if text.startswith("word"):
                    self.assertLessEqual(y + self.view.h_body,
                                         self.view.body_bottom - self.view.h_body)

    def test_page_out_of_range_is_clamped(self):
        scr = make_scr(kind="prompt", lines=(("w", LONG),), actionable=True)
        last = self.view.page_count(scr)
        texts = self.body_texts(scr, 99)
        self.assertIn("{}/{}".format(last, last), texts)


class FramingTest(unittest.TestCase):
    def setUp(self):
        self.ble = buddy_ble.BuddyBLE()

    def feed(self, *chunks):
        for c in chunks:
            self.ble._q.append(("rx", c))
        return self.ble.poll()

    def test_name_from_chip_unique_id(self):
        # XOR-fold of the stub's 8-byte unique ID into 3 bytes.
        self.assertEqual(self.ble.name, "Claude_A1B2C3")

    def test_id_suffix_is_stable_and_uses_all_bytes(self):
        uid = bytes(range(1, 9))
        self.assertEqual(buddy_ble.id_suffix(uid), buddy_ble.id_suffix(uid))
        other = bytes(range(1, 8)) + b"\x99"
        self.assertNotEqual(buddy_ble.id_suffix(uid), buddy_ble.id_suffix(other))
        self.assertEqual(len(buddy_ble.id_suffix(uid)), 6)

    def test_advertising_payloads_fit(self):
        self.assertLessEqual(len(self.ble._adv), 31)
        self.assertLessEqual(len(self.ble._resp), 31)

    def test_lines_split_across_chunks(self):
        out = self.feed(b'{"a":', b'1}\n{"b"', b":2}\n")
        self.assertEqual(out, [("line", b'{"a":1}'), ("line", b'{"b":2}')])

    def test_multiple_lines_in_one_chunk(self):
        out = self.feed(b"x\ny\n\nz")
        self.assertEqual(out, [("line", b"x"), ("line", b"y")])
        self.assertEqual(self.feed(b"\n"), [("line", b"z")])

    def test_overlong_line_dropped_then_recovers(self):
        big = b"q" * (buddy_ble._MAX_LINE + 10)
        out = self.feed(big[:4000], big[4000:], b"\nok\n")
        self.assertEqual(out, [("line", b"ok")])

    def test_connect_resets_partial_line(self):
        self.feed(b"partial")
        self.ble._q.append(("connect", None))
        out = self.feed(b"fresh\n")
        self.assertEqual(out, [("connect", None), ("line", b"fresh")])


if __name__ == "__main__":
    unittest.main()
