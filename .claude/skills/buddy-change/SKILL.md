---
name: buddy-change
description: Checklist for changing Claude Buddy's implementation (anything under apps/claude_buddy/) without breaking its power management or the Badger/Tufty display split. Use whenever you edit, refactor, fix or add a feature to the badge app, including the main loop, the painter's refresh policy, battery/USB handling, case lights, BLE timing, screens or layout, even if the request doesn't mention power or devices. Also use when asked to review such a change. For BLE/protocol message changes, use buddy-protocol as well; for the docs it touches, buddy-docs.
---

# Changing the Claude Buddy implementation

Claude Buddy runs on a battery badge that never sleeps while the app is
open (Bluetooth needs the radio on). Almost every part of the app was
tuned to save power, and on the Badger's e-ink panel, saving power and
avoiding screen flashes are the same thing: **fewer refreshes**. A
change that looks harmless (a new label, a timestamp, a tighter loop)
can quietly add a refresh per heartbeat, which happens 5–15 times a
second. The point of this skill is to catch that before it ships, and
to keep the docs that describe the power and device behaviour true.

## Before you edit

1. Read the parts of these that the change touches. They describe what
   the code is supposed to do, and you'll have to update them anyway:
   - `docs/power.md`: power consumers, USB vs battery, the constants;
   - `docs/devices.md`: Badger (e-ink) vs Tufty (LCD) differences;
   - `docs/protocol.md`: if the change touches messages or BLE.
2. Check whether the request reverses a recorded decision: the
   "Decisions" section of `docs/protocol.md` (e.g. no clock on screen)
   and "Not planned" in the README roadmap. If it does, say so and ask
   before building it.
3. Read `references/power-invariants.md` (in this skill). It lists each
   power rule, where it lives in the code, and which test protects it.
   Note which rules your change could affect.

## While editing

Keep these properties. Each one is explained, with its code location,
in the invariants reference.

- **Repaint only on a visible change.** Anything new on screen goes
  into the screen tuple from `BuddyModel.screen()`. Decide on purpose
  whether it is part of the key (`screen_key`, which triggers repaints)
  or rides along after the key (like battery and tokens). Fast-changing
  values (counters, clocks, percentages) ride along by default.
- **Urgent vs status.** Only things that need the user, or the header
  (connection, USB plug/unplug), are urgent in `is_urgent()`. Anything
  else is throttled to one repaint every `status_interval_ms` (the
  profile's `Refresh`).
- **No new periodic hardware work in the loop.** The loop runs every
  `LOOP_SLEEP_MS`. Work there must be a cheap check (a pin read, a
  ticks comparison) or rate-limited, like the battery ADC
  (`BATTERY_POLL_MS`) and the receive-log flush.
- **No flash writes per message.** `State.save()` only on a real
  change or a recorded decision.
- **Case lights:** the repeating blink stays USB-only; a blink must
  never cause a refresh.
- **Radio:** don't shorten the advertising interval or add BLE traffic
  without saying why; `ble.close()` on exit must still turn it off.
- **Never sleep while connected.** `badge.sleep()` powers down and
  drops the link. Sleep is only planned while disconnected on battery
  (README roadmap).

### Device and display split

Every difference between the badges lives in their profiles in
`buddy_profile.py` (`BADGER`, `TUFTY`): display mode, Badgeware loop
quirks, fonts, colours, backlight, and refresh timings per power
source. `__init__.py` picks the profile once from `badge.model`;
**nothing else may check `badge.model`**. A new difference is a new
profile field, not an `if` on the model.

The Tufty runs at 320×240 with its own fonts and colours but the
Badger's refresh timings; a live refresh on USB power (keeping the
e-ink timings on battery) is the next step. On the Tufty, Badgeware's
`run()` clears and sends the screen every loop
(`run_clears_screen`: `badge.default_clear = None` keeps the last
paint on screen, so don't remove it). It also polls the buttons every
loop (`run_polls_buttons`: `update()` must not poll again, or every
press is lost).

- Keep `buddy_model.py` display-agnostic: no `badge.model`, no
  timings that only make sense for e-ink.
- Put refresh decisions in `buddy_painter.py` and their timings in
  the profile's `Refresh`. The Badger's must stay the e-ink timings
  on both power sources (`test_profile.py` checks this).
- Check layout changes at both sizes: `TuftyViewTest` in
  `tests/test_device_logic.py` reruns the view tests at 320×240. On
  hardware, the Tufty needs a look as well as the Badger.
- If a change needs a Tufty decision you can't try on the device,
  record it in `docs/devices.md` as _Not implemented_ with the plan,
  rather than guessing.
- If a change makes the two badges behave differently, add a row to
  `docs/devices.md` in the same change.

### When a power rule has to change

Sometimes the right fix does cost power (e.g. a new urgent screen).
That's fine, but make it a visible decision: say so to the user, give
the cost (e.g. "one extra e-ink refresh per connect"), and update
`docs/power.md` so the doc keeps matching the code.

## After editing

1. Run the host checks and report the real output:

   ```bash
   python3 -m unittest discover -s tests -v
   ruff check .
   mpy-cross apps/claude_buddy/<changed file>.py   # if installed
   ```

2. Add or update tests for any power rule you touched. The painter and
   model tests use fake clocks, so refresh counts and throttles can be
   asserted directly (see `tests/test_painter.py`).
3. Update the docs in the same change, then format them (buddy-docs):
   - a constant's value changed: grep the docs for the old value and
     the constant's name (`docs/power.md` has a settings table, and the
     README repeats some numbers);
   - USB vs battery behaviour: `docs/power.md`;
   - Badger vs Tufty behaviour: `docs/devices.md`;
   - anything a user sees: the README.
4. Tell the user what you couldn't check on the host: the layout on
   the panel, real refresh timing, and power draw all need hardware.

## Reviewing a change

When asked to review, go through the invariants reference rule by rule
against the diff, and say which rules the change touches and whether
each still holds. A per-heartbeat refresh or an un-throttled status
repaint is a bug even if every test passes.
