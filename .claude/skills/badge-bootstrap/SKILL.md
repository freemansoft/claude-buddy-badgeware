---
name: badge-bootstrap
description: Set up or check a Badgeware badge (Badger 2350 or Tufty 2350) on USB for Claude Buddy - find out which badge is connected (from badge.model), whether its Badgeware firmware is the latest Pimoroni release, flash new firmware, then install the app and confirm it. Use whenever the user has a new or freshly unboxed badge, wants to update or reflash firmware, asks which badge or firmware version is plugged in, sees a badge misbehave after a firmware change, or is about to start work on a badge model (e.g. Tufty support), even if they don't say "bootstrap". Uses tools/badge_info.py, tools/flash_firmware.py and tools/install.py.
---

# Bootstrapping a badge

A new badge arrives with whatever firmware Pimoroni flashed at the
factory, often months old. Claude Buddy needs current Badgeware: it
uses the `badge` object, Bluetooth (BTstack) and `aioble`, and older
builds lack some of these. Before writing or testing code on a badge,
know exactly which badge it is and what firmware it runs, so that a
bug in the app isn't really an old firmware.

Most steps need the user's hands (buttons on the back of the badge),
so this is a guided procedure: run the scripts, tell the user exactly
which buttons to press and what they should see, and wait for them.

## Which badge: `badge.model`

The model comes from `badge.model` on the badge: `"badger"` or
`"tufty"` (Badgeware also has `"blinky"`, which isn't a target).
Badgeware derives it from `os.uname().machine`. Use it, not the USB
drive's name or the serial port's description. Those are hints, and
the RP2350 bootloader drive doesn't say which badge it is at all.
`tools/badge_info.py` reads `badge.model` and says where it got it:

- `badge.model`: the menu's own `badge` object;
- `badge.model (new Badge object)`: the usual case over `mpremote`,
  where the menu's object is gone, so the script makes one. This is
  still `badge.model`;
- `badgeware.badge.MODEL`: firmware too old to have a `badge` object
  (MicroPython 1.27), which Claude Buddy can't run on;
- `os.uname().machine`: Badgeware didn't load at all (see below).

## Steps

### 1. Identify the badge and check its firmware

The badge must be plugged in by USB and in normal mode (menu or an app
on screen), not USB disk mode. Then:

```bash
python3 tools/badge_info.py
```

It finds the badge among the serial devices (other boards are
ignored; if two badges are connected it asks for `--port`) and prints:
model, board, MicroPython build and build date, Bluetooth/aioble,
whether Claude Buddy is installed, and the latest release for that
model on GitHub with a verdict: current, OLDER, or newer.

- **The verdict compares dates.** The firmware doesn't record which
  Pimoroni release it is, only its MicroPython build and build date.
  "Current" means it was built within a few days of the latest
  release. Say so when reporting; don't claim the exact version.
- **It stops whatever was running** on the badge. Tell the user to
  press RESET afterwards to get back to the menu. Don't run it while
  the user is in the middle of using Claude Buddy.
- If `mpremote` is missing: `pip install mpremote`.

If the verdict is current and Bluetooth and aioble are present, skip
to step 4.

### 2. Choose the firmware image (ask the user)

Every release has two images, and `tools/flash_firmware.py` makes you
pick one each time, because the wrong one loses data:

- `--firmware-only`: replaces only the firmware. Apps and files stay.
  The right choice for a badge already in use.
- `--with-filesystem`: also replaces every app and file with
  Pimoroni's defaults. Claude Buddy, and possibly its saved settings
  in `/state`, are lost. Good for a new badge, because its default
  apps then match the new firmware.

Explain the trade-off and let the user choose. Don't pass `--yes`
(which skips the wipe confirmation) unless they have just said to
wipe it.

Before flashing a new release, skim its notes for changes that touch
Claude Buddy (Bluetooth, `badge` API, picovector, power):

```bash
gh release view -R pimoroni/<model>2350
```

### 3. Flash

Tell the user: with the badge's back facing them, **hold BOOT** (far
left), **tap RESET**, then let go of BOOT. A drive named `RP2350`
appears. Then run, with the model from step 1:

```bash
python3 tools/flash_firmware.py --model tufty --firmware-only
```

The script downloads the image from `pimoroni/<model>2350` releases
(cached in the system temp folder), checks it's a complete UF2 file,
copies it to the `RP2350` drive, and the badge restarts into the menu.
`--tag vX.Y.Z` picks an older release; `--download-only` just fetches
it. Pre-releases (such as `v4.0.0-ide.1`) are skipped by "latest";
only use one if the user asks.

Flashing the other model's firmware doesn't brick a badge (the
bootloader is in ROM), but nothing works until the right image is
flashed. That's why the model must come from step 1.

Then run `badge_info.py` again (press RESET afterwards). Expect
`Model ... (from badge.model)`, Bluetooth and aioble `yes`, and a
"current" verdict.

### 4. Install Claude Buddy

Tell the user to **double-tap RESET**; the badge mounts as a drive
(`BADGER` or `TUFTY`). Then:

```bash
python3 tools/install.py
```

On macOS and Linux it ejects the drive itself; on Windows (or with
`--no-eject`) ask the user to eject it. The badge restarts into the
menu, which lists Claude Buddy. `badge_info.py` should now say
`installed`.

Never reset the badge (RESET, `mpremote`, unplugging) while the drive
is still mounted: writes still in the computer's cache are lost, and
the app later fails with a `SyntaxError` in a truncated file. If
`install.py` says it couldn't eject, have the user eject before
anything else.

If `install.py` exits with "The copy failed", the app on the badge
wasn't changed: the new copy is built and checked in
`.claude_buddy.new` at the drive's root and swapped into `apps/` only
when every file matches the repo. Check the drive is still mounted
(and not full), then run it again. Don't fall back to copying by hand,
which has no check and leaves a half-copied app if it's interrupted.

Both badges are supported. The Tufty's MonaSans font comes from the
firmware's own filesystem (`/system/assets/fonts`); after a
`--firmware-only` flash of a badge whose files are older, check the
font is there, or the app falls back to the smaller pixel fonts (see
`docs/devices.md`).

**Updating the app without the buttons:** with the badge on USB in
normal mode, `mpremote connect <port> exec "import _msc"` switches it
to USB-drive mode (the same thing a double-tap of RESET does). The
mpremote call hangs or fails as the serial port goes away; that's
expected. Run `install.py` (which ejects on macOS and Linux), then ask
the user to press RESET once: ejecting doesn't restart a badge put
into drive mode this way.

### 5. Record what changed

- If the firmware version, MicroPython fork or picovector version
  differs from what the README's References section names (for
  example `bw-1.29.0-gc`, picovector `v3.1.0`), update those lines
  and follow the buddy-docs skill.
- If you found something about the Tufty on the way (its firmware,
  its `badge` API), add it to `docs/devices.md`, "To check on a
  Tufty" or the comparison table.
- Report to the user: model, firmware before and after (build dates),
  which image was flashed, and what's still untested.

## When things go wrong

- **No badge found:** it's in disk mode (double-tap RESET again to
  leave it, or eject), unplugged, or a charge-only cable.
- **No RP2350 drive:** BOOT must be held while RESET is tapped.
- **`badge_info.py` says `os.uname().machine`** as the model source:
  Badgeware failed to import, which usually means a damaged or
  non-Badgeware firmware. Reflash with `--with-filesystem` (after
  asking).
- **Installed and connected, but stuck on "Waiting for the first
  update from Claude"** (or `No data` that never clears): check the
  computer's Bluetooth before suspecting the firmware or the app. Walk
  the user through the README's
  [Troubleshooting](../../../README.md#troubleshooting) reset, and if
  in doubt, A/B against the `main` build. Don't reflash for this.
