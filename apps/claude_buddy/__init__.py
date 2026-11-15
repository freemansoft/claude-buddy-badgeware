"""Claude Buddy for Badgeware (Badger 2350 and Tufty 2350).

A Claude Desktop "Hardware Buddy": pairs over BLE (Nordic UART, line
JSON), shows the latest status from Claude, and answers permission
prompts with the badge buttons.

    A        Accept (approve once)
    B        Deny
    C        Exit to the Badgeware menu (HOME also works)
    UP/DOWN  Page through a long prompt or Claude's latest reply

Everything that differs between the badges (display mode, fonts,
colours, backlight, refresh timings, Badgeware loop quirks) is in the
badge's profile (buddy_profile), chosen once below from badge.model.

Refresh policy lives in buddy_painter.Painter: the screen is reduced
to a tuple (buddy_model.BuddyModel.screen) and the panel only
refreshes when that tuple or the page changes. Changes that need the
user (a prompt, a connection change, a page turn) repaint after a short
settle delay; status-only changes repaint at most every
``status_interval_ms`` of the profile's Refresh for the current power
source.
"""

import gc
import sys
import time

APP_DIR = "/system/apps/claude_buddy"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from buddy_backlight import Backlight  # noqa: E402
from buddy_lights import CaseLights  # noqa: E402
from buddy_model import ATTENTION_KINDS, S_KIND, BuddyModel, is_urgent  # noqa: E402
from buddy_painter import Painter  # noqa: E402
from buddy_profile import PROFILES  # noqa: E402
from buddy_rxlog import RxLog  # noqa: E402
from buddy_view import BuddyView  # noqa: E402

# -- tuning -----------------------------------------------------------------

# Refresh timings, fonts, colours and the backlight levels are per badge,
# in buddy_profile.
LOOP_SLEEP_MS = 20
# Ignore buttons briefly at launch so the menu's launch press can't
# count as an answer.
STARTUP_IGNORE_MS = 400
# How often to sample the battery level. The header shows it in 25%
# steps and it never causes a refresh by itself (except crossing into
# low). USB plug/unplug is checked every loop and does refresh (~0.3 s).
BATTERY_POLL_MS = 10000
# Case lights (no e-ink refresh): one blink acknowledges A/B; while
# Claude waits for an answer (on the badge or in the app) and USB power
# is present, a double blink every WAITING_BLINK_REPEAT_MS.
BLINK_MS = 150
BLINK_LEVEL = 0.6
WAITING_BLIP_MS = 120
WAITING_BLINK_REPEAT_MS = 5000

STATE_KEY = "claude_buddy"


# -- platform glue ------------------------------------------------------------


class _Store:
    """BuddyModel's settings store: Badgeware's State, which keeps
    ``/state/claude_buddy.json`` (name, owner, approve/deny counts).

    Every save() is a flash write, so the model only saves when a value
    changes or a decision is recorded, never per heartbeat. ``/state``
    is the writable filesystem; ``/system`` (the USB drive) is read-only
    to apps.
    """

    def load(self, defaults):
        State.load(STATE_KEY, defaults)

    def save(self, data):
        State.save(STATE_KEY, data)


_boot_s = time.time()
_battery = {}


def _read_battery():
    """Sample the battery ADC once; the result feeds both the header and
    the status ack (Desktop polls status every ~2 s, so caching avoids
    sampling the ADC that often)."""
    bat = {}
    try:
        volts = badge.battery_voltage()
        bat["pct"] = int(badge.battery_level())
        bat["mV"] = int(volts * 1000)
        bat["usb"] = bool(badge.usb_connected())
    except Exception as e:  # noqa: BLE001
        print("claude_buddy: battery read failed:", e)
    return bat


def _status():
    """The ``bat`` and ``sys`` parts of the status ack.

    Desktop polls status about every 2 s, so this must stay cheap: the
    battery is the cached reading from _poll_battery (every
    BATTERY_POLL_MS), not a fresh ADC sample. ``sys.up`` is seconds
    since the app started, not since the badge booted.
    """
    return {
        "bat": dict(_battery),
        "sys": {"up": int(time.time() - _boot_s), "heap": gc.mem_free()},
    }


def _display_busy():
    """True while the e-ink panel is still refreshing.

    The Badger runs with NON_BLOCKING, so display.update() returns at
    once and the 1-2 s refresh carries on in the background. The
    painter won't start another refresh until this is False, and A/B
    are ignored meanwhile (Painter.answerable_doc), because the user is
    still looking at the previous screen.
    """
    busy = getattr(display, "busy", None)
    return bool(busy()) if callable(busy) else False


def _present():
    """Push the framebuffer to the panel.

    On e-ink (profile.eink) the first frame after launching an app uses
    the slowest (cleanest) waveform to clear ghosting from the menu,
    same as badge.update(). badge.update() isn't used because it also
    polls the buttons, which would swallow a press made between our
    poll and the refresh.
    """
    first = badge.first_update and profile.eink
    if first:
        display.speed(0)
    display.update()
    if first:
        display.speed((badge.mode() >> 4) & 0xF)
    badge.first_update = False


def _set_backlight(level):
    """Tufty backlight, 0-1 (gamma-corrected by the driver; 0 is off)."""
    try:
        display.backlight(level)
    except Exception:  # noqa: BLE001, S110
        pass


def _any_button_pressed():
    for button in (BUTTON_A, BUTTON_B, BUTTON_C, BUTTON_UP, BUTTON_DOWN):
        if badge.pressed(button):
            return True
    return False


def _caselights(level):
    """Set the case lights (0 = off). Driven only by CaseLights, which
    calls this on changes, not every loop. The lights cost battery,
    which is why the waiting blink runs only on USB power."""
    try:
        badge.caselights(level)
    except Exception:  # noqa: BLE001, S110
        pass


# -- app ----------------------------------------------------------------------

profile = PROFILES.get(badge.model)
if profile is None:
    fatal_error("Claude Buddy", "Needs a Badger 2350 or Tufty 2350, not: " + str(badge.model))

# Badger: FAST_UPDATE | NON_BLOCKING. The driver currently ignores the
# speed bits (every refresh uses the same 4-grey waveform), but
# NON_BLOCKING lets the loop keep reading buttons and BLE while the
# panel refreshes (~1-2 s). Tufty: HIRES, 320x240.
badge.mode(profile.mode())

if profile.run_clears_screen:
    # On the Tufty, Badgeware's run() clears the framebuffer
    # (badge.clear()) and pushes it to the LCD (display.update()) every
    # frame, for apps that redraw every frame. This app draws only when
    # the painter says so, like on e-ink, so without this the screen
    # would go blank one frame after each paint. With no clear colour,
    # badge.clear() leaves the framebuffer alone and each frame re-sends
    # the last screen drawn.
    badge.default_clear = None

# Whether Badgeware's run() calls badge.poll() itself between our
# update() calls: the Tufty's does, the Badger's doesn't. update() must
# poll exactly once per pass, or button presses are lost.
_RUN_POLLS = profile.run_polls_buttons

gc.collect()
try:
    from buddy_ble import BuddyBLE

    ble = BuddyBLE()
except ImportError:
    fatal_error("Claude Buddy", "This firmware has no Bluetooth support.")

model = BuddyModel(ble.name, store=_Store(), status_provider=_status)
# The timings for the current power source are set every pass
# (painter.set_refresh); start with the battery ones.
_refresh = profile.refresh(False)
painter = Painter(
    BuddyView(profile),
    present=_present,
    busy=_display_busy,
    settle_ms=_refresh.settle_ms,
    status_interval_ms=_refresh.status_interval_ms,
)
print("claude_buddy: advertising as", ble.name)
# Debug log of what Desktop sends; off unless its file exists.
rx_log = RxLog()
if rx_log.enabled:
    print("claude_buddy: rx log ->", rx_log.path)

lights = CaseLights(
    _caselights,
    level=BLINK_LEVEL,
    ack_ms=BLINK_MS,
    blip_ms=WAITING_BLIP_MS,
    gap_ms=WAITING_BLIP_MS,
    repeat_ms=WAITING_BLINK_REPEAT_MS,
)

_started_ms = time.ticks_ms()
# Tufty backlight (no repaint): on battery it dims after the profile's
# idle time with nothing needing the user and no button press, and the
# first press only wakes it. A badge without one gets a no-op.
_bl = profile.backlight
backlight = Backlight(
    _set_backlight if _bl else None,
    bright=_bl.bright if _bl else 1,
    dim=_bl.dim if _bl else 1,
    idle_ms=_bl.idle_ms if _bl else 0,
    now=_started_ms,
)
_last_scr = None
_buttons_armed = False
_next_battery_ms = _started_ms


def _usb_present():
    """VBUS pin read, called every loop (cheap: no ADC). Falls back to
    the last battery reading if the firmware lacks usb_connected()."""
    try:
        return bool(badge.usb_connected())
    except Exception:  # noqa: BLE001
        return _battery.get("usb", False)


def _is_charging():
    """badge.is_charging(): USB present and the charger's status pin says
    charging. False on battery, or if the firmware lacks it."""
    try:
        return bool(badge.is_charging())
    except Exception:  # noqa: BLE001
        return False


def _poll_battery(now):
    """USB presence every loop (one pin read) so plug/unplug shows within
    the settle delay; the battery ADC every BATTERY_POLL_MS, or straight
    away when USB changes, so the label never shows a stale charging
    voltage as a percentage."""
    global _next_battery_ms
    usb_changed = model.set_usb(_usb_present())
    if not usb_changed and time.ticks_diff(now, _next_battery_ms) < 0:
        return
    _next_battery_ms = time.ticks_add(now, BATTERY_POLL_MS)
    _battery.clear()
    _battery.update(_read_battery())
    # Charging state is for the header only; the status ack's "bat" keeps
    # the reference's fields (pct, mV, usb).
    model.set_battery(_battery.get("pct"), _battery.get("usb", False), _is_charging())


def update():
    """One pass of the app loop; Badgeware's run() calls it repeatedly.

    Order matters:
    0. Read the buttons once per pass: badge.poll() here on the
       Badger. On the Tufty, run() has just called badge.poll() and
       we use its reading (see _RUN_POLLS); a second poll would lose
       every press.
    1. Power: USB presence every pass, the battery ADC every
       BATTERY_POLL_MS.
    2. BLE: handle received lines (replies go straight back), connects
       and disconnects; drop a link silent for DEAD_LINK_MS; keep
       advertising while unconnected; flush the receive log.
    3. Buttons: C exits; A/B answer only the prompt on the panel
       (never one that hasn't been drawn), and not both at once.
    4. Lights, backlight, paging, then the painter, which refreshes the
       e-ink only when the screen key or page changed (see
       buddy_painter). While the Tufty's backlight is dim, the first
       button press only wakes it and is otherwise ignored.

    Timing and power: each pass ends with LOOP_SLEEP_MS (20 ms), so
    buttons and BLE are serviced about 50 times a second. The app
    never sleeps (BLE needs the radio on while connected), so battery
    life is much shorter than for Badgeware apps that do; see
    docs/power.md, "Why the badge never sleeps". Returning
    True exits to the menu.
    """
    global _buttons_armed, _last_scr
    # pressed() reports what changed since the previous poll. The
    # Tufty's run() has just polled, so polling again here would wipe
    # out every press it caught.
    if not _RUN_POLLS:
        badge.poll()
    now = time.ticks_ms()
    _poll_battery(now)
    refresh = profile.refresh(model.on_usb)
    painter.set_refresh(refresh)

    for kind, payload in ble.poll():
        if kind == "line":
            rx_log.note(now, "RX", payload)
            for reply in model.handle_line(payload, now):
                ble.send(reply)
        elif kind == "connect":
            model.on_connect(now)
            rx_log.note(now, "--", "connect")
            print("claude_buddy: connected")
        elif kind == "disconnect":
            model.on_disconnect()
            rx_log.note(now, "--", "disconnect")
            print("claude_buddy: disconnected")
    if model.is_dead(now) and ble.drop(now):
        rx_log.note(now, "--", "no heartbeat, dropping link")
        print("claude_buddy: no heartbeat, dropping link")
    ble.service(now)
    rx_log.service(now)

    if not _buttons_armed:
        # Latched once: comparing against _started_ms forever would turn
        # the buttons off again when the ticks wrap (~6 days).
        _buttons_armed = time.ticks_diff(now, _started_ms) >= STARTUP_IGNORE_MS
    # A press while the backlight is dim only wakes the screen: the user
    # can't see what A/B/C would act on.
    woke = _buttons_armed and backlight.enabled and _any_button_pressed() and backlight.press(now)
    if _buttons_armed and not woke:
        if badge.pressed(BUTTON_C):
            return True  # leave run(); Badgeware resets into the menu
        approve = badge.pressed(BUTTON_A)
        deny = badge.pressed(BUTTON_B)
        # A and B together is ambiguous: answer nothing.
        if approve != deny:
            # Only the prompt actually on the panel can be answered.
            message = model.permission_message(approve, now, painter.answerable_doc())
            if message is not None and ble.send(message):
                rx_log.note(now, "TX", message)
                model.record_decision(message)
                lights.ack(now)
                painter.hold(now, refresh.answer_hold_ms)

    scr = model.screen(now)
    # Waiting for an answer (badge prompt or "Answer in the Claude App")
    # on a live link: double blink, but only on USB power.
    lights.tick(
        now,
        scr[S_KIND] in ATTENTION_KINDS and model.on_usb and not model.is_stale(now),
    )
    # Bright while something needs the user or the screen just changed
    # urgently (a prompt, a connection change); dims when idle.
    backlight.tick(now, model.on_usb, scr[S_KIND] in ATTENTION_KINDS or is_urgent(scr, _last_scr))
    _last_scr = scr
    if woke:
        pass
    elif badge.pressed(BUTTON_DOWN):
        painter.turn(scr, 1)
    elif badge.pressed(BUTTON_UP):
        painter.turn(scr, -1)
    painter.tick(scr, now)
    time.sleep_ms(LOOP_SLEEP_MS)
    return None


def on_exit():
    """Called by Badgeware on C (after run() returns) or HOME."""
    _caselights(0)
    backlight.restore()
    rx_log.service(time.ticks_ms(), force=True)
    try:
        ble.close()
    except Exception as e:  # noqa: BLE001
        print("claude_buddy: ble close:", e)


run(update)
