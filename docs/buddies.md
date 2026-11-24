# Buddy characters

Anthropic's reference device,
[claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy),
shows one of 18 animated ASCII pets (a cat, an owl, a robot...) that
reacts to what Claude is doing. This page is about bringing those pets
to Claude Buddy.

**Status: phase 0, evaluation.** The pets are imported and can be
viewed on a badge with a gallery tool, but the app doesn't show them
yet: nothing on its screens has changed. Not yet tried on hardware.

## Where they come from

- **Source:** `src/buddies/*.cpp` in claude-desktop-buddy, vendored as
  the submodule `vendor/claude-desktop-buddy`, pinned to commit
  `a280c64` (the commit [docs/protocol.md](protocol.md) cites).
- **Import:** `python3 tools/import_buddies.py` parses those files and
  writes `apps/claude_buddy/buddy_species.py`. Run it again after
  moving the pin; `--show` prints every kept pose as text, and
  `--check` fails if the generated file is out of date (a test runs
  the same check).
- **Licence:** the pets are Copyright 2026 Anthropic, PBC, under the
  MIT licence. Anthropic keeps one `LICENSE` at the repository root
  and no notices in the source files. Here the notice goes everywhere
  a copy goes: the generated module's header names the source,
  commit and copyright, and the licence is copied verbatim to
  `apps/claude_buddy/LICENSE-claude-desktop-buddy`, which
  `tools/install.py` copies onto every badge with the app.
- **Not used:** upstream's `characters/bufo` GIFs, which are not MIT
  ("all rights remain with their original creators").

## What's kept

Upstream animates each state at 5 frames a second from a sequence of
5-line poses, with particles drawn round the pet. The Badger's e-ink
can't animate (every frame would be a 1–2 s refresh), so each state
keeps **one still pose**:

| State     | Upstream shows it when                                | Pose kept                                      |
| --------- | ----------------------------------------------------- | ---------------------------------------------- |
| sleep     | the screen has just woken, or by the clock at night   | the sequence's first                           |
| idle      | connected with nothing urgent, or disconnected        | the sequence's first                           |
| busy      | 3 or more sessions running                            | the sequence's first                           |
| attention | a session is waiting for approval                     | the sequence's first                           |
| celebrate | Desktop's `completed` flag, or a level-up             | the final pose (arms up; the cactus's bloom)   |
| dizzy     | the M5Stick is shaken (IMU), or late at night (clock) | not kept: the badges have no motion sensor     |
| heart     | petting it, or approving a prompt within 5 s          | not kept: no touch sensor; may come back later |

Celebrate is the one state whose first pose doesn't work still: every
species starts it with a crouch before the jump. The choice is
`PREFERRED` in `tools/import_buddies.py`.

The duck's one non-ASCII character (`´`) becomes `'`; everything else
is printable ASCII. The species table is about 11 KB of source and a
5 KB `.mpy`.

### Still marks

Many states differ upstream mainly by motion and particles: the cat's
idle and busy faces differ by one letter (`o` and `O`). In place of
the particles, `buddy_sprite.py` adds a fixed mark beside each pose,
the same for every species:

| State     | Mark                         |
| --------- | ---------------------------- |
| sleep     | `Z` and `z`, top right       |
| idle      | none                         |
| busy      | `...` beside the middle line |
| attention | `!` at both top corners      |
| celebrate | `*` at both top corners      |

Whether the states can be told apart with these is one of the things
to judge on the badge.

## Drawing on a fixed grid

The art needs fixed columns, but the badge fonts are proportional (an
`i` is narrower than a `W`). `buddy_sprite.py` draws each character in
its own cell, centred, as the M5Stick's fixed 6×8 font does upstream.
The cell is as wide as the widest character the art uses.

Each line is trimmed and centred on the pose's middle, the way
upstream draws a pet on the M5Stick's home screen (at 2×). Upstream's
smaller view keeps each line's padding instead, so the columns line up
on the left. That was tried first, and on the Tufty the bottom line
(feet, base, tail), usually the narrowest, sat too far left. Centring
a line one character shorter than the widest moves it by half a cell.

The ROM pixel fonts' widths, read from their `.ppf` glyph tables. The
gallery measures them on the badge, and they can differ: `sins`
measured 8 px wide on the Tufty, not 7. The widest pose, marks
included, is 18 cells by 5 rows:

| Font      | Cell (px, from the file) | Widest pose (px) |
| --------- | ------------------------ | ---------------- |
| `sins`    | 7 × 12 (8 × 12 measured) | 126 × 60         |
| `teatime` | 7 × 12                   | 126 × 60         |
| `kobold`  | 7 × 12                   | 126 × 60         |
| `hungry`  | 7 × 15                   | 126 × 75         |
| `nope`    | 10 × 13                  | 180 × 65         |

At 7 px cells a pet fits in a column about 130 px wide beside the text
on the Badger's 264×176 screen. `nope`, the Badger's body font, is too
wide for that. MonaSans (the Tufty's font) is measured by the gallery.

## Trying them on a badge

1. Install the app as usual (`python3 tools/install.py`, see the
   README). The pet files go with it; the app doesn't use them yet.
2. With the badge back in normal mode, run:

   ```bash
   python3 tools/buddy_gallery.py
   ```

   It stops whatever the badge was running and shows each species'
   poses with their marks, four to a screen on the Badger, so two
   screens per species:
   - **DOWN** / **UP:** next / previous screen;
   - **B** / **A:** next / previous font;
   - **C:** stop. The badge restarts.

   The terminal shows the RAM the species table takes and the cell
   size measured for each font.

### What to judge

For each species, at the smallest font that reads well:

- **Recognisable:** does it look like the animal (or thing)?
- **Five distinct states:** can sleep, idle, busy, attention and
  celebrate be told apart at a glance, marks included?
- **Clean:** no missing or wrong characters (`[`, `\`, `` ` `` and
  `"` are the risky ones), no ghosting after a few screens.
- **Memory:** the species table's RAM next to what the app has free.

Results go in a table here, per species: use as is, use with a
different pose (a `PREFERRED` entry), or drop. Not yet done.

## Next: showing a pet in the app (phase 1)

Planned, not built. The pet would sit in a column at the right of the
body on connected screens, its state taken from what the screen
already shows, so it adds **no e-ink refreshes**:

| Screen                                    | State     |
| ----------------------------------------- | --------- |
| No sessions                               | sleep     |
| Connected, or status with nothing running | idle      |
| Status with sessions running              | busy      |
| A prompt, or waiting without one          | attention |
| Answered: approved                        | celebrate |
| Answered: denied                          | idle      |
| Pair with Claude / Disconnected (framed)  | no pet    |

Busy starts at 1 running session here, not upstream's 3, because the
title already changes from "Idle" to "Working" at 1 and the counts are
part of the screen's change key. The species would be a saved setting,
"none" by default so badges keep today's look; A and B never pick one,
since a prompt arriving mid-press would be answered. Nothing animates,
on either badge; a live pet on the Tufty on USB power is a later idea.
