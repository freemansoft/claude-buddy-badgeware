"""Host tests for buddy_sprite: laying a buddy pose out on a character
grid, with the still marks that stand in for upstream's particles."""

import unittest

import support  # noqa: F401 - puts apps/claude_buddy on sys.path

import buddy_species
import buddy_sprite as sprite


def picture(species, state, marks=True):
    """The laid-out pose as text, one string per row."""
    grid, (cols, rows) = sprite.cells(species, state, marks)
    out = [[" "] * cols for _ in range(rows)]
    for col, row, ch in grid:
        out[row][col] = ch
    return ["".join(row).rstrip() for row in out]


class CellsTest(unittest.TestCase):
    def test_leading_blank_columns_are_dropped(self):
        self.assertEqual(picture("cat", "idle"), ["", " /\\_/\\", "( o   o )", "(  w   )", '(")_(")'])

    def test_blank_cells_are_left_out(self):
        grid, _size = sprite.cells("cat", "idle")
        self.assertNotIn(" ", [ch for _col, _row, ch in grid])

    def test_sleep_marks_sit_right_of_the_widest_line(self):
        self.assertEqual(picture("cat", "sleep"), ["          Z", "          z", " .-..-.", "( -.- )", "`------`~"])

    def test_left_marks_shift_the_art_right(self):
        rows = picture("cat", "attention")
        self.assertEqual(rows[0], "!          !")
        self.assertEqual(rows[2], " ( O   O )")

    def test_size_covers_art_and_marks(self):
        _grid, (cols, rows) = sprite.cells("cat", "busy")
        self.assertEqual((cols, rows), (13, 5))  # "( O   O ) ..."
        _grid, (cols, _rows) = sprite.cells("cat", "busy", marks=False)
        self.assertEqual(cols, 9)

    def test_every_pose_lays_out_and_fits_the_widest_block(self):
        widest = 0
        for name in buddy_species.SPECIES:
            for state in buddy_species.STATES:
                grid, (cols, rows) = sprite.cells(name, state)
                self.assertEqual(rows, 5)
                self.assertTrue(grid, (name, state))
                self.assertEqual(min(col for col, _row, _ch in grid), 0)
                widest = max(widest, cols)
        self.assertLessEqual(widest, 17)  # 17 columns x 7 px = 119 px on the Badger

    def test_every_state_has_marks(self):
        self.assertEqual(set(sprite.MARKS), set(buddy_species.STATES))


class PitchTest(unittest.TestCase):
    def test_widest_character_sets_the_pitch(self):
        widths = {"@": 9, "W": 8}
        self.assertEqual(sprite.pitch_for(lambda ch: widths.get(ch, 5)), 9)

    def test_float_widths_round_up_to_whole_pixels(self):
        # The firmware's measure_text returns floats (seen: 8.0 on a Tufty).
        pitch = sprite.pitch_for(lambda ch: 7.25 if ch == "@" else 6.0)
        self.assertEqual((pitch, type(pitch)), (8, int))
        placed = sprite.place([(1, 1, "i")], 0, 0, pitch, 12, lambda _ch: 3.0)
        self.assertEqual(placed, [("i", 10, 12)])
        self.assertTrue(all(type(v) is int for _ch, x, y in placed for v in (x, y)))

    def test_marks_count(self):
        # Characters only the marks use (here "Z") must count too.
        self.assertEqual(sprite.pitch_for(lambda ch: 12 if ch == "Z" else 4, chars="ab"), 12)


class PlaceTest(unittest.TestCase):
    def test_cells_at_fixed_pitch(self):
        grid = [(0, 0, "a"), (2, 1, "b")]
        self.assertEqual(sprite.place(grid, 10, 20, 7, 12), [("a", 10, 20), ("b", 24, 32)])

    def test_characters_centred_in_their_cell(self):
        grid = [(0, 0, "i"), (1, 0, "W")]
        widths = {"i": 3, "W": 7}
        self.assertEqual(sprite.place(grid, 0, 0, 7, 12, widths.get), [("i", 2, 0), ("W", 7, 0)])


if __name__ == "__main__":
    unittest.main()
