"""Optional log of what Claude Desktop sends, for debugging.

Off unless the log file already exists. It lives in ``/state`` because
apps can't write to ``/system`` (the USB drive), which is read-only to
MicroPython (OSError 30). To turn it on from a host:
``mpremote exec "open('/state/claude_buddy_rx.log','w').close()"``.
Delete the file to turn it off; that also works while the app runs.

The log holds the text of your Claude session (prompts, commands,
replies), so delete it (and the ``.old`` copy) when you're done.

Each line is ``<ticks_ms> <tag> <text>``: ``RX`` for a line received
from Desktop, ``TX`` for a permission decision sent, ``--`` for
connect/disconnect and notes from the log itself.

Desktop sends heartbeats several times a second, almost all identical,
and a status poll every ~2 s. A received line that matches one of the
last ``recent_max`` received lines is skipped and counted, so the log
records changes rather than repeats. Lines are buffered and written at
most every ``flush_ms`` so flash writes stay rare. Once the file passes
``max_bytes`` it is renamed to ``<path>.old`` (replacing any older one)
and a new file is started.

Pure Python apart from ``os``, so it runs under CPython tests too.
"""

import os

try:  # MicroPython
    from time import ticks_add, ticks_diff
except ImportError:  # CPython (tests)

    def ticks_add(a, b):
        return a + b

    def ticks_diff(a, b):
        return a - b


LOG_PATH = "/state/claude_buddy_rx.log"
MAX_BYTES = 32 * 1024
# Long enough for a heartbeat with a full prompt and entries.
LINE_MAX = 1024
FLUSH_MS = 2000
MAX_PENDING = 40
# Heartbeats and status polls interleave, so compare against more than
# just the previous line.
RECENT_MAX = 3


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _text(data, limit):
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data[:limit])
        try:
            data = data.decode("utf-8")
        except UnicodeError:
            data = repr(data)
    elif not isinstance(data, str):
        data = str(data)
    data = data[:limit]
    return data.replace("\r", "\\r").replace("\n", "\\n")


class RxLog:
    """The receive log (see the module docstring). Costs nothing when
    off: the file check happens once, at construction, which is why the
    log file must exist before the app is launched. When on, flash is
    written at most every ``flush_ms``, never from BLE callbacks."""

    def __init__(
        self,
        path=LOG_PATH,
        max_bytes=MAX_BYTES,
        line_max=LINE_MAX,
        flush_ms=FLUSH_MS,
        max_pending=MAX_PENDING,
        recent_max=RECENT_MAX,
    ):
        self.path = path
        self.max_bytes = max_bytes
        self.line_max = line_max
        self.flush_ms = flush_ms
        self.max_pending = max_pending
        self.recent_max = recent_max
        self.enabled = _exists(path)
        self._pending = []
        self._dropped = 0
        self._recent = []
        self._skipped = 0
        self._flush_at = None

    def note(self, now, tag, data):
        """Queue one log line (no flash I/O here). A received line equal
        to one of the last ``recent_max`` is counted, not logged:
        Desktop repeats the same heartbeat several times a second, and
        logging each would fill the 32 KB file in under a minute."""
        if not self.enabled:
            return
        text = _text(data, self.line_max)
        if tag == "RX":
            if text in self._recent:
                self._skipped += 1
                return
            self._recent.append(text)
            if len(self._recent) > self.recent_max:
                self._recent.pop(0)
        if self._skipped:
            self._queue(now, "--", "{} repeated lines skipped".format(self._skipped))
            self._skipped = 0
        self._queue(now, tag, text)

    def _queue(self, now, tag, text):
        """Buffer a line for the next flush. At most ``max_pending``
        lines are held between flushes (bounded RAM); extras are counted
        and reported as "lines dropped (buffer full)"."""
        if len(self._pending) >= self.max_pending:
            self._dropped += 1
            return
        self._pending.append("{} {} {}".format(now, tag, text))
        if self._flush_at is None:
            self._flush_at = ticks_add(now, self.flush_ms)

    def service(self, now, force=False):
        """Write queued lines if due. Returns True if it wrote."""
        if not self.enabled or not self._pending:
            return False
        if not force and ticks_diff(now, self._flush_at) < 0:
            return False
        lines = self._pending
        self._pending = []
        self._flush_at = None
        if self._dropped:
            lines.append("{} -- {} lines dropped (buffer full)".format(now, self._dropped))
            self._dropped = 0
        try:
            size = os.stat(self.path)[6]
        except OSError:
            self.enabled = False  # file deleted: logging off
            return False
        try:
            if size > self.max_bytes:
                old = self.path + ".old"
                try:
                    os.remove(old)
                except OSError:
                    pass
                os.rename(self.path, old)
            with open(self.path, "a") as f:
                for line in lines:
                    f.write(line + "\n")
        except Exception as e:  # noqa: BLE001 - a flash error must not break the link
            print("claude_buddy: rx log write failed:", e)
            self.enabled = False
            return False
        return True
