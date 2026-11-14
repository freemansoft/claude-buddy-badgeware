# Power management

How Claude Buddy keeps its power use down, what changes between USB
power and battery, and which parts exist only because the Badger 2350
has an e-ink panel.

> **No measurements yet.** Nothing here has been checked with a power
> meter. The choices below come from how the hardware works and from
> Badgeware's own apps. Measuring is the first step of the Phase 3
> power work in the [Roadmap](../README.md#roadmap).

## Where the power goes

| Consumer            | When it draws                              | How the app limits it                                                                                                 |
| ------------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| **CPU**             | Always, while the app is open              | 20 ms idle (`time.sleep_ms`) at the end of every loop pass. No deep sleep (see [below](#why-the-badge-never-sleeps)). |
| **Bluetooth radio** | Always, while the app is open              | Advertises every 100 ms only while unconnected. Turned off when the app exits.                                        |
| **Display**         | E-ink: only while refreshing. LCD: always. | Badger: refresh only on a visible change (see [E-ink only](#e-ink-only-badger-2350)). Tufty: not implemented.         |
| **Case lights**     | Only when lit                              | The repeating "Claude is waiting" blink runs on USB power only.                                                       |
| **Battery ADC**     | Each sample                                | Sampled every 10 s, not on every status poll.                                                                         |
| **Flash writes**    | Each settings save                         | Saved only when a value changes or an answer is recorded, never per heartbeat.                                        |

## USB power vs battery

The app reads the USB-power (VBUS) pin on every loop pass, which is
cheap (no ADC). Plugging in or unplugging takes a fresh battery reading
at once and repaints within about 0.3 s.

Most of the app behaves the same on both. These are the differences:

| Behaviour                                | On USB power                                                                                                  | On battery                                                                                                       |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **"Claude is waiting" case-light blink** | Double blink every 5 s while Claude waits for an answer (on the badge or in the app) and the link isn't stale | **Off**, to save charge                                                                                          |
| **A/B acknowledge blink**                | One 150 ms blink                                                                                              | One 150 ms blink (kept: it's short and only on a press)                                                          |
| **Battery label in the header**          | `Charging`, `Full` (not charging, reading ≥ 95%), or `USB` (e.g. no battery fitted)                           | Percentage in 25% steps                                                                                          |
| **Low-battery warning**                  | Never "low"                                                                                                   | Below 20%: 5% steps, and the label repaints on its own. Stays low until the reading is back to 25% (hysteresis). |
| **Sleep**                                | Never                                                                                                         | Never (planned: sleep while disconnected; see [Planned](#planned-phase-3))                                       |
| **Loop rate, radio, refresh policy**     | Same                                                                                                          | Same                                                                                                             |

`Charging` changing to `Full` doesn't cause a repaint by itself. It
shows on the next one.

## Device-specific settings

Only the power-relevant differences are here. Every display difference
between the badges, with the planned Tufty profile, is in
[devices.md](devices.md).

| Setting        | Badger 2350 (e-ink)                                                                                | Tufty 2350 (colour LCD)                                 |
| -------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| Display power  | Only while refreshing, so the app keeps refreshes rare (see [E-ink only](#e-ink-only-badger-2350)) | Not implemented (the LCD is always on)                  |
| Refresh policy | Settle, throttle and hold timings in [devices.md](devices.md#how-the-app-treats-each-display)      | Not implemented                                         |
| Backlight      | None                                                                                               | Not implemented (dim when idle, using the light sensor) |
| Case lights    | As in [USB power vs battery](#usb-power-vs-battery)                                                | Not implemented                                         |

## E-ink only (Badger 2350)

An e-ink panel holds its image with no power and draws current only
while it refreshes. Badgeware's SSD1680 driver currently does a
full-screen 4-grey refresh on every update and ignores the speed
setting, so there is no partial refresh. Each refresh takes about
1–2 s and flashes the panel.

So on the Badger, power saving and avoiding flashing are the same
thing: make as few refreshes as possible. The app does this in
`apps/claude_buddy/buddy_painter.py`:

1. **Repaint only on visible change.** The screen is reduced to a small
   tuple, and the panel refreshes only when its key part changes.
   Desktop's heartbeats (every 70–200 ms) and `status` polls (every
   ~2 s) cause no refresh unless something on screen changed.
2. **Battery and tokens ride along.** Their labels are redrawn with
   other repaints, but a change in them never causes one. The
   exceptions are dropping below 20% on battery and plugging in or
   unplugging USB.
3. **Urgent changes settle for 300 ms** (a new prompt, a connection
   change, the stale-link warning), so a burst becomes one refresh.
4. **Status-only changes** (summary, transcript lines, counts) are
   coalesced into at most one refresh every 15 s.
5. **One refresh per answer.** After A or B, the app waits ~1 s so
   Desktop's follow-up heartbeat lands in the same refresh.
6. **"No sessions" waits 5 s**, so closing one session and opening
   another doesn't cost two refreshes.
7. **Page turns refresh only on a button press.**
8. **Non-blocking refresh.** `NON_BLOCKING` lets the loop keep serving
   buttons and BLE while the panel updates, and the painter won't start
   a new refresh until the current one has finished.
9. **Case lights for instant feedback.** A press blinks the case lights
   instead of drawing a "sending…" screen.

None of this applies to an always-on LCD, where these rules only make
the screen lag. That's why the Tufty will get its own profile (see
[devices.md](devices.md)).

## Why the badge never sleeps

Badgeware's docs describe the usual Badger pattern as: draw, then
`badge.sleep()` until a timer or button press. The stock apps do this
through `wait_for_button_or_alarm()`, which sleeps after 5 s on
battery. Claude Buddy deliberately calls neither:

- **Sleep is a power-down.** RAM is lost and waking restarts
  `main.py`. The Bluetooth radio is off while asleep, so the link to
  Claude Desktop drops. Desktop treats the device as gone after 30 s.
- **Bluetooth can't wake the badge.** The only wake sources are a
  button, an RTC alarm, the sleep timer, USB power and RESET.
- **Prompts arrive whenever Claude needs an answer, not on a
  schedule.** A badge that woke every N seconds would miss prompts or
  answer them late, and would have to reconnect each time.

So while the app is open it stays awake with the radio on, on USB
power and on battery alike. The 20 ms loop pause (`time.sleep_ms`) is
a CPU idle, not deep sleep. Battery life is therefore much shorter
than the "days on Badger" figure for apps that sleep. Exit the app (C)
when you aren't using it: that turns the radio off.

## Settings

All in `apps/claude_buddy/` unless noted.

| Constant                  | Value  | File             | Applies to | What it does                                         |
| ------------------------- | ------ | ---------------- | ---------- | ---------------------------------------------------- |
| `LOOP_SLEEP_MS`           | 20 ms  | `__init__.py`    | All        | CPU idle at the end of each loop pass (~50 passes/s) |
| `BATTERY_POLL_MS`         | 10 s   | `__init__.py`    | All        | Battery ADC sample interval                          |
| `URGENT_SETTLE_MS`        | 300 ms | `__init__.py`    | E-ink      | Settle before an urgent repaint                      |
| `ANSWER_SETTLE_MS`        | 1 s    | `__init__.py`    | E-ink      | Hold after A/B                                       |
| `STATUS_MIN_INTERVAL_MS`  | 15 s   | `__init__.py`    | E-ink      | Minimum gap between status-only repaints             |
| `BLINK_MS`                | 150 ms | `__init__.py`    | All        | A/B acknowledge blink                                |
| `BLINK_LEVEL`             | 0.6    | `__init__.py`    | All        | Case-light brightness                                |
| `WAITING_BLIP_MS`         | 120 ms | `__init__.py`    | USB power  | Length of each blink in the waiting double blink     |
| `WAITING_BLINK_REPEAT_MS` | 5 s    | `__init__.py`    | USB power  | Waiting double-blink period                          |
| `_ADV_INTERVAL_US`        | 100 ms | `buddy_ble.py`   | All        | BLE advertising interval while unconnected           |
| `_ADV_RETRY_MS`           | 2 s    | `buddy_ble.py`   | All        | Retry after advertising fails to start               |
| `BATTERY_STEP`            | 25%    | `buddy_model.py` | Battery    | Header percentage step                               |
| `BATTERY_LOW_PCT`         | 20%    | `buddy_model.py` | Battery    | Becomes "low": 5% steps, repaints on its own         |
| `BATTERY_LOW_CLEAR_PCT`   | 25%    | `buddy_model.py` | Battery    | Stops being "low"                                    |
| `BATTERY_LOW_STEP`        | 5%     | `buddy_model.py` | Battery    | Header step while low                                |
| `BATTERY_FULL_PCT`        | 95%    | `buddy_model.py` | USB power  | `Full` instead of `USB` when not charging            |
| `NO_SESSIONS_DELAY_MS`    | 5 s    | `buddy_model.py` | E-ink      | Delay before the "No sessions" screen                |
| `DEAD_LINK_MS`            | 60 s   | `buddy_model.py` | All        | Drop a silent link and advertise again               |

## Planned (Phase 3)

From the README's [Roadmap](../README.md#roadmap). Measure first, then
consider:

- a longer advertising interval;
- a lower CPU clock;
- a slower loop when idle;
- on battery, sleeping after a few minutes with no Claude Desktop
  connection, until a button is pressed;
- on the Tufty, dimming the backlight when idle and using the light
  sensor.
