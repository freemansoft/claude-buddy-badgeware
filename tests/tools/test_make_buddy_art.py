"""Host tests for tools/make_buddy_art.py and the images it writes to
apps/claude_buddy/buddy_art/."""

import struct
import unittest
import zlib

import support  # noqa: F401 - puts tools/ on sys.path

import make_buddy_art as art


def decode(data):
    """Rows of (r, g, b, a) from an RGBA PNG written by art.png()."""
    width, height = struct.unpack(">II", data[16:24])
    raw = zlib.decompress(data[41:-12])
    stride = 1 + 4 * width
    return [[tuple(raw[y * stride + 1 + 4 * x:y * stride + 5 + 4 * x]) for x in range(width)] for y in range(height)]


def ink_columns(rows):
    """(first, last) column with any visible pixel."""
    cols = [x for x in range(len(rows[0])) if any(row[x][3] for row in rows)]
    return cols[0], cols[-1]


class ArtTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = art.build()  # about 2 s: render once for all the tests

    def test_one_image_per_badge_and_state(self):
        self.assertEqual(len(self.files), len(art.BADGES) * len(art.STATES))
        for badge, spec in art.BADGES.items():
            for state in art.STATES:
                rows = decode(self.files[art.filename(badge, state)])
                self.assertEqual((len(rows[0]), len(rows)), (spec["size"], spec["size"]))

    def test_every_state_is_the_same_width_on_screen(self):
        # Marks (zZ, gears, !?, the party hat) stay within the body, so
        # the buddy takes the same room whatever it's doing.
        for badge in art.BADGES:
            widths = {state: ink_columns(decode(self.files[art.filename(badge, state)])) for state in art.STATES}
            self.assertEqual(len(set(widths.values())), 1, (badge, widths))

    def test_badger_images_are_pure_black_and_white(self):
        for state in art.STATES:
            rows = decode(self.files[art.filename("badger", state)])
            pixels = {p for row in rows for p in row}
            self.assertLessEqual(pixels, {(0, 0, 0, 0), (0, 0, 0, 255), (255, 255, 255, 255)}, state)

    def test_background_is_transparent(self):
        for name, data in self.files.items():
            rows = decode(data)
            self.assertEqual(rows[0][0][3], 0, name)
            self.assertEqual(rows[-1][-1][3], 0, name)

    def test_states_differ(self):
        for badge in art.BADGES:
            images = {self.files[art.filename(badge, state)] for state in art.STATES}
            self.assertEqual(len(images), len(art.STATES))

    def test_unknown_state_is_an_error(self):
        with self.assertRaises(ValueError):
            art.scene("dizzy")

    def test_app_images_are_up_to_date(self):
        for name, data in self.files.items():
            self.assertEqual((art.OUT / name).read_bytes(), data, "run python3 tools/make_buddy_art.py")


if __name__ == "__main__":
    unittest.main()
