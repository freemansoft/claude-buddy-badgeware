"""Claude Buddy for Badgeware (Badger 2350; Tufty 2350 planned).

A Claude Desktop "Hardware Buddy": pairs over BLE (Nordic UART, line
JSON), shows the latest status from Claude, and answers permission
prompts with the badge buttons.

    A        Accept (approve once)
    B        Deny
    C        Exit to the Badgeware menu (HOME also works)
    UP/DOWN  Page through a long prompt or Claude's latest reply

E-ink refresh policy lives in buddy_painter.Painter: the screen is
reduced to a tuple (buddy_model.BuddyModel.screen) and the panel only
refreshes when that tuple or the page changes. Changes that need the
user (a prompt, a connection change, a page turn) repaint after a short
settle delay; status-only changes repaint at most every
STATUS_MIN_INTERVAL_MS.
"""

import gc
import sys
import time

APP_DIR = "/system/apps/claude_buddy"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from buddy_lights import CaseLights  # noqa: E402
from buddy_model import ATTENTION_KINDS, S_KIND, BuddyModel  # noqa: E402
from buddy_painter import Painter  # noqa: E402
from buddy_rxlog import RxLog  # noqa: E402
from buddy_view import BuddyView  # noqa: E402

# -- tuning -----------------------------------------------------------------

# Coalesce bursts (e.g. heartbeat + status poll) into one refresh.
URGENT_SETTLE_MS = 300
# After A/B, wait this long so Claude's follow-up heartbeat (prompt
# cleared) lands in the same refresh as the "Allowed"/"Denied" result.
ANSWER_SETTLE_MS = 1000
# Status-only changes (msg, entries, counts) refresh at most this often.
STATUS_MIN_INTERVAL_MS = 15000
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
    return {
        "bat": dict(_battery),
        "sys": {"up": int(time.time() - _boot_s), "heap": gc.mem_free()},
    }


def _is_badger():
    return badge.model == "badger"


def _display_busy():
    busy = getattr(display, "busy", None)
    return bool(busy()) if callable(busy) else False


def _present():
    """Push the framebuffer to the panel.

    On the Badger the first frame after launching an app uses the
    slowest (cleanest) waveform to clear ghosting from the menu, same as
    badge.update(). badge.update() isn't used because it also polls the
    buttons, which would swallow a press made between our poll and the
    refresh.
    """
    first = badge.first_update
    if _is_badger() and first:
        display.speed(0)
    display.update()
    if _is_badger() and first:
        display.speed((badge.mode() >> 4) & 0xF)
    badge.first_update = False


def _caselights(level):
    try:
        badge.caselights(level)
    except Exception:  # noqa: BLE001, S110
        pass


# -- app ----------------------------------------------------------------------

if _is_badger():
    # The driver currently ignores the speed bits (every refresh uses the
    # same 4-grey waveform), but NON_BLOCKING lets the loop keep reading
    # buttons and BLE while the panel refreshes (~1-2 s).
    badge.mode(FAST_UPDATE | NON_BLOCKING)
else:
    badge.mode(HIRES)

gc.collect()
try:
    from buddy_ble import BuddyBLE

    ble = BuddyBLE()
except ImportError:
    fatal_error("Claude Buddy", "This firmware has no Bluetooth support.")

model = BuddyModel(ble.name, store=_Store(), status_provider=_status)
painter = Painter(
    BuddyView(),
    present=_present,
    busy=_display_busy,
    settle_ms=URGENT_SETTLE_MS,
    status_interval_ms=STATUS_MIN_INTERVAL_MS,
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
_buttons_armed = False
_next_battery_ms = _started_ms


def _usb_present():
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
    global _buttons_armed
    badge.poll()
    now = time.ticks_ms()
    _poll_battery(now)

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
    if _buttons_armed:
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
                painter.hold(now, ANSWER_SETTLE_MS)

    scr = model.screen(now)
    # Waiting for an answer (badge prompt or "Answer in the Claude App")
    # on a live link: double blink, but only on USB power.
    lights.tick(
        now,
        scr[S_KIND] in ATTENTION_KINDS and model.on_usb and not model.is_stale(now),
    )
    if badge.pressed(BUTTON_DOWN):
        painter.turn(scr, 1)
    elif badge.pressed(BUTTON_UP):
        painter.turn(scr, -1)
    painter.tick(scr, now)
    time.sleep_ms(LOOP_SLEEP_MS)
    return None


def on_exit():
    """Called by Badgeware on C (after run() returns) or HOME."""
    _caselights(0)
    rx_log.service(time.ticks_ms(), force=True)
    try:
        ble.close()
    except Exception as e:  # noqa: BLE001
        print("claude_buddy: ble close:", e)


run(update)
