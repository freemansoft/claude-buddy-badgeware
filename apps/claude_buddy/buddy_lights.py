"""Case-light patterns, without any e-ink refresh.

- ``ack()``: one short blink when A or B sends an answer.
- ``tick(now, attention)``: while ``attention`` is True (the app passes
  "Claude is waiting for an answer, on the badge or in the app, and USB
  power is present"), a double blink ("blip blip") straight away and
  then every ``repeat_ms``. It stops as soon as ``attention`` goes False.

Battery is left out by the caller: the lights cost charge on every
cycle, and on USB they're free.

Pure Python: the light is driven through the ``set_level`` callback, so
it runs under CPython tests too.
"""

try:  # MicroPython
    from time import ticks_add, ticks_diff
except ImportError:  # CPython (tests)

    def ticks_add(a, b):
        return a + b

    def ticks_diff(a, b):
        return a - b


class CaseLights:
    def __init__(
        self,
        set_level,
        level=0.6,
        ack_ms=150,
        blip_ms=120,
        gap_ms=120,
        repeat_ms=5000,
    ):
        self._set_level = set_level
        self.level = level
        self.ack_ms = ack_ms
        self.blip_ms = blip_ms
        self.gap_ms = gap_ms
        self.repeat_ms = repeat_ms
        self._ack_until = None
        self._cycle_start = None
        self._shown = 0

    def ack(self, now):
        self._ack_until = ticks_add(now, self.ack_ms)

    def _blip_on(self, now):
        phase = ticks_diff(now, self._cycle_start)
        if phase >= self.repeat_ms:
            # Move the cycle start forward so the difference stays small
            # (ticks wrap on MicroPython).
            self._cycle_start = ticks_add(
                self._cycle_start, (phase // self.repeat_ms) * self.repeat_ms
            )
            phase %= self.repeat_ms
        second = self.blip_ms + self.gap_ms
        return phase < self.blip_ms or second <= phase < second + self.blip_ms

    def tick(self, now, attention):
        """Set the lights for ``now``. Returns the level shown."""
        if attention:
            if self._cycle_start is None:
                self._cycle_start = now
            on = self._blip_on(now)
        else:
            self._cycle_start = None
            on = False
        if self._ack_until is not None:
            if ticks_diff(now, self._ack_until) < 0:
                on = True
            else:
                self._ack_until = None
        level = self.level if on else 0
        if level != self._shown:
            self._set_level(level)
            self._shown = level
        return level
