"""Decides when the screen is repainted and which page is shown.

Pure Python: the view, the "push to panel" call and the busy check are
passed in, so it runs under CPython tests too.

Repaint policy (e-ink profile):
- Nothing is drawn unless (screen key, page) differs from what's shown.
  Battery and token labels aren't in the key; see buddy_model.
- Urgent changes (buddy_model.is_urgent) and page turns repaint after
  ``settle_ms``, which coalesces bursts and rapid button presses.
- Other changes (status text) also wait until ``status_interval_ms``
  has passed since the last paint.
- ``hold()`` delays painting, e.g. after A/B, so Claude's follow-up
  heartbeat lands in the same refresh.

Paging: the view splits long content into pages. The page resets to the
first one only when the screen's document (buddy_model S_DOC: a prompt
id, or which reply) changes. A routine status update leaves the reader
where they are, clamped if the content got shorter.

The timings come from the badge's profile (buddy_profile.Refresh), per
power source: the app calls set_refresh() every pass. A live Refresh
(the Tufty on USB power) has no settle, throttle or hold, and compares
the whole screen tuple, so the battery and token labels repaint too.
"""

from buddy_model import S_ACTIONABLE, S_DOC, is_urgent, screen_key

try:  # MicroPython
    from time import ticks_add, ticks_diff
except ImportError:  # CPython (tests)

    def ticks_add(a, b):
        return a + b

    def ticks_diff(a, b):
        return a - b


class Painter:
    """Owns the e-ink panel: what's on it, which page, and when to
    refresh. Every refresh on the Badger is a full-screen 4-grey update
    of about 1-2 s that visibly flashes, so the policy here is mostly
    about doing fewer of them (see the module docstring)."""

    def __init__(self, view, present, busy, settle_ms, status_interval_ms):
        """``present()`` pushes the framebuffer to the panel; ``busy()`` is
        True while a refresh is still in progress (the app runs the
        panel non-blocking). ``settle_ms`` and ``status_interval_ms`` are
        the starting timings; see set_refresh()."""
        self.view = view
        self._present = present
        self._busy = busy
        self.settle_ms = settle_ms
        self.status_interval_ms = status_interval_ms
        # Live: compare the whole screen tuple, passengers included.
        self.live = False

        self.page = 0
        self.doc = None
        self.shown_scr = None
        self.shown_state = None
        self.first_diff_ms = None
        self.last_paint_ms = None
        self.hold_until_ms = None

    # -- input --------------------------------------------------------------

    def set_refresh(self, refresh):
        """Use ``refresh``'s timings (a buddy_profile.Refresh) from now
        on. The app calls this every pass with the timings for the
        current power source; it is three attribute writes."""
        self.settle_ms = refresh.settle_ms
        self.status_interval_ms = refresh.status_interval_ms
        self.live = refresh.live

    def hold(self, now, ms):
        """Paint nothing for ``ms``. Used after A/B (the profile's
        ``answer_hold_ms``) so "Allowed"/"Denied" and Desktop's
        follow-up heartbeat, which clears the prompt, land in one
        refresh instead of two."""
        self.hold_until_ms = ticks_add(now, ms)
        self.first_diff_ms = None

    def answerable_doc(self):
        """S_DOC of the prompt the user can see with A/B showing, or None.

        None while nothing answerable is on the panel or a refresh is
        still in progress (the old screen is what the user is looking
        at). A/B must only answer this prompt; see
        BuddyModel.permission_message.
        """
        scr = self.shown_scr
        if scr is None or not scr[S_ACTIONABLE] or self._busy():
            return None
        return scr[S_DOC]

    def turn(self, scr, delta):
        """Move ``delta`` pages; returns True if the page changed."""
        self._sync_doc(scr)
        last = self.view.page_count(scr) - 1
        new = max(0, min(last, self.page + delta))
        changed = new != self.page
        self.page = new
        return changed

    # -- per loop -----------------------------------------------------------

    def tick(self, scr, now):
        """Repaint if due. Returns True if it painted."""
        self._sync_doc(scr)
        self.page = max(0, min(self.page, self.view.page_count(scr) - 1))

        state = (scr if self.live else screen_key(scr), self.page)
        if state == self.shown_state:
            self.first_diff_ms = None
            return False
        if self.hold_until_ms is not None:
            if ticks_diff(now, self.hold_until_ms) < 0:
                return False
            self.hold_until_ms = None
        if self.first_diff_ms is None:
            self.first_diff_ms = now

        due = ticks_add(self.first_diff_ms, self.settle_ms)
        page_turned = self.shown_state is not None and self.page != self.shown_state[1]
        if (
            not page_turned
            and not is_urgent(scr, self.shown_scr)
            and self.last_paint_ms is not None
        ):
            # A negative difference means the ticks wrapped (MicroPython,
            # after ~6 days without a paint): long enough, no throttle.
            since = ticks_diff(now, self.last_paint_ms)
            if 0 <= since < self.status_interval_ms:
                throttle = ticks_add(self.last_paint_ms, self.status_interval_ms)
                if ticks_diff(throttle, due) > 0:
                    due = throttle
        if ticks_diff(now, due) < 0 or self._busy():
            return False

        self.view.draw(scr, self.page)
        self._present()
        self.shown_scr = scr
        self.shown_state = state
        self.last_paint_ms = now
        self.first_diff_ms = None
        return True

    def _sync_doc(self, scr):
        """Back to page 1 when the document changes (a new prompt id or a
        new reply), but not for routine status updates, so a heartbeat
        several times a second can't yank the reader off their page."""
        if scr[S_DOC] != self.doc:
            self.doc = scr[S_DOC]
            self.page = 0
