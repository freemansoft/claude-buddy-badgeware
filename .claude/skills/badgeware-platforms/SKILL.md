---
name: badgeware-platforms
description: How the Badger 2350 (e-ink) and Tufty 2350 (colour LCD) differ under the same Badgeware firmware, with each difference backed by a file in vendor/badger2350 or vendor/tufty2350, and where Claude Buddy's own rules for handling them live. Load it whenever you write, change, review or plan Claude Buddy code that touches the display, the run loop, buttons, colours, start-up or exit, port something between the badges, bump the vendor submodules, or debug something that works on one badge but not the other - even if the user only says "make it work on the Tufty", "why is the Tufty screen black" or mentions a Blinky.
---

# Badger 2350 vs Tufty 2350

Both badges run Pimoroni's Badgeware firmware, built from near-identical
source trees, and app code looks portable. It isn't quite: the run
loop, the screen, the start-up flow and several built-in names differ.
Each row below was read from the firmware source pinned at **v3.1.1**
in the two submodules (`git submodule update --init` if `vendor/` is
empty). Read the cited file before relying on a row, and **re-check
every row against the new tag before bumping either submodule**.

This skill holds the firmware facts. Claude Buddy's own rules for
handling them are elsewhere (see the end), and they win where the two
seem to disagree, because they were tried on the hardware.

## The differences

|                                                      | Badger 2350                                                                                                       | Tufty 2350                                                                                                                                                                                       | Source                                                                                                                                           |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Screen                                               | e-ink, keeps its image unpowered, slow refresh                                                                    | colour LCD with a backlight, `display.backlight(0..1)`                                                                                                                                           | `vendor/tufty2350/modules/common/badgeware/__init__.py`                                                                                          |
| Resolution                                           | 264x176                                                                                                           | 160x120 (LORES, default) or 320x240 after `badge.mode(HIRES)`                                                                                                                                    | `vendor/tufty2350/modules/common/badgeware/badge.py` (`mode()`)                                                                                  |
| Default pen and clear                                | black on white                                                                                                    | white on black                                                                                                                                                                                   | `vendor/tufty2350/modules/common/badgeware/badge.py` (`Badge.__init__`)                                                                          |
| `color.white`, `color.black`                         | pure white (255, 255, 255), pure black                                                                            | an off-white (0xde, 0xee, 0xd6) and a dark navy (0x14, 0x1e, 0x28), from a Dawnbringer palette; `color.rgb(255, 255, 255)` and `color.rgb(0, 0, 0)` are true white and black                     | pimoroni/picovector `micropython/color.cpp` (`#ifdef TUFTY`), not vendored                                                                       |
| `run(update)` loop                                   | calls `update()` only; the app calls `badge.update()` to refresh                                                  | `badge.clear()` before and `display.update()` after every `update()`, every frame, and `badge.poll()` each loop                                                                                  | `vendor/badger2350/modules/common/badgeware/__init__.py`, `vendor/tufty2350/modules/common/badgeware/__init__.py` (`_run.__call__`)              |
| `badge.clear()`                                      | same                                                                                                              | does nothing to the screen when `badge.default_clear` is `None`, so the last frame drawn is re-sent                                                                                              | `vendor/tufty2350/modules/common/badgeware/badge.py` (`clear()`)                                                                                 |
| `badge.first_update`                                 | set False after the first `badge.update()`                                                                        | never set False                                                                                                                                                                                  | `vendor/badger2350/modules/common/badgeware/badge.py`                                                                                            |
| `NON_BLOCKING`                                       | defined                                                                                                           | not defined (NameError)                                                                                                                                                                          | `vendor/badger2350/modules/common/badgeware/badge.py`                                                                                            |
| `wait_for_button_or_alarm`                           | defined; deep-sleeps after its timeout on battery                                                                 | not defined                                                                                                                                                                                      | `vendor/badger2350/modules/common/badgeware/__init__.py`                                                                                         |
| Stock `main.py`                                      | reopens the last app (`state["running"]`) unless it is gone or the wake reason is `WAKE_RESET`                    | always opens the menu; eats the waking press first with `badge.poll()`                                                                                                                           | `vendor/badger2350/firmware/main.py`, `vendor/tufty2350/firmware/main.py`                                                                        |
| Menu                                                 | remembers the selected app                                                                                        | starts at the first app (`active = 0`), apps alphabetical, 6 per page                                                                                                                            | `vendor/tufty2350/firmware/apps/menu/__init__.py`                                                                                                |
| HOME                                                 | `do_exit()` (the app's `on_exit`), then `clear_running()`, which makes the menu the app to reopen, then `reset()` | `do_exit()`, then `reset()`; there is no `clear_running()`                                                                                                                                       | `vendor/badger2350/modules/common/badgeware/__init__.py`, `vendor/tufty2350/modules/common/badgeware/__init__.py` (`launch`, `quit_to_launcher`) |
| `reset()`                                            | HOME is also BOOT on both, so it waits for HOME to be released, then `machine.reset()` (a watchdog reboot)        | same                                                                                                                                                                                             | same files (`reset`)                                                                                                                             |
| Any other `machine.reset()` (`mpremote ... reset`)   | reopens the last app, because nothing changed `state["running"]`                                                  | the stock `main.py` opens the menu                                                                                                                                                               | `vendor/badger2350/firmware/main.py`, `vendor/tufty2350/firmware/main.py`                                                                        |
| Restart reason                                       | `powman.get_wake_reason()`                                                                                        | same codes: HOME and any `machine.reset()` give `WAKE_WATCHDOG` 0xf2 (242), RESET `WAKE_RESET` 0xf1 (241), double-tap `WAKE_DOUBLETAP` 5, a front button `WAKE_BUTTON_*`, USB `WAKE_VBUS_DETECT` | `vendor/tufty2350/modules/c/powman/bindings.c`, `vendor/badger2350/modules/c/powman/bindings.c`                                                  |
| Double-tap RESET                                     | disk mode                                                                                                         | disk mode, handled before `main.py` runs                                                                                                                                                         | `vendor/tufty2350/modules/common/main.py`                                                                                                        |
| Hold RESET                                           | the same power-off code is in the source                                                                          | case lights fade, then power off; a front button turns it on                                                                                                                                     | `vendor/badger2350/modules/c/powman/powman.c`, `vendor/tufty2350/modules/c/powman/powman.c` (`handle_long_press`)                                |
| Waking button press                                  | reaches the first `badge.poll()`                                                                                  | same; `run()` polls before the first `update()`, so the app sees it as pressed                                                                                                                   | `vendor/tufty2350/modules/c/input/input.cpp`                                                                                                     |
| Disk-mode drive                                      | `BADGER`                                                                                                          | `TUFTY`                                                                                                                                                                                          | `vendor/badger2350/board/mpconfigboard.cmake`, `vendor/tufty2350/board/mpconfigboard.cmake` (`PIMORONI_FATFS_LABEL`)                             |
| Bluetooth (BTstack), `aioble`                        | built in                                                                                                          | same                                                                                                                                                                                             | `vendor/badger2350/board/mpconfigboard.cmake`, `vendor/tufty2350/board/manifest.py` (`aioble`)                                                   |
| `State`, filesystem helpers                          | same                                                                                                              | same                                                                                                                                                                                             | `vendor/tufty2350/modules/common/badgeware/state.py`, `vendor/tufty2350/modules/common/badgeware/filesystem.py`                                  |
| Fonts                                                | same set                                                                                                          | same                                                                                                                                                                                             | `vendor/tufty2350/romfs/fonts`                                                                                                                   |
| Power source                                         | `badge.usb_connected()`                                                                                           | same                                                                                                                                                                                             | `vendor/tufty2350/modules/common/badgeware/badge.py`                                                                                             |
| Lint rules (`ci/ruff.toml`, what Pimoroni's CI runs) | same                                                                                                              | same; `tests/project/test_ruff_config.py` checks they stay identical                                                                                                                             | `vendor/badger2350/ci/ruff.toml`, `vendor/tufty2350/ci/ruff.toml`, `vendor/tufty2350/ci/python.sh`                                               |

## General rules for Badgeware app code

- **Never assume the screen keeps its image.** True on the e-ink only;
  on the Tufty the run loop clears the screen before every `update()`
  unless `badge.default_clear` is `None`.
- **Branch on `badge.model`** (`"badger"`, `"tufty"`), never on drive
  names or screen size guesses.
- **Guard Badger-only names** (`NON_BLOCKING`, `wait_for_button_or_alarm`,
  `badge.first_update`): only use them on the Badger code path.
- **Don't poll twice per loop on the Tufty.** `run()` already calls
  `badge.poll()`; a second poll wipes out `badge.pressed()`.
- **Define `on_exit()` at module level before calling `run()`.** The
  app's import blocks inside `run()`, and HOME looks `on_exit` up on
  the module, so anything defined after `run()` doesn't exist yet.
- **HIRES on the Tufty** for anything taller than 120 px.
- **`color.white`/`color.black` are tinted on the Tufty.** Use
  `color.rgb()` where true black or white matters.
- **Read the source in `vendor/`**, not only badgewa.re/docs: the docs
  can lag the source.

## How Claude Buddy handles them

Claude Buddy's own rules, which this skill doesn't repeat:

- **`docs/devices.md`:** every Badger vs Tufty behaviour difference in
  the app, "Where the code switches" (one profile per badge in
  `apps/claude_buddy/buddy_profile.py`, picked once from
  `badge.model`), why the Tufty sets `badge.default_clear = None`
  instead of redrawing every frame, why `update()` doesn't poll on the
  Tufty, the colour scheme, and what's still to check on a Tufty.
- **The `buddy-change` skill, "Device and display split":** nothing
  but `__init__.py` checks `badge.model`; a new difference is a new
  profile field; the Badger's refresh timings stay e-ink on both power
  sources.
- **`.claude/skills/buddy-change/references/power-invariants.md`:**
  the power rules (refreshes, never sleeping while connected, the
  Tufty backlight) and the tests that protect them.

One point to know when touching colours: the Tufty theme names
`"white"` and `"black"` (`color.white`, `color.black`), so it gets the
tinted pair from the table above, not pure white on black. It was
chosen on the device; see `docs/devices.md` "Colour scheme" before
changing it.

## Bumping the submodules

When Pimoroni releases new firmware and the badges are updated to it:

1. Check out the new tag in both `vendor/badger2350` and
   `vendor/tufty2350`.
2. Re-check every row above against the new source and fix the rows
   and citations (`tests/project/test_platform_skill.py` fails on a cited path
   that no longer exists).
3. Run `.venv/bin/ruff check .` and the tests:
   `tests/project/test_ruff_config.py` fails if the two `ci/ruff.toml` files
   now differ, and someone has to decide which rules to follow.
4. Update the version the README's References section names.
