"""Lays out a buddy pose (from buddy_species) on a character grid.

The art was drawn for the M5StickC's fixed 6x8 font. The badge fonts
are proportional (an "i" is narrower than a "W"), so each character is
drawn in its own cell, ``pitch`` pixels wide and ``line_h`` high,
centred in it.

Lines are laid out the way upstream draws a pet on the M5Stick's home
screen (buddy.cpp, buddyPrintLine at 2x): each line trimmed of spaces
and centred on the pose's middle. Upstream's padded columns (its 1x
view) put narrow lines, such as the feet, too far left. Centring a
line one character shorter than the widest moves it by half a cell,
so columns here count **half cells**.

Upstream animates each state and draws moving particles round the
buddy (Zz, dots, "!", confetti). Nothing here moves: each state shows
one still pose plus a fixed mark from MARKS, so states that differ
upstream mostly by motion can still be told apart.

Pure layout: no drawing calls, so it runs on the host in the tests.
The caller draws each cell with its own text function.
"""

from buddy_species import SPECIES, STATES

# Still marks standing in for upstream's moving particles:
# (side, row, text). "R" puts the text one cell right of the widest
# line, "L" one cell left of it; row 0 is the pose's top line.
MARKS = {
    "sleep": (("R", 0, "Z"), ("R", 1, "z")),
    "idle": (),
    "busy": (("R", 2, "..."),),
    "attention": (("L", 0, "!"), ("R", 0, "!")),
    "celebrate": (("L", 0, "*"), ("R", 0, "*")),
}


def pose(species, state):
    """The pose's lines for ``state`` of ``species``."""
    return SPECIES[species][1][STATES.index(state)].split("\n")


def cells(species, state, marks=True):
    """((half, row, char), ...), (width, rows) for one pose.

    ``half`` is the character's column in half cells, counted from the
    block's left edge (art or mark); blank cells are left out.
    ``width`` is the block's width in half cells and ``rows`` its
    height in lines, marks included, so callers can place it (see
    width_px)."""
    lines = [line.strip() for line in pose(species, state)]
    widest = max(len(line) for line in lines)
    out = []
    for row, line in enumerate(lines):
        start = widest - len(line)  # centred: (widest - len) / 2 cells
        out.extend((start + 2 * i, row, ch) for i, ch in enumerate(line) if ch != " ")
    if marks:
        for side, row, text in MARKS[state]:
            start = 2 * (widest + 1) if side == "R" else -2 * (len(text) + 1)
            out.extend((start + 2 * i, row, ch) for i, ch in enumerate(text))
    first = min(half for half, _row, _ch in out)
    out = [(half - first, row, ch) for half, row, ch in out]
    width = max(half for half, _row, _ch in out) + 2
    return out, (width, len(lines))


def width_px(width, pitch):
    """A width in half cells (from cells()) in whole pixels."""
    return (width * pitch + 1) // 2


def _whole(width):
    """A measured width as whole pixels, rounded up: the firmware's
    measure_text returns floats (8.0), and MicroPython's range and
    integer layout need ints."""
    whole = int(width)
    return whole + 1 if width > whole else whole


def pitch_for(measure, chars=None):
    """The cell width, in whole pixels, that fits every character the
    art uses: ``measure(ch)`` is a character's width in the current
    font."""
    if chars is None:
        chars = {ch for _colour, poses in SPECIES.values() for p in poses for ch in p} - {" ", "\n"}
    chars = set(chars) | {ch for marks in MARKS.values() for _side, _row, text in marks for ch in text}
    return max(_whole(measure(ch)) for ch in chars)


def place(grid, x, y, pitch, line_h, measure=None):
    """(char, x, y) for each cell of ``grid`` (from cells()) drawn with
    the block's top-left corner at (x, y), in whole pixels. With
    ``measure`` each character is centred in its cell; without, it
    sits at the cell's left edge."""
    return [
        (
            ch,
            int(x + (half * pitch) // 2 + ((pitch - _whole(measure(ch))) // 2 if measure else 0)),
            int(y + row * line_h),
        )
        for half, row, ch in grid
    ]
