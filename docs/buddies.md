# The buddy character

A small orange blob on the Tufty that shows what Claude is doing: one
still picture per state. Anthropic's reference device shows an
animated pet; this is the badge's own take on that. **The Badger has
no buddy** (see [Not on the Badger](#not-on-the-badger)).

**Status:** the app shows the buddy on the Tufty's connected screens
(see [In the app](#in-the-app)). The pictures were checked on a Tufty
2350 with the gallery tool on 2026-11-23 (see [Results](#results));
the app with the buddy hasn't been run on a Tufty yet.

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
`apps/claude_buddy/buddy_art/tufty_<state>.png`. Change a shape,
colour or size there and run it again; `--sheet DIR` also writes
preview sheets, and `--check` (and a unit test) fails if the PNGs are
out of date.

They are 96 px square: an orange body, a dark face and white marks,
antialiased, on a transparent background. The files are about 1 KB
each, but each takes about 37 KB of RAM once decoded, so the app
should load only the picture it is showing.

The size was chosen on the Tufty: 128 px looked too big beside the
text, and half that too small.

## Not on the Badger

The Badger's e-ink gets no buddy. Decided on 2026-11-23, after trying
two black-and-white versions at 72 px (previewed on the Mac, never on
a Badger):

- **Solid black body, white face:** read as a figure painted black
  with only its eyes showing, which could offend.
- **Outlined, white body with a black edge:** with no antialiasing,
  thin lines broke up; thickened, they pushed into the marks above the
  head and cut the party hat apart. It never looked as good as the
  colour version.

The Badger keeps its text-only screens, and this work must leave it
**unchanged**: its screens, layout, refreshes and power behaviour.
The only Badger-side changes allowed are in files both badges share
(for example a profile field the Badger sets to "no buddy"). The
Tufty's pictures are copied onto a Badger with the rest of the app
folder (about 5 KB) but never read there. Reopening this is a new
decision, not a bug fix.

## Viewing them on a Tufty

1. Install the app as usual (`python3 tools/install.py`, see the
   README). The pictures go with it; the app doesn't use them yet.
2. With the Tufty back in normal mode, run:

   ```bash
   python3 tools/buddy_gallery.py
   ```

   It stops whatever the Tufty was running and shows:
   - **page 1:** all five states side by side, at half size;
   - **pages 2–6:** each state at full size on the right, beside a
     title and sample text, roughly as the app would lay it out.

   **DOWN** / **UP** turn pages and **C** stops; the Tufty then
   restarts. The terminal shows the pictures' size and RAM.

## Results

**Tufty 2350, 2026-11-23** (firmware v3.1.1): the 96 px pictures look
right beside the text, and the states read clearly. Two rounds of
changes came from seeing them on the screen: smaller (from 128 px) and
bigger feet.

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

## In the app

On the Tufty only: its profile (`buddy_profile.TUFTY.buddy`) names the
pictures and their size, and the Badger's profile has none, so the
Badger's screens are drawn exactly as before. The buddy sits on the
right of the body on connected screens, centred above the bottom row;
the title and text wrap in the space left of it, and the bottom row
(counts, tokens, page marker) keeps the full width. Its state comes
from what the screen already shows (`BuddyModel.buddy_mood`), so it
adds no repaints of its own:

| Screen                                    | State     |
| ----------------------------------------- | --------- |
| No sessions                               | sleep     |
| Connected, or status with nothing running | idle      |
| Status with sessions running              | busy      |
| A prompt, or waiting without one          | attention |
| Answered: approved                        | celebrate |
| Answered: denied                          | idle      |
| Pair with Claude / Disconnected (framed)  | no buddy  |

Busy starts at 1 running session, not upstream's 3, because the
title already changes from "Idle" to "Working" there and the counts
are part of the screen's change key. The state rides at the end of
the screen tuple (`S_MOOD`) as a passenger; a test checks it never
changes while the key stays the same. Only the picture on screen is
loaded (about 37 KB of RAM), when the state changes. Nothing animates.
