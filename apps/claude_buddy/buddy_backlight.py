"""Dims the Tufty's backlight after a quiet spell on battery.

The Tufty's LCD and backlight are on all the time the app runs, and the
backlight is likely its biggest draw. The app can't sleep while
connected (badge.sleep() would drop the Bluetooth link), so instead the
backlight dims when nothing needs the user, and the link stays up.

- ``tick(now, on_usb, keep_on)`` every pass: bright while on USB power
  or while ``keep_on`` (the app passes "something needs the user, or
  the screen just changed urgently": a prompt, a connection change);
  dim once ``idle_ms`` has passed since the last of those or the last
  button press.
- ``press(now)`` on any button press: returns True if the backlight
  was dim. The app then ignores that press, so the first press only
  wakes the screen and can't approve, deny or exit unseen.
- ``restore()`` on exit, so the menu isn't left dim.

Changing the backlight never repaints: the framebuffer is unchanged.

Pure Python: the backlight is driven through the ``set_level`` callback
(0 = off, 1 = full), so it runs under CPython tests too. Pass
``set_level=None`` for a badge without a backlight (the Badger); every
call is then a no-op.
"""

try:  # MicroPython
    from time import ticks_diff
except ImportError:  # CPython (tests)

    def ticks_diff(a, b):
        return a - b


class Backlight:
    def __init__(self, set_level, bright, dim, idle_ms, now=0):
        self._set = set_level
        self.bright = bright
        self.dim = dim
        self.idle_ms = idle_ms
        self._last_active = now
        self._level = None
        self.dimmed = False
        self._apply(bright)

    @property
    def enabled(self):
        return self._set is not None

    def _apply(self, level):
        if self._set is not None and level != self._level:
            self._level = level
            self._set(level)

    def _wake(self, now):
        self._last_active = now
        self.dimmed = False
        self._apply(self.bright)

    def press(self, now):
        """A button was pressed. True if it only woke the screen."""
        if not self.enabled:
            return False
        was_dim = self.dimmed
        self._wake(now)
        return was_dim

    def tick(self, now, on_usb, keep_on):
        if not self.enabled:
            return
        if on_usb or keep_on:
            self._wake(now)
            return
        if not self.dimmed and ticks_diff(now, self._last_active) >= self.idle_ms:
            self.dimmed = True
            self._apply(self.dim)

    def restore(self):
        """Back to full brightness (on exit)."""
        self.dimmed = False
        self._apply(self.bright)
