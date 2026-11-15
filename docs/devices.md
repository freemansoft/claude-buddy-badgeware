# Devices and display architectures

Claude Buddy targets two Badgeware badges. They share the RP2350, the
Bluetooth radio, the buttons and the app code, but their displays work
in opposite ways. This page is the one place that records every
behaviour that differs between them because of that.

- **Badger 2350:** e-ink. Supported (phase 1).
- **Tufty 2350:** colour TFT LCD. Supported (phase 2, step 1): the app
  runs at the Tufty's resolution with its own fonts and colours, but
  keeps the Badger's refresh rules for now. The live LCD profile is the
  next step; its entries below are marked _Not implemented_.

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
only make the screen lag, so the Tufty will get its own **display
profile** instead of reusing them.

| Setting                 | Badger 2350 (e-ink profile, today)                                       | Tufty 2350 (today; the LCD profile is the plan)                                                                                                  |
| ----------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `badge.mode()`          | `FAST_UPDATE \| NON_BLOCKING`                                            | `HIRES`                                                                                                                                          |
| What triggers a repaint | The screen key changes (`screen_key`: battery and tokens excluded)       | Same as the Badger. LCD profile _Not implemented_ (plan: **any** change)                                                                         |
| Urgent settle delay     | 300 ms                                                                   | 300 ms, same as the Badger (plan: none)                                                                                                          |
| Status-only changes     | Coalesced, at most one repaint every 15 s                                | Same 15 s throttle (plan: immediate)                                                                                                             |
| After A/B               | ~1 s hold, so the result and Desktop's follow-up share one refresh       | Same ~1 s hold (plan: no hold)                                                                                                                   |
| "No sessions" screen    | After 5 s with no sessions, so a quick close-and-open costs no refreshes | Same 5 s (plan: could be immediate)                                                                                                              |
| First frame             | Slowest, cleanest waveform, to clear ghosting from the menu              | Not needed                                                                                                                                       |
| Button reading          | `update()` calls `badge.poll()` each pass                                | Badgeware's `run()` calls `badge.poll()` each loop; `update()` uses that reading and doesn't poll                                                |
| Present                 | `display.update()`, non-blocking; painter waits while `display.busy()`   | `display.update()` on each paint; `run()` re-sends the framebuffer every loop, so `badge.default_clear = None` stops it clearing between paints  |
| Battery label           | 25% steps (5% when low), rides along with other repaints                 | Same as the Badger (plan: exact %, live)                                                                                                         |
| Tokens label            | Rounded (`31k`), rides along                                             | Same as the Badger (plan: live, e.g. `31,204`)                                                                                                   |
| Colours                 | Black on white; no grey text (too faint on e-ink)                        | White on black (Badgeware's Tufty default) for the header and body; titles orange, button labels light blue, counts/tokens/page line light green |
| Accents                 | None                                                                     | Not implemented (plan: e.g. highlight the title when the `emphasis` flag is set)                                                                 |
| Fonts                   | `nope` pixel font, sized for 264×176                                     | MonaSans (vector, from the firmware): 18 px header and footer, 20 px body, 24 px titles; pixel fonts as fallback                                 |
| Animation               | None: nothing on screen moves                                            | Not implemented (open question: a "working" indicator?)                                                                                          |
| Instant feedback        | Case-light blink on A/B, because the panel takes 1–2 s                   | Not implemented (the screen itself may be fast enough)                                                                                           |

Things that are the **same on both**: the protocol, the BLE link, the
buttons, the case lights, the battery and USB handling in the model,
and the rule that the app never sleeps while it's open (see
[power.md](power.md#why-the-badge-never-sleeps)).

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
  pass. Both badges use the e-ink timings on both power sources today.

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

The next step, a live LCD refresh for the Tufty, is planned for **USB
power only**; on battery the Tufty keeps the e-ink timings to save
power:

- `buddy_profile.py`: the Tufty's `refresh_usb` gets zero timings, and
  `Refresh` gains the key function (`screen_key` for e-ink, the whole
  tuple for live) and the label precision.
- `apps/claude_buddy/buddy_model.py`: stays display-agnostic. The
  battery and token labels take a precision argument (rounded vs
  exact).
- Tests: run the painter policy tests under both refresh sets.

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
- How fast is a full redraw? This decides whether the LCD profile
  draws only on change or every frame.
- How much does dimming the backlight save? No measurements yet.
- What does the always-on display plus BLE draw from the battery?

## Adding to this page

When a change makes the badges behave differently, add a row here in
the same change. Mark anything that exists only as a plan
_Not implemented_, and say what the plan is. If the code sets a Tufty
value that hasn't been tried on hardware, say "untested placeholder" so
nobody mistakes it for working support.
