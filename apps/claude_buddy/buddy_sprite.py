"""Lays out a buddy pose (from buddy_species) on a character grid.

The art was drawn for the M5StickC's fixed 6x8 font, so every column
has to line up. The badge fonts are proportional (an "i" is narrower
than a "W"), so each character is drawn in its own cell, ``pitch``
pixels wide and ``line_h`` high, centred in it.

Upstream animates each state and draws moving particles round the
buddy (Zz, dots, "!", confetti). Nothing here moves: each state shows
one still pose plus a fixed mark from MARKS, so states that differ
upstream mostly by motion can still be told apart.

Pure layout: no drawing calls, so it runs on the host in the tests.
The caller draws each cell with its own text function.
"""

from buddy_species import SPECIES, STATES

# Still marks standing in for upstream's moving particles:
# (side, row, text). "R" puts the text one column right of the widest
# line, "L" one column left of the art; row 0 is the pose's top line.
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
    """((col, row, char), ...), (cols, rows) for one pose.

    Columns are shifted so the leftmost character (art or mark) is in
    column 0; blank cells are left out. ``cols`` x ``rows`` is the size
    of the whole block, marks included, so callers can place it."""
    lines = pose(species, state)
    inked = [line for line in lines if line.strip()]
    left = min(len(line) - len(line.lstrip()) for line in inked)
    right = max(len(line) for line in inked)
    out = [
        (col, row, ch)
        for row, line in enumerate(lines)
        for col, ch in enumerate(line)
        if ch != " "
    ]
    if marks:
        for side, row, text in MARKS[state]:
            start = right + 1 if side == "R" else left - 1 - (len(text) - 1)
            out.extend((start + i, row, ch) for i, ch in enumerate(text))
    first = min(col for col, _row, _ch in out)
    out = [(col - first, row, ch) for col, row, ch in out]
    cols = max(col for col, _row, _ch in out) + 1
    return out, (cols, len(lines))


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
    its top-left corner at (x, y), in whole pixels. With ``measure``
    each character is centred in its cell; without, it sits at the
    cell's left edge."""
    return [
        (ch, int(x + col * pitch + ((pitch - _whole(measure(ch))) // 2 if measure else 0)), int(y + row * line_h))
        for col, row, ch in grid
    ]
