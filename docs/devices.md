# Devices and display architectures

Claude Buddy targets two Badgeware badges. They share the RP2350, the
Bluetooth radio, the buttons and the app code, but their displays work
in opposite ways. This page is the one place that records every
behaviour that differs between them because of that.

- **Badger 2350:** e-ink. Supported (phase 1).
- **Tufty 2350:** colour TFT LCD. **No display code yet.** It will be
  added in phase 2, when the hardware is available. Every Tufty entry
  below is a plan, marked _Not implemented_.

Related pages: [power.md](power.md) (USB power vs battery, and why
e-ink refreshes cost power), [protocol.md](protocol.md) (the same on
both badges).

## Display hardware

|                        | Badger 2350                                       | Tufty 2350                                      |
| ---------------------- | ------------------------------------------------- | ----------------------------------------------- |
| Panel                  | E-ink, SSD1680 driver                             | Colour TFT LCD                                  |
| Resolution in this app | 264×176                                           | Not implemented (320×240 expected in `HIRES`)   |
| Colours                | 4 greys                                           | Full colour                                     |
| Holds image unpowered  | Yes                                               | No: always on while the app runs                |
| Update                 | Full-screen 4-grey refresh, ~1–2 s, visible flash | Not implemented (expected fast, no flash)       |
| Partial refresh        | No (the driver ignores the speed setting)         | Not needed                                      |
| Backlight              | None                                              | Yes. Not implemented (dim when idle is planned) |
| Light sensor           | Not used                                          | Front sensor. Not implemented (for backlight)   |
| Power while static     | ~None for the panel                               | Panel and backlight draw all the time           |
| Main display cost      | The _number_ of refreshes                         | Backlight on-time                               |

## How the app treats each display

The Badger's rules all exist to avoid e-ink refreshes. On an LCD they
only make the screen lag, so the Tufty will get its own **display
profile** instead of reusing them.

| Setting                 | Badger 2350 (e-ink profile, today)                                       | Tufty 2350 (LCD profile)                                                      |
| ----------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| `badge.mode()`          | `FAST_UPDATE \| NON_BLOCKING`                                            | Not implemented (`HIRES` is set as an untested placeholder)                   |
| What triggers a repaint | The screen key changes (`screen_key`: battery and tokens excluded)       | Not implemented (plan: **any** change, including battery and tokens)          |
| Urgent settle delay     | 300 ms                                                                   | Not implemented (plan: none, or one frame)                                    |
| Status-only changes     | Coalesced, at most one repaint every 15 s                                | Not implemented (plan: immediate)                                             |
| After A/B               | ~1 s hold, so the result and Desktop's follow-up share one refresh       | Not implemented (plan: no hold)                                               |
| "No sessions" screen    | After 5 s with no sessions, so a quick close-and-open costs no refreshes | Not implemented (plan: could be immediate)                                    |
| First frame             | Slowest, cleanest waveform, to clear ghosting from the menu              | Not needed                                                                    |
| Present                 | `display.update()`, non-blocking; painter waits while `display.busy()`   | Not implemented (plan: `display.update()` every repaint)                      |
| Battery label           | 25% steps (5% when low), rides along with other repaints                 | Not implemented (plan: exact %, live)                                         |
| Tokens label            | Rounded (`31k`), rides along                                             | Not implemented (plan: live, e.g. `31,204`)                                   |
| Colours                 | Black on white; no grey text (too faint on e-ink)                        | Not implemented (`Theme` sets light on dark as an untested placeholder)       |
| Accents                 | None                                                                     | Not implemented (plan: e.g. a coloured title when the `emphasis` flag is set) |
| Fonts                   | `nope` pixel font, sized for 264×176                                     | Not implemented (plan: larger fonts for 320×240)                              |
| Animation               | None: nothing on screen moves                                            | Not implemented (open question: a "working" indicator?)                       |
| Instant feedback        | Case-light blink on A/B, because the panel takes 1–2 s                   | Not implemented (the screen itself may be fast enough)                        |

Things that are the **same on both**: the protocol, the BLE link, the
buttons, the case lights, the battery and USB handling in the model,
and the rule that the app never sleeps while it's open (see
[power.md](power.md#why-the-badge-never-sleeps)).

## Where the code switches

The app picks behaviour from `badge.model` (`"badger"` or not). Today
that check is in only two places, and both Tufty branches are
placeholders:

- `apps/claude_buddy/__init__.py`: `_is_badger()` chooses
  `badge.mode()` and the first-frame waveform in `_present()`.
- `apps/claude_buddy/buddy_view.py`: `Theme` chooses the colours.

Phase 2 moves every refresh decision behind a display profile:

- `apps/claude_buddy/buddy_painter.py`: the repaint policy and paging
  already live here, with `present`, `busy` and the timings passed in.
  A profile argument will supply the key function (`screen_key` for
  e-ink, the whole tuple for the LCD) and the timings (no status
  throttle on the LCD). `__init__.py` picks the profile from
  `badge.model`.
- `apps/claude_buddy/buddy_model.py`: stays display-agnostic. The
  battery and token labels take a precision argument (rounded vs
  exact).
- `apps/claude_buddy/buddy_view.py`: layout is already derived from the
  screen size and font heights. Add Tufty fonts and accents.
- Tests: run the painter policy tests under both profiles.

## To check on a Tufty

- Does `badge.mode(HIRES)` give 320×240?
- Are labels centred in thirds still above the A/B/C buttons?
- How fast is a full redraw? This decides whether to draw only on
  change (planned) or every frame.
- What does `set_brightness()` do? In the Badger firmware it's an empty
  stub; check [pimoroni/tufty2350](https://github.com/pimoroni/tufty2350).
- What does the always-on display plus BLE draw from the battery?

## Adding to this page

When a change makes the badges behave differently, add a row here in
the same change. Mark anything that exists only as a plan
_Not implemented_, and say what the plan is. If the code sets a Tufty
value that hasn't been tried on hardware, say "untested placeholder" so
nobody mistakes it for working support.
