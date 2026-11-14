# Claude Buddy for Badgeware

A [Claude Desktop Hardware Buddy](https://github.com/anthropics/claude-desktop-buddy)
for Pimoroni's [Badgeware](https://badgewa.re) badges. It pairs over
Bluetooth LE with Claude Desktop on macOS or Windows, shows what Claude
is doing, and lets you **accept** or **deny** permission prompts from
the badge's buttons.

- **Target:** Badger 2350 (264×176, 4-grey e-ink).
- **Planned (phase 2):** Tufty 2350 (always-on colour LCD), with its own
  display profile for live updates. The layout and theme already adapt
  to the screen; see
  [Phase 2 design](#phase-2-design-tufty-display-switch).
- **Language:** MicroPython, running as a normal Badgeware app launched
  from the badge's menu.
- **License:** MIT.

> **Status: phase 1, not yet tested on hardware.** The protocol logic,
> text wrapping and BLE line framing are unit-tested on the host. All
> device files compile with `mpy-cross` and pass Pimoroni's lint rules.
> BLE behaviour and the on-screen layout still need a first run on a
> real badge.

## Screen

For a table of everything Claude Desktop sends and which parts the
badge shows, see
[What Desktop sends, and what the badge shows](docs/protocol.md#what-desktop-sends-and-what-the-badge-shows).

```
+------------------------------------------+
| Claude_A1B2C3              75% Connected |  device ID, battery, link status
+------------------------------------------+
| Allow Bash?                              |  last message from Claude
| rm -rf ./build && make release           |
|                                          |
+------------------------------------------+
|  A: Accept       B: Deny        C: Exit  |  button labels
+------------------------------------------+
```

When nothing needs an answer, the content area shows status instead:
Claude's latest reply, with the session counts and today's tokens on
the bottom row. The Accept and Deny labels disappear. Content longer
than the screen is split into pages, and the page number goes on the
right of the bottom row:

```text
| Done                                     |
| Claude: I renamed old_name to new_name   |
| in 4 files.                              |
| All 80 tests pass. The BLE module now... |
| also drops a link that has gone quiet.   |
| 0 running, 0 waiting, 31k today      1/2 |
+------------------------------------------+
|                                 C: Exit  |
+------------------------------------------+
```

- **Header:**
  - **Device identifier** `Claude_XXXXXX`: the Bluetooth name listed in
    Claude Desktop's **Connect** picker, so you can tell which device to
    pick.
    - It stays on screen even if Desktop gives the buddy another name.
      That name is reported back to Desktop but not shown.
    - The `XXXXXX` comes from the RP2350's unique chip ID, so it never
      changes across reboots. It's always shown in full: when space is
      short, the battery is dropped first and then the status is
      shortened.
  - **Battery:**
    - on battery, shown in 25% steps (`100%` … `25%`);
    - on USB power, `Charging` while the charger is charging (from
      Badgeware's `badge.is_charging()`), `Full` when it has stopped
      with the battery reading 95% or more, and `USB` otherwise (for
      example with no battery fitted). `Charging` changing to `Full`
      shows on the next refresh; it doesn't cause one by itself;
    - plugging in or unplugging shows within about 0.3 s. The USB-power
      pin is checked every loop, and a fresh battery reading is taken on
      each change. The cost is one e-ink refresh per plug or unplug;
    - below 20% it switches to 5% steps, and stays "low" until the
      reading is back to 25%.
  - **Link status:** `Not connected`, `Connected`, or `No data`
    (connected, but no heartbeat for 30 s). After 60 s with no
    heartbeat the badge drops the link and advertises again, so a
    silent connection (a phone's BLE scanner, another Mac) can't keep
    Claude Desktop out of the badge's only connection slot.
- **Content:** the latest message from Claude, always in black, using
  the bold `nope` pixel font (the same font as the header and footer).
  - **Needs you:**
    - a permission prompt you can answer (`Allow <tool>?` and the
      command or path), or
    - an approval Claude is waiting for but didn't send to the badge in
      answerable form. The title is Desktop's own summary (e.g.
      `approve: Bash`, or `Approval needed` if it sent none). The body
      shows the waiting tool call, or how many sessions are waiting.
  - **Status:**
    - Claude's one-line summary (the title);
    - session counts with today's output tokens (`31k today`, from the
      heartbeat's `tokens_today`), on the bottom row of every page.
      When they don't fit next to the page number they become
      `12 run, 3 wait, 1.2M today`, and are cut with `...` as a last
      resort. The page number is never dropped;
    - **Claude's latest reply**, starting `Claude:`:
      - the text of the last assistant turn Desktop sent;
      - simple markdown (`**`, backticks, `#` headings, code fences)
        removed, paragraphs kept;
      - capped at 3,000 characters and 40 paragraphs;
    - recent transcript lines;
    - the pairing instructions;
    - the result after you answer.
  - **No sessions:** when Claude Desktop reports no sessions open
    (`total` 0) for 5 s, the title becomes `No sessions`, with a hint
    to open one. Claude's last reply stays below as history, and the
    bottom row shows only today's tokens. The 5 s delay means closing
    one session and opening another doesn't cost two e-ink refreshes.
    Opening a session switches back within about 0.3 s.
  - **Not connected:** before the first connection (`Pair with Claude`)
    and after Claude Desktop disconnects (`Disconnected`), the content
    area shows the pairing instructions inside a thick black frame, set
    in from the screen edges and dividers with blank space round it.
    The title is centred, with a rule under it. The frame appears only
    on these screens, so at a glance the badge isn't showing Claude's
    data. It's drawn as part of the refresh the connection change
    already causes, so it costs no extra refresh.

    ```text
    +------------------------------------------+
    | Claude_A1B2C3          75% Not connected |
    +------------------------------------------+
    |                                          |
    |    ##################################    |
    |    #          Disconnected          #    |
    |    ##################################    |
    |    # In Claude Desktop: Developer > #    |
    |    # Open Hardware Buddy... >       #    |
    |    # Connect                        #    |
    |    # Pick Claude_A1B2C3             #    |
    |    ##################################    |
    |                                          |
    +------------------------------------------+
    |                                 C: Exit  |
    +------------------------------------------+
    ```

  - **Paging:** when the content is longer than the screen, **DOWN** and
    **UP** move through the pages. This works on both prompts and the
    status screen.
    - A prompt shows its full command or path, up to 2,000 characters,
      with the command's own line breaks kept. You can read all of it
      before pressing Accept.
    - The title repeats on every page. The page number (`2/3`) is on
      the right of the bottom row.
    - The view jumps back to page 1 when a new prompt or a new reply
      arrives. Routine status updates leave you on the page you're
      reading.
    - Each page turn is one e-ink refresh, made only when you press a
      button.
- **Footer:** button labels, each above its button.
  - `A: Accept` and `B: Deny` appear **only when there is a prompt the
    badge can answer**. Their presence is the signal that Claude needs
    a decision from you.
  - When Claude is waiting for an approval the badge **can't** answer,
    the A/B space says **`Answer in the Claude App`** instead. That
    covers three cases:
    - Desktop didn't send an answerable prompt;
    - the prompt's id can't be sent back exactly (not a string of at
      most 39 characters; see
      [Prompt ids](docs/protocol.md#badge--desktop)). The prompt is
      shown and the header still says `Connected`;
    - the header shows `No data` (no update for 30 s while still
      connected). Any prompt on screen stays visible, but A and B are
      hidden and the buttons do nothing, because Desktop has probably
      stopped listening. They come back as soon as Desktop's updates
      resume.
  - `C: Exit` is always shown.

```text
+------------------------------------------+
| Answer in the Claude App        C: Exit  |
+------------------------------------------+
```

An earlier version drew status text in dark grey, but that was too hard
to read on e-ink, so all text is black now. The fonts are constants at
the top of `apps/claude_buddy/buddy_view.py` (`BAR_FONT`, `TITLE_FONT`,
`BODY_FONT`). The firmware has 37 built-in pixel fonts to choose from.

There is no creature or animation. Nothing on screen moves.

## Buttons

| Button            | Action                                                    |
| ----------------- | --------------------------------------------------------- |
| **A**             | Accept: approve this tool call once (`"decision":"once"`) |
| **B**             | Deny (`"decision":"deny"`)                                |
| **C**             | Exit to the Badgeware menu                                |
| **DOWN** / **UP** | Next / previous page of a long prompt or reply            |
| HOME              | Exit to the menu (Badgeware default)                      |

A and B do nothing unless their labels are showing. UP and DOWN do
nothing unless the page number is showing. Each prompt is answered
at most once. A press blinks the case lights, so you get feedback
straight away without an extra e-ink refresh.

A and B only ever answer the prompt that is on the panel. If a newer
prompt arrives while the old one is still showing, or while the panel
is redrawing, a press does nothing until the new one has been drawn,
so you can't approve a command you haven't seen. Pressing A and B
together also does nothing.

### Case lights while Claude waits

On USB power, the case lights double-blink every 5 s while Claude is
waiting for an answer, both when the badge can answer it (A/B showing)
and when it can't ("Answer in the Claude App"). They stop as soon as
the request is answered, on the badge or in the app. On battery they
stay off to save charge. None of this causes an e-ink refresh.

## Power and screen refreshes

How the app saves power, what changes between USB power and battery,
and every timing constant are in [docs/power.md](docs/power.md). In
short:

- **Few e-ink refreshes.** Every Badger refresh is a full-screen flash
  of about 1–2 s, so the panel only refreshes when something you can
  see changes. A new prompt shows after about 0.3 s. Status-only
  changes (summary, transcript, counts) show at most every 15 s.
  Battery and tokens update along with other refreshes, so they can
  be a little out of date.
- **No sleep while the app is open.** Sleeping would turn the radio
  off and drop the link to Claude Desktop, and Bluetooth can't wake
  the badge. Battery life is therefore much shorter than for Badgeware
  apps that sleep. Exit the app (C) when you aren't using it.
- **Case lights on USB power only.** The "Claude is waiting" blink is
  off on battery.

## Install

You need a Badger 2350 running Badgeware firmware with Bluetooth. The
current [pimoroni/badger2350](https://github.com/pimoroni/badger2350)
releases build MicroPython with `bluetooth` (BTstack) and `aioble`.

1. **Double-tap RESET** on the back of the badge. It mounts as a USB
   drive named `BADGER`.
2. Copy the app onto the drive, using either:
   - `python3 tools/install.py`, which finds the drive on macOS,
     Windows or Linux (pass `--dest` to choose it), or
   - by hand: copy `apps/claude_buddy/` into the drive's `apps/` folder.
3. Eject the drive. The badge restarts into the menu, which now shows
   **Claude Buddy**.

## Connect to Claude Desktop

1. On the badge, open **Claude Buddy**. It shows `Pair with Claude`
   and its name (e.g. `Claude_A1B2C3`).
2. In Claude Desktop:
   1. Turn on developer mode (one-time): **Help → Troubleshooting →
      Enable Developer Mode**.
   2. Open **Developer → Open Hardware Buddy…**, click **Connect**, and
      pick the badge's name.
3. The header changes to `Connected`, then shows Claude's status.

Claude Desktop reconnects in the background while the app is running.
If you exit the app, the badge stops advertising; reopen it to
reconnect.

### macOS vs Windows

- **No OS-level pairing.** This firmware can't encrypt or bond (see
  [Security](#security)), so there is no passkey. Connect only from
  Claude Desktop's Hardware Buddy window.
  - **Windows:** don't add the badge in **Settings → Bluetooth**.
  - **macOS:** you don't need to pair it in System Settings.
- **macOS:** the first connection triggers the system's Bluetooth
  permission prompt for Claude. Allow it.
- **Windows passive scanning:** some Windows scanners never request a
  scan response. The badge therefore puts the NUS service UUID and a
  shortened `Claude` name in the main advertising packet, and the full
  `Claude_XXXXXX` name in the scan response.
- **Name caching:** both OSes cache device names. If you see an old
  name after changing firmware or apps, toggle Bluetooth off and on.

These notes come from the protocol reference and general BLE behaviour.
They haven't yet been checked against this badge on both platforms.

## Security

The BLE link is **unencrypted**. Badgeware's rp2 MicroPython builds
BTstack without the pairing/bonding API, so the passkey flow the
reference recommends isn't available. As a result:

- The status ack reports `"sec": false`, so Claude Desktop knows.
- Any nearby device could connect while the app runs (one connection at
  a time). Someone in radio range could also read what Claude Desktop
  sends.
- The badge only sends a decision when **you press A or B**, and only
  for the prompt on screen.
- Character-pack file pushes are refused.

Exit the app (C) when you aren't using it.

## Project layout

```
apps/claude_buddy/        the Badgeware app (copied to the badge)
  __init__.py             entry point: loop, buttons, refresh policy, exit
  buddy_model.py          protocol + state -> screen tuple (pure Python)
  buddy_ble.py            Nordic UART peripheral (MicroPython bluetooth)
  buddy_view.py           layout, paging and drawing (Badgeware screen API)
  buddy_painter.py        when to repaint, and which page (pure Python)
  buddy_rxlog.py          optional debug log of what Desktop sends
  buddy_lights.py         case-light blinks (pure Python)
  icon.png                24x24 menu icon (generated by tools/make_icon.py)
docs/protocol.md          the protocol subset implemented, and decisions
docs/power.md             power management: USB power vs battery
docs/devices.md           Badger (e-ink) vs Tufty (LCD) display differences
tests/                    host-side unit tests (CPython)
tools/install.py          copy the app to the badge's USB drive
tools/make_icon.py        regenerate icon.png (no dependencies)
```

## Development

### Making a change

1. Make the code changes, and run the host tests (below).
2. Put the badge in disk mode: **double-tap RESET** on the back. It
   mounts as a USB drive named `BADGER`.
3. Copy the app across: `python3 tools/install.py`.
4. Eject the drive.
5. If the badge doesn't restart into the menu by itself, press RESET
   once.
6. Run the app from the Badgeware menu: select the **Claude Buddy**
   icon and press **B**.

### Checks on the host

```bash
python3 -m unittest discover -s tests -v   # protocol, wrapping, paging, repaint policy, framing
ruff check .                               # Pimoroni's lint rules
pip install mpy-cross && mpy-cross apps/claude_buddy/buddy_model.py   # syntax check
npx --yes prettier@3.9.10 --check "**/*.md"   # Markdown formatting
```

Markdown is formatted with prettier (pinned version, settings in
`.prettierrc.json`). A pre-commit hook blocks commits whose staged
`.md` files aren't formatted. Turn it on once per clone:

```bash
git config core.hooksPath .githooks
```

`print()` output from the app (connects, disconnects, BLE errors) is
meant for the badge's USB serial REPL, e.g. in Thonny or `mpremote`. In
practice it may not show up there while the app runs; the receive log
below is more reliable.

### Logging what Claude Desktop sends

The app can write every line it receives from Claude Desktop to a file.
Logging is off unless that file already exists when the app starts.

The file lives in `/state`, not on the USB drive: apps can't write to
`/system` (the drive), which is read-only to MicroPython. So the log
isn't visible in disk mode; it's read over the USB cable with
[`mpremote`](https://docs.micropython.org/en/latest/reference/mpremote.html),
with nothing else (Thonny, another `mpremote`) holding the serial port.

1. Create the empty log file:
   `mpremote exec "open('/state/claude_buddy_rx.log','w').close()"`
2. Launch Claude Buddy from the menu (it checks for the file at launch)
   and use it as normal.
3. Exit the app with **C**. This writes any buffered lines and frees
   the serial connection.
4. Read the log over USB:
   `mpremote fs cat :/state/claude_buddy_rx.log`. A coding assistant
   such as Claude Code can run this itself once the app has exited, and
   read exactly what Desktop sent.
5. Turn logging off: `mpremote fs rm :/state/claude_buddy_rx.log` (and
   `:/state/claude_buddy_rx.log.old` if present).

Each line is `<ticks_ms> <tag> <text>`: `RX` for a line from Desktop,
`TX` for an Accept/Deny sent, `--` for connect/disconnect and skip
counts. Desktop sends a heartbeat several times a second, almost all
identical, so a received line that matches one of the last three is
skipped and counted (`-- 12 repeated lines skipped`). Lines are cut at
1,024 characters and written every 2 s. After 32 KB the file is moved
to `claude_buddy_rx.log.old` and a new one is started. Delete the file
to stop logging (this also works while the app runs). The log contains
your Claude session's commands and replies, so delete it when you're
done.

## Roadmap

- **Phase 1 (this): Badger 2350.**
  - BLE pairing with Claude Desktop.
  - Status display.
  - Accept/Deny/Exit.
  - Minimal e-ink refreshes.
  - Still to do on hardware:
    - check the fonts and layout on the panel;
    - tune the refresh thresholds;
    - confirm MTU negotiation and that long prompts arrive.
- **Phase 2: Tufty 2350** (when the hardware is available). See
  [Phase 2 design](#phase-2-design-tufty-display-switch) below.
- **Phase 3: power** (both badges). Measure first, then consider:
  - a longer advertising interval;
  - a lower CPU clock;
  - a slower loop when idle.
  - **Sleep while disconnected on battery.** After a few minutes with no
    Claude Desktop connection, show a "Sleeping, press any button"
    screen, then call `badge.sleep()` with no duration so only a button
    wakes it.
    - The menu records the running app before launching it, and
      `main.py` relaunches that app on any wake except RESET. A button
      press should therefore bring Claude Buddy straight back,
      advertising and ready to reconnect. This comes from reading
      `main.py` and needs testing.
    - Sleep isn't possible while connected (see
      [Why the badge never sleeps](docs/power.md#why-the-badge-never-sleeps)).
  - **Tufty backlight:** dim it when idle (the LCD is always on, so
    the backlight is likely its biggest draw), and use the front light
    sensor. In the Badger firmware `set_brightness()` is an empty stub,
    so check what the Tufty firmware provides
    ([pimoroni/tufty2350](https://github.com/pimoroni/tufty2350)).
- **Later:**
  - Raise the BLE link security if a future Badgeware firmware enables
    BTstack pairing/bonding. This will be its own piece of work and
    pull request.
- **Not planned:** a clock on screen, and folder push (including a
  pushed config file, which is deferred). See
  [Decisions](docs/protocol.md#decisions).
- **Ideas (unprioritized, low priority):**
  - **Battery icon instead of words.** The pixel fonts have no battery
    or charging symbols, so the header uses words (`75%`, `Charging`,
    `Full`, `USB`). An icon could be drawn from rectangles, as the
    Badgeware menu does (`firmware/apps/menu/ui.py`): a 16×8 outline
    with a 1 px terminal and a fill bar for the 25% steps, a small bolt
    while charging, and a solid fill when full. It takes about 17 px
    instead of up to 48 px, so the header would rarely drop it. Keep
    the text (`5%`) next to it when low, since 5% steps don't show in a
    12 px fill. Don't animate the fill while charging as the menu does:
    that would refresh the e-ink constantly. An alternative is a custom
    inline glyph registered with `image.add_glyph()` and written as
    `[bat:75]` in the header text.

### Phase 2 design: Tufty display switch

The Tufty has no display code yet. Its colour LCD is always on and
redraws without flashing, so the Badger's e-ink rules (which exist to
avoid refreshes) would only make it lag. Phase 2 adds a **display
profile** chosen from `badge.model` and moves every refresh decision
behind it.

The full comparison of the two displays, the planned Tufty profile,
where the code switches, and what to check on a Tufty are in
[docs/devices.md](docs/devices.md).

## References

Sources used to design and build this app. All links were checked on
2026-11-13. Firmware links point at `main` unless pinned to the version
the current firmware builds with.

### Claude Hardware Buddy protocol

- [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy):
  Anthropic's reference device (ESP32, C++). MIT.
- [REFERENCE.md](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md):
  the wire protocol. It defines the NUS UUIDs, heartbeat fields,
  `prompt`, permission decisions, the status ack, and timing.
  Summarised in [docs/protocol.md](docs/protocol.md).

### Other buddy implementations (ideas only, no code copied)

- [freemansoft/build-with-claude](https://github.com/freemansoft/build-with-claude):
  MicroPython buddies for the M5Stack Cardputer and Core2. Apache-2.0.
  - [`buddy/` on the `core2-support` branch](https://github.com/freemansoft/build-with-claude/tree/core2-support/buddy).
    Its docs cover:
    - BLE quirks;
    - Desktop sending `waiting` without a `prompt`;
    - the status ack envelope;
    - power measurements.
  - Upstream: [moremas/build-with-claude](https://github.com/moremas/build-with-claude).
- [amargandhi/claude-buddy-pico](https://github.com/amargandhi/claude-buddy-pico):
  a Pico 2 W buddy in C/BTstack. MIT. It covers:
  - the advertising layout;
  - passkey pairing on BTstack;
  - line buffering.

### Badgeware platform and docs

- [badgewa.re](https://badgewa.re) and the
  [Badgeware docs](https://badgewa.re/docs)
  ([source: pimoroni/badgeware-docs](https://github.com/pimoroni/badgeware-docs)).
- Pages in the docs:
  - [The three badges](https://github.com/pimoroni/badgeware-docs/blob/main/guides/badge-differences.md):
    Badger "sleeps between updates", plus display sizes and grey levels.
  - [badge API](https://github.com/pimoroni/badgeware-docs/blob/main/api/badge.md):
    `mode()`, buttons, battery, `sleep()` and wake reasons.
  - [rtc API](https://github.com/pimoroni/badgeware-docs/blob/main/api/rtc.md):
    alarms that can wake the badge.
  - [Buttons guide](https://github.com/pimoroni/badgeware-docs/blob/main/guides/buttons.md)
    and [Text guide](https://github.com/pimoroni/badgeware-docs/blob/main/guides/text.md).
  - [Your first app](https://github.com/pimoroni/badgeware-docs/blob/main/introduction/your-first-app.md):
    the app folder layout, the 24×24 `icon.png`, and disk mode.
  - [Update your firmware](https://github.com/pimoroni/badgeware-docs/blob/main/introduction/update-your-firmware.md).
  - [Downloading / networking](https://github.com/pimoroni/badgeware-docs/blob/main/guides/downloading.md):
    points at MicroPython's own `bluetooth` module.

### Badger 2350 firmware ([pimoroni/badger2350](https://github.com/pimoroni/badger2350), [releases](https://github.com/pimoroni/badger2350/releases))

- [board/mpconfigboard.cmake](https://github.com/pimoroni/badger2350/blob/main/board/mpconfigboard.cmake):
  turns on `MICROPY_PY_BLUETOOTH` with BTstack on the CYW43 radio.
- [board/manifest.py](https://github.com/pimoroni/badger2350/blob/main/board/manifest.py):
  freezes `aioble`.
- [ci/micropython.sh](https://github.com/pimoroni/badger2350/blob/main/ci/micropython.sh):
  pins the MicroPython fork (`bw-1.29.0-gc`) and picovector (`v3.1.0`).
- [modules/common/badgeware/\_\_init\_\_.py](https://github.com/pimoroni/badger2350/blob/main/modules/common/badgeware/__init__.py):
  - `run()`;
  - `launch()`, which calls `on_exit()` and exits on HOME;
  - `wait_for_button_or_alarm()`, which sleeps after 5 s on battery.
- [modules/common/badgeware/badge.py](https://github.com/pimoroni/badger2350/blob/main/modules/common/badgeware/badge.py):
  - `badge.update()` and its first-update full refresh;
  - the `mode()` bits (`FAST_UPDATE`, `NON_BLOCKING`);
  - battery readings and case lights.
- [modules/common/badgeware/state.py](https://github.com/pimoroni/badger2350/blob/main/modules/common/badgeware/state.py):
  `State` persistence in `/state/<app>.json`.
- [firmware/main.py](https://github.com/pimoroni/badger2350/blob/main/firmware/main.py):
  relaunches the last running app on wake (except RESET). This is the
  basis for the disconnected-sleep roadmap item.
- [firmware/apps/menu/\_\_init\_\_.py](https://github.com/pimoroni/badger2350/blob/main/firmware/apps/menu/__init__.py)
  and [firmware/apps/hydrate/\_\_init\_\_.py](https://github.com/pimoroni/badger2350/blob/main/firmware/apps/hydrate/__init__.py):
  stock app patterns.
- [modules/c/ssd1680/ssd1680.cpp](https://github.com/pimoroni/badger2350/blob/main/modules/c/ssd1680/ssd1680.cpp):
  the e-ink driver.
  - Every update is a full 4-grey refresh, and the speed setting is
    ignored.
  - It shows how colours quantise to the four levels (0x40 is dark
    grey, 0xC0 is white).
- [modules/c/input/input.cpp](https://github.com/pimoroni/badger2350/blob/main/modules/c/input/input.cpp):
  `pressed` is edge-detected on each `poll()`.
- [ci/ruff.toml](https://github.com/pimoroni/badger2350/blob/main/ci/ruff.toml):
  the lint rules mirrored in this repo's `ruff.toml`.
- [pimoroni/tufty2350](https://github.com/pimoroni/tufty2350): the
  Tufty 2350 firmware, for the planned port.

### Graphics library ([picovector-micropython v3.1.0](https://github.com/pimoroni/picovector-micropython/tree/v3.1.0))

- [api/image.py](https://github.com/pimoroni/picovector-micropython/blob/v3.1.0/api/image.py):
  - `text()` and `measure_text()`;
  - inline `[name]` markup, where `[[` is a literal `[`, hence the
    escaping in `buddy_view.py`.
- [api/color.py](https://github.com/pimoroni/picovector-micropython/blob/v3.1.0/api/color.py):
  the Badger e-ink greys `dark_grey` (0x40) and `light_grey` (0xC0).

### MicroPython and Bluetooth

- [MicroPython `bluetooth` module](https://docs.micropython.org/en/latest/library/bluetooth.html):
  the IRQ events, `gatts_*` and `gap_advertise` used in `buddy_ble.py`.
- [pimoroni/micropython @ bw-1.29.0-gc](https://github.com/pimoroni/micropython/tree/bw-1.29.0-gc),
  the fork Badgeware builds:
  - [ports/rp2/CMakeLists.txt](https://github.com/pimoroni/micropython/blob/bw-1.29.0-gc/ports/rp2/CMakeLists.txt):
    `MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING` is set only for
    NimBLE builds, so BTstack builds such as Badgeware have no
    pairing. That's why the link is unencrypted.
  - [extmod/btstack/modbluetooth_btstack.c](https://github.com/pimoroni/micropython/blob/bw-1.29.0-gc/extmod/btstack/modbluetooth_btstack.c):
    - notifications are queued when ACL buffers are full;
    - `config(mtu=...)` maps to `l2cap_set_max_le_mtu`;
    - MTU exchange events.
  - [extmod/btstack/btstack_config_common.h](https://github.com/pimoroni/micropython/blob/bw-1.29.0-gc/extmod/btstack/btstack_config_common.h):
    BTstack limits, including a single connection and a 512-byte ATT
    database.

### Tools

- [mpy-cross](https://pypi.org/project/mpy-cross/): MicroPython
  bytecode compiler, used as a syntax check.
- [Ruff](https://docs.astral.sh/ruff/): Python linter.
- [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html)
  and [Thonny](https://thonny.org): REPL access to see the app's
  `print()` output.

## Credits

- Protocol: [anthropics/claude-desktop-buddy](https://github.com/anthropics/claude-desktop-buddy)
  (MIT).
- Ideas were taken from these. No code was copied from either.
  - the M5Stack Core2/Cardputer buddy in
    [freemansoft/build-with-claude](https://github.com/freemansoft/build-with-claude)
    (Apache-2.0);
  - [amargandhi/claude-buddy-pico](https://github.com/amargandhi/claude-buddy-pico)
    (MIT).
- Platform: [Pimoroni Badgeware](https://badgewa.re).
