# The buddy character

A small orange blob that shows what Claude is doing: one still picture
per state. Anthropic's reference device shows an animated pet; this is
the badge's own take on that.

**Status:** the pictures are drawn and can be viewed on a badge with a
gallery tool, but the app doesn't show them yet: nothing on its
screens has changed. Viewed on a Tufty 2350 on 2026-11-23 (see
[Results](#results)); not yet on a Badger.

## The character

An original blob, drawn for this project in Claude's orange. It isn't
Anthropic's mascot or any of claude-desktop-buddy's pets. Every state
has the same body width, so the buddy takes the same room on screen
whatever it's doing:

| State     | Picture                                                    |
| --------- | ---------------------------------------------------------- |
| sleep     | Squashed flatter, eyes closed, `zZ` above                  |
| idle      | Round eyes, small smile                                    |
| busy      | Glancing up at two meshing gears, mouth pulled to one side |
| attention | Wide eyes, small "o" mouth, `!?` above                     |
| celebrate | Happy `^ ^` eyes, open grin, a party hat and confetti      |

Upstream also has dizzy (shaking the M5Stick) and heart (petting it,
or approving within 5 s). The badges have no motion or touch sensor,
so those aren't drawn.

## The pictures

`tools/make_buddy_art.py` draws them from simple shapes (squircles,
ellipses, lines, polygons) with the standard library and writes
`apps/claude_buddy/buddy_art/<badge>_<state>.png`. Change a shape,
colour or size there and run it again; `--sheet DIR` also writes
preview sheets, and `--check` (and a unit test) fails if the PNGs are
out of date.

| Badge  | Size  | Colours                                          | RAM per image |
| ------ | ----- | ------------------------------------------------ | ------------- |
| Tufty  | 96 px | orange body, dark face, white marks; antialiased | about 37 KB   |
| Badger | 72 px | outlined: white body, black edge, face and marks | about 21 KB   |

On the Badger the buddy is outlined: pure black and white, for the
e-ink, with a thick black edge round a white body. A solid black body
with only white eyes showing was tried first, and dropped because it
read as a figure painted black, which could offend.

Backgrounds are transparent, so the pictures sit on either badge's
background. The files are small (0.3–1.3 KB each); the RAM is the
decoded image, so the app should load only the picture it is showing.

Sizes were chosen on the Tufty: 128 px looked too big beside the text,
and half that too small. The Badger's 72 px matches by eye (its
pixels are larger) but hasn't been seen on a Badger yet.

## Viewing them on a badge

1. Install the app as usual (`python3 tools/install.py`, see the
   README). The pictures go with it; the app doesn't use them yet.
2. With the badge back in normal mode, run:

   ```bash
   python3 tools/buddy_gallery.py
   ```

   It stops whatever the badge was running and shows:
   - **page 1:** all five states side by side, at half size;
   - **pages 2–6:** each state at full size on the right, beside a
     title and sample text, roughly as the app would lay it out.

   **DOWN** / **UP** turn pages and **C** stops; the badge then
   restarts. The terminal shows the pictures' size and RAM.

## Results

**Tufty 2350, 2026-11-23** (firmware v3.1.1): the 96 px pictures look
right beside the text, and the states read clearly. Two rounds of
changes came from seeing them on the screen: smaller (from 128 px) and
bigger feet.

**Badger 2350:** not yet viewed.

## Why not claude-desktop-buddy's ASCII pets

They were tried first: the 18 pets from
[anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)
(MIT), one still pose per state, drawn as text. On a Tufty they were
too hard to read in any font that leaves room for text beside them.
What was learned:

- **The badge fonts are proportional**, so ASCII art only lines up if
  each character is drawn in its own fixed-width cell.
- **Font cells measured on a Tufty:** `sins` and `teatime` 8×12 px,
  `nope` 11×13, MonaSans 12/14/16 px 11×12, 13×14 and 14×16. The pixel
  fonts measure 1 px wider than their `.ppf` files say.
- **Upstream centres each line** on the M5Stick's home screen; keeping
  its padded columns instead put the feet too far left.
- **The firmware's `measure_text` returns floats** (`8.0`).

The work is in closed pull request #19.

## Next: showing the buddy in the app

Planned, not built. The buddy would sit on the right of the body on
connected screens, its state taken from what the screen already
shows, so it adds **no e-ink refreshes**:

| Screen                                    | State     |
| ----------------------------------------- | --------- |
| No sessions                               | sleep     |
| Connected, or status with nothing running | idle      |
| Status with sessions running              | busy      |
| A prompt, or waiting without one          | attention |
| Answered: approved                        | celebrate |
| Answered: denied                          | idle      |
| Pair with Claude / Disconnected (framed)  | no buddy  |

Busy starts at 1 running session, because the title already changes
from "Idle" to "Working" there and the counts are part of the screen's
change key. Text beside the buddy wraps in the narrower space left.
Nothing animates, on either badge.
