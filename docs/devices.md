# Devices and display architectures

Claude Buddy targets two Badgeware badges. They share the RP2350, the
Bluetooth radio, the buttons and the app code, but their displays work
in opposite ways. This page is the one place that records every
behaviour that differs between them because of that.

- **Badger 2350:** e-ink. Supported (phase 1).
- **Tufty 2350:** colour TFT LCD. Supported (phase 2): the app runs
  at the Tufty's resolution with its own fonts and colours. On USB
  power it redraws live; on battery it keeps the Badger's refresh
  timings to save power.

Related pages: [power.md](power.md) (USB power vs battery, and why
e-ink refreshes cost power), [protocol.md](protocol.md) (the same on
both badges).

## Display hardware

|                        | Badger 2350                                       | Tufty 2350                                                    |
| ---------------------- | ------------------------------------------------- | ------------------------------------------------------------- |
| Panel                  | E-ink, SSD1680 driver                             | Colour TFT LCD                                                |
| Resolution in this app | 264×176                                           | 320×240 (`HIRES`)                                             |
| Colours                | 4 greys                                           | Full colour                                                   |
| Holds image unpowered  | Yes                                               | No: always on while the app runs                              |
| Update                 | Full-screen 4-grey refresh, ~1–2 s, visible flash | Fast, no flash; Badgeware's `run()` sends a frame every loop  |
| Partial refresh        | No (the driver ignores the speed setting)         | Not needed                                                    |
| Backlight              | None                                              | Yes. Dims after 60 s idle on battery (`buddy_backlight.py`)   |
| Light sensor           | Not used                                          | Front sensor. Not implemented (plan: set the backlight level) |
| Power while static     | ~None for the panel                               | Panel and backlight draw all the time                         |
| Main display cost      | The _number_ of refreshes                         | Backlight on-time                                             |

## How the app treats each display

The Badger's rules all exist to avoid e-ink refreshes. On an LCD they
only make the screen lag, so on **USB power** the Tufty redraws live:
every change shows at once. On **battery** it keeps the Badger's
timings, because every redraw costs power. Both come from its profile
(`refresh_usb`, `refresh_battery`; see below).

| Setting                 | Badger 2350 (e-ink, USB and battery)                                     | Tufty 2350 (live on USB; e-ink timings on battery)                                                                                              |
| ----------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `badge.mode()`          | `FAST_UPDATE \| NON_BLOCKING`                                            | `HIRES`                                                                                                                                         |
| What triggers a repaint | The screen key changes (`screen_key`: battery and tokens excluded)       | On USB: **any** change, battery and tokens included. On battery: same as the Badger                                                             |
| Urgent settle delay     | 300 ms                                                                   | On USB: none. On battery: 300 ms                                                                                                                |
| Status-only changes     | Coalesced, at most one repaint every 15 s                                | On USB: at once. On battery: at most every 15 s, as on the Badger                                                                               |
| After A/B               | ~1 s hold, so the result and Desktop's follow-up share one refresh       | On USB: no hold. On battery: ~1 s hold                                                                                                          |
| "No sessions" screen    | After 5 s with no sessions, so a quick close-and-open costs no refreshes | On USB: at once. On battery: after 5 s                                                                                                          |
| First frame             | Slowest, cleanest waveform, to clear ghosting from the menu              | Not needed                                                                                                                                      |
| Button reading          | `update()` calls `badge.poll()` each pass                                | Badgeware's `run()` calls `badge.poll()` each loop; `update()` uses that reading and doesn't poll                                               |
| Present                 | `display.update()`, non-blocking; painter waits while `display.busy()`   | `display.update()` on each paint; `run()` re-sends the framebuffer every loop, so `badge.default_clear = None` stops it clearing between paints |
| Battery label           | 25% steps (5% when low), rides along with other repaints                 | On USB the header shows `Charging`/`Full`/`USB` (no percentage). On battery: same as the Badger                                                 |
| Tokens label            | Rounded (`31k`), rides along                                             | On USB: exact and live (`31,204 today`). On battery: same as the Badger                                                                         |
| Colours                 | Black on white; no grey text (too faint on e-ink)                        | White on black, with coloured titles, button labels and counts (see [Colour scheme](#colour-scheme))                                            |
| Accents                 | None                                                                     | Not implemented (plan: e.g. highlight the title when the `emphasis` flag is set)                                                                |
| Fonts                   | `nope` pixel font, sized for 264×176                                     | MonaSans (vector, from the firmware): 18 px header and footer, 20 px body, 24 px titles; pixel fonts as fallback                                |
| Animation               | None: nothing on screen moves                                            | Not implemented (open question: a "working" indicator?)                                                                                         |
| Instant feedback        | Case-light blink on A/B, because the panel takes 1–2 s                   | Not implemented (the screen itself may be fast enough)                                                                                          |

Things that are the **same on both**: the protocol, the BLE link, the
buttons, the case lights, the battery and USB handling in the model,
and the rule that the app never sleeps while it's open (see
[power.md](power.md#why-the-badge-never-sleeps)).

### Colour scheme

Each profile's `theme` in `apps/claude_buddy/buddy_profile.py` names
five colours, which `Theme` in `buddy_view.py` turns into pens. The
code is the source; keep this table in step with it.

| Theme key | Used for                                 | Badger | Tufty                             |
| --------- | ---------------------------------------- | ------ | --------------------------------- |
| `bg`      | Background                               | White  | Black                             |
| `fg`      | Header, body text, dividers and frame    | Black  | White                             |
| `title`   | Screen titles (e.g. "Allow Bash?")       | Black  | Claude orange, RGB (217, 119, 87) |
| `footer`  | Button labels ("A: Accept", "C: Exit")   | Black  | Light blue, RGB (110, 190, 255)   |
| `meta`    | Counts, today's tokens and the page line | Black  | Light green, RGB (140, 220, 140)  |

- **Badger:** black on white only. Its panel has four greys, but grey
  text was too faint to read, so every part is black.
- **Tufty:** white on black is Badgeware's own Tufty default. The
  three accent colours set the fixed parts apart from Claude's text.
  They look right on the device but haven't been checked for contrast
  or colour blindness.
- **Values:** each entry is either a `color` name (`"white"`) or an
  (r, g, b) tuple; `_color()` in `buddy_view.py` handles both.

## Where the code switches

The app picks behaviour from `badge.model`. Badgeware derives it from
`os.uname().machine`, so it is `"badger"`, `"tufty"` or `"blinky"`.
Badgeware v3 creates the `badge` object; older firmware (MicroPython
1.27, as on a Tufty from the factory) has only `badgeware.badge.MODEL`,
so the app needs v3 or later. `tools/badge_info.py` reports the model
from the host.

Everything that differs is in one place: a **profile** per badge in
`apps/claude_buddy/buddy_profile.py` (`BADGER`, `TUFTY`).
`__init__.py` picks it once from `badge.model`, and any other model
gets an error screen. Nothing else checks `badge.model`. A profile
holds:

- the `badge.mode()` flags, and whether the panel is e-ink (the
  first-frame waveform in `_present()`);
- the Badgeware loop quirks: `run_clears_screen` (the Tufty sets
  `badge.default_clear = None`) and `run_polls_buttons` (see below);
- the fonts and colours, which `buddy_view.py` uses. The layout is
  derived from the screen size and font heights, so the badges share
  it;
- the backlight levels and idle time (`None` on the Badger);
- the refresh timings (`Refresh`: settle, status throttle, hold after
  A/B), **one set for USB power and one for battery**
  (`profile.refresh(on_usb)`). The painter gets the current set every
  pass. The Badger uses the e-ink timings on both power sources; the
  Tufty redraws live on USB power and uses the e-ink timings on
  battery.

Adding a badge means adding a profile.

**Why `default_clear = None`:** on the Tufty, Badgeware's `run()`
clears the framebuffer and sends it to the LCD every loop, for apps
that redraw every frame. This app draws only when the painter says so,
so without it the screen went blank one frame after each paint. With
no clear colour, each loop re-sends the last screen drawn. The
Badger's `run()` does neither.

**Why `update()` doesn't poll the buttons on the Tufty:** the Tufty's
`run()` also calls `badge.poll()` every loop. `badge.pressed()` reports
what changed since the previous poll, so a second poll in `update()`
wiped out every press: A/B, UP/DOWN and C did nothing. `update()` polls
only where `run()` doesn't (`run_polls_buttons` in the profile).

**Live refresh (Tufty on USB power):** the Tufty's `refresh_usb` is
`LIVE_REFRESH`: no settle, throttle or hold, "No sessions" at once,
and `live=True`. With `live`, the painter compares the whole screen
tuple instead of `screen_key`, so the battery and token labels repaint
too, and the app tells the model to show today's tokens in full
(`model.exact_tokens`). The model still never checks the badge: the
app sets `exact_tokens` and `no_sessions_delay_ms` from the current
`Refresh` every pass. Unplugging USB is an urgent change, so the
switch back to the e-ink timings repaints straight away.

## To check on a Tufty

Already checked: a Tufty from the factory had MicroPython 1.27 (built
2026-04-10), too old for the app. After flashing v3.1.1 it runs the
same MicroPython fork (`bw-1.29.0-gc`) as the Badger, with Bluetooth
and `aioble`, and `badge.model` is `"tufty"` (14 November 2026).

On the device (14 November 2026): the app runs at 320×240, the
pairing screen stays up, it connects to Claude Desktop, and a prompt
offered on the badge is answered with A and B. Fonts were compared on
the panel: the pixel fonts (`smart` 16 px) needed fine vision, so the
Tufty uses MonaSans at sizes picked on the device. The Badger keeps its
pixel fonts for now: MonaSans is drawn with smoothed (grey) edges, and
grey was already too faint on its 4-grey e-ink. MonaSans with
antialiasing off is untried there.

- Paging with UP/DOWN and exiting with C: same fix as A/B, not yet
  tried separately.
- How fast is a full redraw with MonaSans? Live refresh redraws on
  every change (it still skips identical heartbeats).
- How much does dimming the backlight save? No measurements yet.
- What does the always-on display plus BLE draw from the battery?

## Adding to this page

When a change makes the badges behave differently, add a row here in
the same change. Mark anything that exists only as a plan
_Not implemented_, and say what the plan is. If the code sets a Tufty
value that hasn't been tried on hardware, say "untested placeholder" so
nobody mistakes it for working support.
