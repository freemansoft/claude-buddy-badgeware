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
        self.rects = []
        self.sizes = []  # font_size of every measure and draw
        self.pens = {}  # text -> the pen it was drawn with
        self.font = None
        self.pen = None

    # True: firmware where "[" starts a glyph tag and "[[" is one literal
    # "[". False: firmware that draws brackets as they are (Badgeware
    # v3.1.1, as seen on a Tufty).
    markup = True

    def _check_escaped(self, text):
        # With markup, a lone "[" starts a glyph tag; the view must
        # escape it as "[[" before measuring or drawing.
        if self.markup and "[" in text.replace("[[", ""):
            raise AssertionError("unescaped markup: {!r}".format(text))

    def measure_text(self, text, font_size=0):
        self.sizes.append(font_size)
        if text in ("[", "[["):  # the view's markup probe
            return ((1 if self.markup else len(text)) * CHAR_W, 12)
        self._check_escaped(text)
        # With markup, "[[" is one literal "[".
        shown = text.replace("[[", "[") if self.markup else text
        return (len(shown) * CHAR_W, 12)

    def text(self, text, x, y, font_size=0):
        self._check_escaped(text)
        self.drawn.append((text, x, y))
        self.pens[text] = self.pen
        self.sizes.append(font_size)

    def clear(self):
        self.drawn = []
        self.rects = []
        self.pens = {}

    def rectangle(self, *args):
        self.rects.append(tuple(args))


# Vector font files the fake font.load() treats as missing.
MISSING_FONTS = set()


def _load_font(path):
    if path in MISSING_FONTS:
        raise OSError(2, "no such file")
    return types.SimpleNamespace(path=path)


def install_badgeware_stubs():
    builtins.screen = FakeScreen()
    builtins.font = types.SimpleNamespace(
        sins=types.SimpleNamespace(height=12),
        nope=types.SimpleNamespace(height=13),
        winds=types.SimpleNamespace(height=12),
        absolute=types.SimpleNamespace(height=16),
        smart=types.SimpleNamespace(height=16),
        curse=types.SimpleNamespace(height=20),
        load=_load_font,
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
import buddy_profile  # noqa: E402
import buddy_view  # noqa: E402


def make_scr(kind="status", title="Allow Bash?", lines=(), actionable=False,
             name="Claude_A1B2C3", status="Connected", battery="75%", tokens="", doc="d"):
    """A screen tuple in buddy_model's layout (see BuddyModel.screen)."""
    if kind == "status" and title == "Allow Bash?":
        title = "Idle"
    return (name, status, kind, actionable, title, tuple(lines), actionable,
            False, doc, battery == "USB", battery, tokens)


class WrapTest(unittest.TestCase):
    PROFILE = buddy_profile.BADGER

    def setUp(self):
        self.view = buddy_view.BuddyView(self.PROFILE)
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

    def test_no_escaping_where_firmware_has_no_markup(self):
        FakeScreen.markup = False
        self.addCleanup(setattr, FakeScreen, "markup", True)
        view = buddy_view.BuddyView(self.PROFILE)
        view.draw(make_scr(kind="status", lines=(("w", "[pen:1,2,3]x [ -f a ]"),)))
        texts = [t for t, _, _ in screen.drawn]
        self.assertTrue(any("[pen:1,2,3]x" in t for t in texts))
        self.assertFalse(any("[[" in t for t in texts))

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
        self.assertGreaterEqual(x, 2 * (self.view.w // 3))

    def test_charging_label_fits_header(self):
        for status in ("Connected", "Not connected", "No data"):
            texts = self.draw_texts(make_scr(kind="pair", title="", status=status,
                                             battery="Charging"))
            for expected in ("Claude_A1B2C3", "Charging", status):
                self.assertIn(expected, texts, status)

    # -- the not-connected frame -------------------------------------------

    PAIR_LINES = (("w", "In Claude Desktop: Developer > Open Hardware Buddy... > Connect"),
                  ("s", "Pick Claude_A1B2C3"))

    def frame_bars(self):
        """Rectangles other than the two 1 px full-width dividers."""
        return [r for r in screen.rects if not (r[2] == self.view.w and r[3] == 1)]

    def test_not_connected_screens_are_framed(self):
        for title in ("Pair with Claude", "Disconnected"):
            self.view.draw(make_scr(kind="pair", title=title, status="Not connected",
                                    lines=self.PAIR_LINES))
            bars = self.frame_bars()
            # Four sides plus the rule under the title.
            self.assertEqual(len(bars), 5, title)
            # Four FRAME_W sides and one TITLE_RULE_W rule.
            widths = sorted(min(w, h) for _, _, w, h in bars)
            self.assertEqual(widths, sorted([buddy_view.FRAME_W] * 4
                                            + [buddy_view.TITLE_RULE_W]), title)
            for x, y, w, h in bars:
                # Inset from the edges and dividers, with space round it.
                self.assertGreaterEqual(x, buddy_view.FRAME_MARGIN_X)
                self.assertLessEqual(x + w, self.view.w - buddy_view.FRAME_MARGIN_X)
                self.assertGreater(y, self.view.top_rule + buddy_view.FRAME_MARGIN_Y)
                self.assertLessEqual(y + h, self.view.bottom_rule - buddy_view.FRAME_MARGIN_Y)

    def test_connected_screens_are_not_framed(self):
        for scr in (make_scr(kind="status", lines=(("c", "0 running, 0 waiting"),)),
                    make_scr(kind="prompt", lines=(("w", "ls"),), actionable=True),
                    make_scr(kind="waiting", title="Approval needed"),
                    make_scr(kind="connected", title="Connected")):
            self.view.draw(scr)
            self.assertEqual(self.frame_bars(), [], scr[2])

    def test_framed_text_sits_inside_the_frame(self):
        self.view.draw(make_scr(kind="pair", title="Disconnected", status="Not connected",
                                lines=self.PAIR_LINES))
        x0, w, top, bottom = self.view.framed_area
        body = [(t, x, y) for t, x, y in screen.drawn
                if self.view.top_rule < y < self.view.bottom_rule]
        self.assertIn("Disconnected", [t for t, _, _ in body])
        self.assertIn("Pick Claude_A1B2C3", [t for t, _, _ in body])
        for text, x, y in body:
            self.assertGreaterEqual(x, x0, text)
            self.assertLessEqual(x + len(text) * CHAR_W, x0 + w, text)
            self.assertGreaterEqual(y, top, text)
            self.assertLessEqual(y, bottom, text)
        # Nothing is lost to the narrower area: the instructions still wrap
        # whole, with no word cut.
        joined = " ".join(t for t, _, _ in body)
        self.assertIn("Open Hardware", joined)

    def test_framed_title_is_centred_above_a_rule(self):
        self.view.draw(make_scr(kind="pair", title="Disconnected", status="Not connected",
                                lines=self.PAIR_LINES))
        x0, w, _, _ = self.view.framed_area
        pos = {t: (x, y) for t, x, y in screen.drawn}
        tx, ty = pos["Disconnected"]
        tw = len("Disconnected") * CHAR_W
        # Centred: equal space either side, to within a pixel.
        self.assertLessEqual(abs((tx - x0) - (x0 + w - tx - tw)), 1)
        # The rule is the one full-width horizontal bar that isn't the
        # frame's top or bottom; it lies between title and instructions.
        sides = sorted(self.frame_bars(), key=lambda r: r[1])
        horizontal = [r for r in sides if r[2] > r[3]]
        self.assertEqual(len(horizontal), 3)
        rule = horizontal[1]
        self.assertEqual(rule[3], buddy_view.TITLE_RULE_W)
        # The first instructions line (where it wraps depends on width).
        iy = min(y for t, (_, y) in pos.items() if t.startswith("In Claude Desktop"))
        self.assertGreater(rule[1], ty + self.view.h_title - 1)
        self.assertLess(rule[1] + rule[3], iy)
        # The instructions stay left-aligned.
        self.assertEqual(pos["Pick Claude_A1B2C3"][0], x0)

    def test_connected_titles_stay_left_aligned(self):
        for scr in (make_scr(kind="status", title="Done"),
                    make_scr(kind="prompt", title="Allow Bash?", lines=(("w", "ls"),))):
            self.view.draw(scr)
            x = {t: x for t, x, _ in screen.drawn}[scr[4]]
            self.assertEqual(x, self.view.body_x, scr[4])

        # The smaller area still holds everything on one page, so there's
        # no page marker and nothing to page through.
        scr = make_scr(kind="pair", title="Pair with Claude", status="Not connected",
                       lines=self.PAIR_LINES)
        self.assertEqual(self.view.page_count(scr), 1)

    def test_identifier_never_truncated_when_header_is_tight(self):
        # 264 px / 6 px per char = 44 chars across (53 on the Tufty's
        # 320 px); make it overflow on both.
        scr = make_scr(kind="pair", status="Not connected to anything at all, really",
                       title="", battery="100%")
        texts = self.draw_texts(scr)
        self.assertIn("Claude_A1B2C3", texts)
        self.assertNotIn("100%", texts)  # battery dropped first
        self.assertTrue(any(t.endswith("...") for t in texts))  # then status shortened


# Long prompt: 60 words of 9 chars -> ~5 words per 256 px line -> ~12 lines.
LONG = " ".join("word{:05d}".format(i) for i in range(60))


class TuftyViewTest(WrapTest):
    """Every WrapTest again on the Tufty: 320x240, with its own fonts
    and colours. The layout is derived from the screen size and font
    heights, so the same checks must hold. badge.model stays "badger":
    the view must take everything from the profile it's given."""

    PROFILE = buddy_profile.TUFTY

    def setUp(self):
        FakeScreen.width, FakeScreen.height = 320, 240
        buddy_view._loaded.clear()
        self.addCleanup(self._back_to_badger_size)
        super().setUp()

    @staticmethod
    def _back_to_badger_size():
        FakeScreen.width, FakeScreen.height = 264, 176

    def test_uses_the_tufty_size_fonts_and_colours(self):
        self.assertEqual((self.view.w, self.view.h), (320, 240))
        # MonaSans (vector) at 18 px bar, 24 px title, 20 px body.
        for face, size in ((self.view.f_bar, 18), (self.view.f_title, 24),
                           (self.view.f_body, 20)):
            self.assertEqual(face.font.path, buddy_profile.MONA)
            self.assertEqual((face.size, face.height), (size, size))
        self.assertEqual((self.view.theme.bg, self.view.theme.fg), ("black", "white"))
        # Taller fonts, so taller header and footer bars than the Badger's.
        self.assertEqual(self.view.top_rule, 18 + 4)
        self.assertEqual(self.view.bottom_rule, 240 - 22 - 1)

    def test_fixed_parts_are_coloured(self):
        t = self.view.theme
        self.assertEqual(len({t.fg, t.title, t.footer, t.meta}), 4)
        scr = make_scr(kind="prompt", title="Allow Bash?", actionable=True,
                       lines=(("w", "ls"), ("c", "1 running")), tokens="31k today")
        self.view.draw(scr)
        pens = screen.pens
        self.assertEqual(pens["Allow Bash?"], t.title)
        self.assertEqual(pens["ls"], t.fg)
        self.assertEqual(pens["A: Accept"], t.footer)
        self.assertEqual(pens["C: Exit"], t.footer)
        self.assertEqual(pens["1 running, 31k today"], t.meta)
        self.assertEqual(pens["Claude_A1B2C3"], t.fg)  # header stays white

    def test_vector_text_is_measured_and_drawn_at_its_size(self):
        screen.sizes.clear()
        self.view.draw(make_scr(kind="status", title="Done",
                                lines=(("w", "Claude: all done."),)))
        self.assertTrue(screen.sizes)
        self.assertTrue(set(screen.sizes) <= {18, 20, 24}, set(screen.sizes))

    def test_falls_back_to_pixel_fonts_without_the_font_file(self):
        MISSING_FONTS.add(buddy_profile.MONA)
        self.addCleanup(MISSING_FONTS.clear)
        buddy_view._loaded.clear()
        view = buddy_view.BuddyView(buddy_profile.TUFTY)
        self.assertIs(view.f_bar.font, font.smart)
        self.assertIs(view.f_title.font, font.curse)
        self.assertEqual((view.f_body.size, view.h_body), (0, 16))


class BadgerFontTest(unittest.TestCase):
    def test_badger_keeps_its_pixel_fonts_unscaled(self):
        view = buddy_view.BuddyView(buddy_profile.BADGER)
        self.assertIs(view.f_bar.font, font.nope)
        self.assertIs(view.f_title.font, font.absolute)
        self.assertIs(view.f_body.font, font.nope)
        screen.sizes.clear()
        view.draw(make_scr(kind="status", title="Done", lines=(("w", "all done"),)))
        # A size passed to a pixel font would scale it up by that factor.
        self.assertEqual(set(screen.sizes), {0})
        # Everything black: grey or colour doesn't work on its e-ink.
        self.assertEqual(set(screen.pens.values()), {"black"})


class PagingTest(unittest.TestCase):
    def setUp(self):
        self.view = buddy_view.BuddyView(buddy_profile.BADGER)

    def body_texts(self, scr, page):
        self.view.draw(scr, page)
        return [t for t, _, _ in screen.drawn]

    def test_short_content_is_one_page_without_marker(self):
        scr = make_scr(kind="prompt", lines=(("w", "ls -la"),), actionable=True)
        self.assertEqual(self.view.page_count(scr), 1)
        self.assertNotIn("1/1", self.body_texts(scr, 0))

    def test_long_prompt_pages_show_everything_once(self):
        scr = make_scr(kind="prompt", lines=(("w", LONG),), actionable=True)
        pages = self.view.page_count(scr)
        self.assertGreater(pages, 1)
        seen = []
        for page in range(pages):
            texts = self.body_texts(scr, page)
            self.assertIn("Allow Bash?", texts)  # title on every page
            self.assertIn("{}/{}".format(page + 1, pages), texts)
            self.assertNotIn("UP/DOWN", texts)  # the marker is enough
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

    # -- counts on the bottom row ------------------------------------------

    def drawn_at(self, scr, page):
        self.view.draw(scr, page)
        return {t: (x, y) for t, x, y in screen.drawn}

    def bottom_y(self):
        return self.view.body_bottom - self.view.h_body + 1

    def test_counts_on_bottom_row_of_every_page(self):
        scr = make_scr(lines=(("c", "1 running, 0 waiting"), ("w", "Claude: " + LONG)),
                       tokens="31k today")
        pages = self.view.page_count(scr)
        self.assertGreater(pages, 1)
        for page in range(pages):
            drawn = self.drawn_at(scr, page)
            marker = "{}/{}".format(page + 1, pages)
            self.assertEqual(drawn["1 running, 0 waiting, 31k today"], (4, self.bottom_y()))
            self.assertEqual(drawn[marker][1], self.bottom_y())
            for text, (_, y) in drawn.items():
                if text.startswith(("word", "Claude:")):
                    # Whole row above the counts row, not just its top.
                    self.assertLessEqual(y + self.view.h_body, self.bottom_y() - 1, text)

    def test_counts_reserved_even_on_one_page(self):
        # Exactly as many entries as fill one page when nothing reserves
        # the bottom row (a screen without counts). With counts, that row
        # must still be kept free, so no entry may reach it.
        def entries(n):
            return tuple(("s", "entry{}".format(i)) for i in range(n))

        n = 1
        while self.view.page_count(make_scr(lines=entries(n + 1))) == 1:
            n += 1
        scr = make_scr(lines=(("c", "0 running, 0 waiting"),) + entries(n))
        self.view.draw(scr, 0)
        drawn = {t: (x, y) for t, x, y in screen.drawn}
        self.assertEqual(drawn["0 running, 0 waiting"][1], self.bottom_y())
        for text, (_, y) in drawn.items():
            if text.startswith("entry"):
                self.assertLessEqual(y + self.view.h_body, self.bottom_y() - 1, text)

    def test_counts_use_short_labels_when_tight(self):
        # Body is 42 chars wide; with the "1/3" marker the counts get 38.
        # Full labels need 40 here, so they switch to run/wait.
        lines = (("c", "12345 running, 67890 waiting"), ("w", "Claude: " + LONG))
        scr = make_scr(lines=lines, tokens="1.2M today")
        drawn = self.drawn_at(scr, 0)
        self.assertIn("12345 run, 67890 wait, 1.2M today", drawn)
        self.assertIn("1/{}".format(self.view.page_count(scr)), drawn)

    def test_empty_counts_row_shows_tokens_only(self):
        # No-sessions screen: bottom row is today's tokens alone.
        scr = make_scr(kind="none", title="No sessions",
                       lines=(("w", "Open a session."), ("c", "")), tokens="31k today")
        drawn = self.drawn_at(scr, 0)
        self.assertEqual(drawn["31k today"], (4, self.bottom_y()))
        self.assertFalse(any(t.startswith(",") for t in drawn))
        # Without tokens the row is simply empty.
        scr = make_scr(kind="none", title="No sessions", lines=(("w", "Open a session."), ("c", "")))
        drawn = self.drawn_at(scr, 0)
        self.assertFalse(any(y == self.bottom_y() for _, y in drawn.values()))

    def test_tokens_not_on_prompt_bottom_row(self):
        scr = make_scr(kind="prompt", lines=(("w", LONG),), actionable=True, tokens="31k today")
        self.assertFalse(any("31k" in t for t in self.drawn_at(scr, 0)))

    def test_counts_cut_but_marker_kept(self):
        lines = (("c", "1234567890 running, 1234567890 waiting"), ("w", "Claude: " + LONG))
        scr = make_scr(lines=lines, tokens="999M today")
        drawn = self.drawn_at(scr, 0)
        marker = "1/{}".format(self.view.page_count(scr))
        self.assertIn(marker, drawn)
        (counts,) = [t for t in drawn if t.startswith("1234567890")]
        self.assertIn(" run,", counts)  # shortened first, then cut
        self.assertTrue(counts.endswith("..."))
        self.assertLess(drawn[counts][0] + len(counts) * CHAR_W, drawn[marker][0])


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
        # Lanes: 1^4^7 = 0x02, 2^5^8 = 0x0F, 3^6 = 0x05.
        self.assertEqual(buddy_ble.id_suffix(uid), "020F05")
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


class DropTest(unittest.TestCase):
    """Dropping a dead or silent link (BuddyBLE.drop)."""

    def setUp(self):
        self.ble = buddy_ble.BuddyBLE()
        self.disconnects = []
        self.ble._ble.gap_disconnect = self.disconnects.append
        # CPython's time has no ticks_*.
        self.real_time = buddy_ble.time
        buddy_ble.time = types.SimpleNamespace(
            ticks_diff=lambda a, b: a - b, ticks_add=lambda a, b: a + b
        )

    def tearDown(self):
        buddy_ble.time = self.real_time

    def test_drop_only_when_connected_and_rate_limited(self):
        self.assertFalse(self.ble.drop(0))  # nothing to drop
        self.ble._irq(buddy_ble._IRQ_CENTRAL_CONNECT, (7, 0, b""))
        self.assertTrue(self.ble.drop(0))
        self.assertEqual(self.disconnects, [7])
        self.assertFalse(self.ble.drop(buddy_ble._DROP_RETRY_MS - 1))
        self.assertTrue(self.ble.drop(buddy_ble._DROP_RETRY_MS))  # retry
        self.assertTrue(self.ble.drop(-1))  # ticks wrapped: retry, don't stall
        self.ble._irq(buddy_ble._IRQ_CENTRAL_DISCONNECT, (7, 0, b""))
        self.assertFalse(self.ble.drop(10**6))
        self.assertEqual(len(self.disconnects), 3)


if __name__ == "__main__":
    unittest.main()
