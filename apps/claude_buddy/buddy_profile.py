"""Everything that differs between the badges, in one place.

The app is the same on every badge: protocol, screens, layout, buttons,
case lights, battery handling. What differs is the display and how
Badgeware drives it, so each badge gets a Profile, chosen once at
start-up from ``badge.model`` (``PROFILES``). Nothing else in the app
checks ``badge.model``.

Refresh timings are per power source (``Profile.refresh(on_usb)``):
the Badger's e-ink needs them on both, and a profile can relax them on
USB power while keeping them on battery to save power. Today every
profile uses the e-ink timings everywhere.

Pure Python, so CPython tests can import this: colours are stored as
names or tuples and resolved by the view, and the display mode is a
function that reads Badgeware's flags only when the app calls it.
See docs/devices.md for why each value is what it is.
"""


class Refresh:
    """How eagerly the painter repaints (see buddy_painter).

    - ``settle_ms``: urgent changes and page turns wait this long, to
      coalesce bursts (a heartbeat plus a status poll) into one paint.
    - ``status_interval_ms``: status-only changes repaint at most this
      often.
    - ``answer_hold_ms``: after A/B, paint nothing for this long, so the
      result and Desktop's follow-up heartbeat share one paint.
    """

    def __init__(self, settle_ms, status_interval_ms, answer_hold_ms):
        self.settle_ms = settle_ms
        self.status_interval_ms = status_interval_ms
        self.answer_hold_ms = answer_hold_ms


# Every e-ink refresh is a 1-2 s full-screen flash, so changes are
# batched and status updates throttled.
EINK_REFRESH = Refresh(settle_ms=300, status_interval_ms=15000, answer_hold_ms=1000)


class Backlight:
    """Backlight levels (0-1) and the idle time before it dims, on
    battery. See buddy_backlight."""

    def __init__(self, bright, dim, idle_ms):
        self.bright = bright
        self.dim = dim
        self.idle_ms = idle_ms


class Profile:
    """One badge's settings.

    - ``mode``: a function returning the badge.mode() flags. Badgeware
      puts the flags (HIRES, ...) in builtins; MicroPython finds them
      by bare name but not with getattr(builtins, name), so the
      profile can't hold them as strings.
    - ``eink``: first frame after launch uses the slowest, cleanest
      waveform (clears ghosting from the menu).
    - ``run_clears_screen`` / ``run_polls_buttons``: this badge's
      Badgeware run() loop clears the framebuffer / calls badge.poll()
      every pass (see __init__.py).
    - ``fonts``: (bar, title, body) choices; see buddy_view._face.
    - ``theme``: colours for bg, fg, title, footer and meta, each a
      ``color`` attribute name or an (r, g, b) tuple.
    - ``backlight``: a Backlight, or None for a badge without one.
    - ``refresh_usb`` / ``refresh_battery``: a Refresh for each power
      source.
    """

    def __init__(
        self,
        model,
        mode,
        eink,
        run_clears_screen,
        run_polls_buttons,
        fonts,
        theme,
        backlight,
        refresh_usb,
        refresh_battery,
    ):
        self.model = model
        self.mode = mode
        self.eink = eink
        self.run_clears_screen = run_clears_screen
        self.run_polls_buttons = run_polls_buttons
        self.fonts = fonts
        self.theme = theme
        self.backlight = backlight
        self.refresh_usb = refresh_usb
        self.refresh_battery = refresh_battery

    def refresh(self, on_usb):
        return self.refresh_usb if on_usb else self.refresh_battery


# Badger 2350: 264x176 4-grey e-ink. Pixel fonts sized for its panel;
# black on white with no greys (grey text was too faint on e-ink).
BADGER = Profile(
    model="badger",
    mode=lambda: FAST_UPDATE | NON_BLOCKING,
    eink=True,
    run_clears_screen=False,
    run_polls_buttons=False,
    fonts=(("nope",), ("absolute",), ("nope",)),
    theme={"bg": "white", "fg": "black", "title": "black", "footer": "black", "meta": "black"},
    backlight=None,
    refresh_usb=EINK_REFRESH,
    refresh_battery=EINK_REFRESH,
)

# Tufty 2350: 320x240 colour LCD. Its pixel fonts were too small to read
# comfortably (its pixels are about 20% smaller than the Badger's), so it
# uses MonaSans, a vector font that ships with its firmware, at sizes
# picked on the device: 18 px header and footer (the largest that still
# fits them), 24 px titles, 20 px body. Pixel fonts are the fallback.
# White on black (Badgeware's Tufty default) with coloured fixed parts.
MONA = "/system/assets/fonts/MonaSans-Medium.af"
TUFTY = Profile(
    model="tufty",
    mode=lambda: HIRES,
    eink=False,
    run_clears_screen=True,
    run_polls_buttons=True,
    fonts=(((MONA, 18), "smart"), ((MONA, 24), "curse"), ((MONA, 20), "smart")),
    theme={
        "bg": "black",
        "fg": "white",
        "title": (217, 119, 87),  # Claude orange
        "footer": (110, 190, 255),  # light blue
        "meta": (140, 220, 140),  # light green
    },
    # 0.9 is the firmware's own start-up level (230 of 255).
    backlight=Backlight(bright=0.9, dim=0.1, idle_ms=60000),
    # The Badger's timings for now; a live LCD profile is planned for
    # USB power, keeping these on battery.
    refresh_usb=EINK_REFRESH,
    refresh_battery=EINK_REFRESH,
)

PROFILES = {"badger": BADGER, "tufty": TUFTY}
