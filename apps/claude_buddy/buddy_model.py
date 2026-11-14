"""Claude Hardware Buddy protocol state.

Pure Python with no Badgeware or BLE imports, so it runs unchanged on
MicroPython (on the badge) and CPython (unit tests in ``tests/``).

The model consumes newline-delimited JSON lines from Claude Desktop,
produces the JSON replies the device must send, and reduces everything
to a small immutable *screen tuple* that the view draws. The app only
repaints the e-ink panel when that tuple changes, which is what keeps
refreshes (and flashing) to a minimum.

Wire protocol: https://github.com/anthropics/claude-desktop-buddy
(REFERENCE.md). See docs/protocol.md in this repo for the subset used.
"""

import json

try:  # MicroPython
    from time import ticks_diff
except ImportError:  # CPython (tests): plain integer milliseconds

    def ticks_diff(a, b):
        return a - b


# Claude Desktop sends a heartbeat at least every 10 s; 30 s of silence
# means the link is dead (per the reference). The header says "No data"
# from HEARTBEAT_TIMEOUT_MS; at DEAD_LINK_MS the app drops the link and
# advertises again, so a silent central (a scanner, another Mac) can't
# hold the badge's only connection slot.
HEARTBEAT_TIMEOUT_MS = 30000
DEAD_LINK_MS = 60000

# Caps on strings kept from the host. The display can't show more than
# this anyway, and it bounds memory use on the badge.
MAX_MSG = 160
MAX_HINT = 2000
# Claude's latest reply (turn event text), shown on the status screen.
MAX_REPLY = 3000
MAX_PARAGRAPHS = 40
MAX_ENTRY = 160
MAX_ENTRIES = 8
MAX_NAME = 32
# A permission decision must echo prompt.id exactly, so the id is never
# cut or converted. The spec gives no type or length for it, so this
# follows Anthropic's reference firmware (claude-desktop-buddy
# src/data.h, char promptId[40]): a string of at most 39 characters.
# Any other id makes the prompt unanswerable on the badge ("Answer in
# the Claude App"); the reference would cut or drop it silently. See
# docs/protocol.md, "Prompt ids".
MAX_PROMPT_ID = 39

# Screen kinds. ``KIND_PROMPT`` and ``KIND_WAITING`` need the user
# (``emphasis`` is True); the rest are status. The Badger draws all text
# black; emphasis is kept for a future colour accent on the Tufty.
KIND_PAIR = "pair"
KIND_CONNECTED = "connected"
KIND_STATUS = "status"
KIND_PROMPT = "prompt"
KIND_ANSWERED = "answered"
KIND_WAITING = "waiting"
# Connected, but Desktop reports no sessions open (total == 0).
KIND_NO_SESSIONS = "none"

ATTENTION_KINDS = (KIND_PROMPT, KIND_WAITING)

# total must stay 0 this long before the "No sessions" screen replaces
# the status screen, so closing one session and opening another doesn't
# cost two e-ink refreshes.
NO_SESSIONS_DELAY_MS = 5000
NO_SESSIONS_HINT = "Open a chat or Claude Code session in Claude Desktop."

# Body line modes: wrap over as many lines as fit, one line only, or the
# status counts line (drawn on the bottom row of every page, next to the
# page marker, with today's tokens appended; empty text means tokens only).
WRAP = "w"
SINGLE = "s"
COUNTS = "c"

# Battery display. Shown in 25% steps so voltage jitter doesn't change
# the label; below LOW it shows 5% steps and becomes part of the change
# key (so it repaints on its own). It only stops being low at LOW_CLEAR,
# so a reading hovering around 20% can't flip it back and forth.
BATTERY_STEP = 25
BATTERY_LOW_PCT = 20
BATTERY_LOW_CLEAR_PCT = 25
BATTERY_LOW_STEP = 5
# On USB and not charging: "Full" from this reading up, else "USB" (not
# charging can also mean no battery is fitted, or charging paused).
BATTERY_FULL_PCT = 95

# Screen tuple field indexes. Fields before KEY_LEN decide whether the
# screen changed; the rest are "passengers", drawn whenever a repaint
# happens for another reason but never causing one themselves.
S_NAME = 0
S_STATUS = 1
S_KIND = 2
S_EMPHASIS = 3
S_TITLE = 4
S_LINES = 5
S_ACTIONABLE = 6
S_BATTERY_LOW = 7
# Identity of the document being shown (a prompt id, or which reply).
# The app goes back to page 1 when it changes, but not for routine
# status updates, so reading isn't interrupted.
S_DOC = 8
# USB power present. In the key and urgent, so plugging in or unplugging
# shows within the settle delay (one e-ink refresh each time).
S_ON_USB = 9
KEY_LEN = 10
S_BATTERY = 10
S_TOKENS = 11

_TOOL_SUMMARY_KEYS = (
    "command",
    "file_path",
    "path",
    "pattern",
    "url",
    "query",
    "description",
)

_UNSUPPORTED_CMDS = ("char_begin", "file", "chunk", "file_end", "char_end")

# A line is a heartbeat only if it carries at least one of these. Other
# one-shot messages (time sync, anything added later) must not clear
# the pending prompt the way a heartbeat without "prompt" does.
_HEARTBEAT_KEYS = (
    "total",
    "running",
    "waiting",
    "msg",
    "entries",
    "tokens",
    "tokens_today",
    "prompt",
)


def _to_int(value, default=0):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _echoable_id(value):
    """``prompt.id`` if it can be sent back exactly, else None (shown,
    but answered only in the app; see MAX_PROMPT_ID)."""
    if isinstance(value, str) and 0 < len(value) <= MAX_PROMPT_ID:
        return value
    return None


def _to_str(value, limit):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    if len(value) > limit:
        value = value[:limit]
    return value


def _one_line(text):
    return " ".join(text.split())


def format_tokens(n):
    """850, 1.2k, 31k, 1.2M, 12M."""
    if n < 1000:
        return str(n)
    for div, suffix in ((1000000, "M"), (1000, "k")):
        if n >= div:
            value = n / div
            if value < 10:
                text = "{:.1f}".format(value)
                if text.endswith(".0"):
                    text = text[:-2]
                return text + suffix
            return str(int(value)) + suffix
    return str(n)


def reply_paragraphs(text):
    """Claude's reply text -> tuple of plain paragraphs for a small screen.

    Strips the markdown that would show as clutter (code fences, heading
    marks, bold/italic markers, backticks) and keeps line breaks as
    paragraph breaks. Bounded by MAX_REPLY characters and MAX_PARAGRAPHS.
    """
    text = text[:MAX_REPLY]
    out = []
    for raw in text.split("\n"):
        line = raw.strip()
        if line.startswith("```"):
            continue
        while line.startswith("#"):
            line = line[1:]
        for mark in ("**", "__", "`"):
            line = line.replace(mark, "")
        line = _one_line(line)
        if line:
            out.append(line)
            if len(out) >= MAX_PARAGRAPHS:
                break
    return tuple(out)


def screen_key(scr):
    """The part of a screen tuple that decides whether to repaint."""
    return None if scr is None else scr[:KEY_LEN]


def is_urgent(new, old):
    """True if moving from screen ``old`` to ``new`` should repaint soon.

    Urgent: first paint, header changes (name / connection status /
    USB power plugged in or out), a change of screen kind, or any change
    while something needs the user. Everything else is a status-only
    change that the app throttles to keep e-ink refreshes rare.
    """
    if old is None:
        return True
    if new[S_NAME] != old[S_NAME] or new[S_STATUS] != old[S_STATUS]:
        return True
    if new[S_ON_USB] != old[S_ON_USB]:
        return True
    if new[S_KIND] != old[S_KIND] or new[S_ACTIONABLE] != old[S_ACTIONABLE]:
        return True
    return new[S_KIND] in ATTENTION_KINDS or new[S_KIND] == KIND_ANSWERED


class BuddyModel:
    """Protocol state for one Claude Buddy device.

    ``store`` persists small settings: any object with ``load(defaults)``
    (update the dict in place) and ``save(data)``. ``status_provider``
    returns ``{"bat": {...}, "sys": {...}}`` for the status ack.
    """

    def __init__(self, ble_name, store=None, status_provider=None):
        self.ble_name = ble_name
        self._store = store
        self._status_provider = status_provider
        self.settings = {"name": "", "owner": "", "appr": 0, "deny": 0}
        if store is not None:
            try:
                store.load(self.settings)
            except Exception as e:  # noqa: BLE001 - never fail startup on bad state
                print("buddy_model: settings load failed:", e)

        self.connected = False
        self.ever_connected = False
        self.last_heartbeat_ms = None
        self.heartbeat_seen = False

        self.total = 0
        self.running = 0
        self.waiting = 0
        self.msg = ""
        self.entries = ()
        self.tokens_today = None
        # When total last became 0 (ms), or None while sessions are open.
        self._no_sessions_since = None

        # Badge battery, set by the app via set_battery().
        self.battery_pct = None
        self.on_usb = False
        self.charging = False
        self.battery_low = False

        # Pending permission request: (id, tool, hint) or None.
        self.prompt = None
        # Last decision sent: (id, decision, tool) or None.
        self.answered = None
        # Latest tool call seen in a turn event: (name, summary) or None.
        self.last_tool = None
        # Claude's latest reply: tuple of paragraphs, and a counter that
        # changes with each new reply (the paging "document").
        self.reply = ()
        self.reply_seq = 0
        self._reply_lines = ()  # screen lines, built once per reply

    # -- connection lifecycle -------------------------------------------

    def on_connect(self, now_ms):
        """A central connected. Starts the stale/dead clocks from now (a
        full HEARTBEAT_TIMEOUT_MS before "No data") and forgets anything
        from the previous link."""
        self.connected = True
        self.ever_connected = True
        # Give the host a full timeout window before calling it stale.
        self.last_heartbeat_ms = now_ms
        self.heartbeat_seen = False
        self._clear_activity()

    def on_disconnect(self):
        """The link went (Desktop closed it, it timed out, or the app
        dropped it as dead). Shows the pairing screen titled
        "Disconnected"; any unanswered prompt is gone with the link."""
        self.connected = False
        self._clear_activity()

    def _clear_activity(self):
        """Forget the last link's live state, so a reconnect doesn't show
        (or blink for) a request from before. Claude's last reply and
        today's tokens stay: they're history, not live state."""
        self.total = 0
        self.running = 0
        self.waiting = 0
        self.msg = ""
        self.entries = ()
        self.last_tool = None
        self.prompt = None
        self.answered = None
        self._no_sessions_since = None

    def _silence_ms(self, now_ms):
        """Time since the last heartbeat. MicroPython ticks wrap, so a
        negative difference means "longer than ticks_diff can say"."""
        since = ticks_diff(now_ms, self.last_heartbeat_ms)
        return since if since >= 0 else DEAD_LINK_MS + 1

    def is_stale(self, now_ms):
        """Connected but no heartbeat for HEARTBEAT_TIMEOUT_MS (30 s, the
        reference's "treat the connection as dead"). The header shows
        "No data", A/B stop answering, and the waiting blink stops; the
        link itself is only dropped later, at DEAD_LINK_MS."""
        if not self.connected or self.last_heartbeat_ms is None:
            return False
        return self._silence_ms(now_ms) > HEARTBEAT_TIMEOUT_MS

    def no_sessions(self, now_ms):
        """Desktop has reported total == 0 for NO_SESSIONS_DELAY_MS."""
        if self._no_sessions_since is None or self.total > 0:
            return False
        since = ticks_diff(now_ms, self._no_sessions_since)
        return since < 0 or since >= NO_SESSIONS_DELAY_MS  # < 0: ticks wrapped

    def is_dead(self, now_ms):
        """No heartbeat for DEAD_LINK_MS: time to drop the link."""
        if not self.connected or self.last_heartbeat_ms is None:
            return False
        return self._silence_ms(now_ms) > DEAD_LINK_MS

    # -- inbound --------------------------------------------------------

    def handle_line(self, line, now_ms):
        """Process one received line. Returns a list of reply dicts."""
        if isinstance(line, (bytes, bytearray)):
            try:
                line = bytes(line).decode("utf-8")
            except UnicodeError:
                return []
        line = line.strip()
        if not line:
            return []
        try:
            msg = json.loads(line)
        except ValueError:
            print("buddy_model: bad json:", line[:60])
            return []
        if not isinstance(msg, dict):
            return []

        cmd = msg.get("cmd")
        if cmd is not None:
            return self._command(str(cmd), msg)
        if "evt" in msg:
            self._event(msg)
            return []
        # Time sync ({"time": [...]}) and unknown one-shots are ignored.
        if not any(key in msg for key in _HEARTBEAT_KEYS):
            return []
        self._heartbeat(msg, now_ms)
        return []

    def _heartbeat(self, msg, now_ms):
        """Desktop's state snapshot. In practice it arrives every
        70-200 ms, almost always unchanged, so this only updates fields:
        it never saves to flash, and the screen tuple stays equal (no
        e-ink refresh) unless something visible changed. Strings are
        capped (MAX_MSG, MAX_ENTRY, MAX_HINT) to bound memory. A
        heartbeat without ``prompt`` clears any pending prompt."""
        self.last_heartbeat_ms = now_ms
        self.heartbeat_seen = True
        # Treat absent counters / text as unchanged; the reference sends
        # full snapshots, but this is harmless if a host sends deltas.
        if "total" in msg:
            self.total = _to_int(msg.get("total"))
            if self.total > 0:
                self._no_sessions_since = None
            elif self._no_sessions_since is None:
                self._no_sessions_since = now_ms
        if "running" in msg:
            self.running = _to_int(msg.get("running"))
        if "waiting" in msg:
            self.waiting = _to_int(msg.get("waiting"))
        if "tokens_today" in msg:
            self.tokens_today = max(0, _to_int(msg.get("tokens_today")))
        if "msg" in msg:
            self.msg = _one_line(_to_str(msg.get("msg"), MAX_MSG))
        if "entries" in msg:
            raw = msg.get("entries")
            entries = []
            if isinstance(raw, list):
                for item in raw[:MAX_ENTRIES]:
                    text = _one_line(_to_str(item, MAX_ENTRY))
                    if text:
                        entries.append(text)
            self.entries = tuple(entries)

        # "prompt" is present only while a decision is needed, so its
        # absence clears it.
        prompt = msg.get("prompt")
        if isinstance(prompt, dict) and prompt.get("id"):
            self.prompt = (
                _echoable_id(prompt.get("id")),
                _one_line(_to_str(prompt.get("tool"), MAX_NAME)) or "tool",
                _to_str(prompt.get("hint"), MAX_HINT).strip(),
            )
        else:
            self.prompt = None
            self.answered = None

    def _event(self, msg):
        """A turn event (``{"evt":"turn", ...}``).

        Desktop sends one per message as soon as it exists, including
        user messages, tool results and thinking, and drops any over
        4 KB. Only assistant ``text`` becomes "Claude's latest reply"
        (a turn with no text keeps the previous reply), and the last
        ``tool_use`` is remembered for the "Answer in the Claude App"
        screen. The reply's screen lines are built here, once per
        reply, not on every screen() call.
        """
        if msg.get("evt") != "turn":
            return
        content = msg.get("content")
        if not isinstance(content, list):
            return
        if msg.get("role", "assistant") == "assistant":
            texts = [
                block.get("text")
                for block in content
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            ]
            paragraphs = reply_paragraphs("\n".join(texts))
            if paragraphs:
                self.reply = paragraphs
                self.reply_seq += 1
                self._reply_lines = tuple(
                    (WRAP, "Claude: " + p if i == 0 else p)
                    for i, p in enumerate(paragraphs)
                )
        found = None
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                found = block
        if found is None:
            return
        summary = ""
        inp = found.get("input")
        if isinstance(inp, dict):
            for key in _TOOL_SUMMARY_KEYS:
                value = inp.get(key)
                if isinstance(value, str) and value:
                    summary = value
                    break
        self.last_tool = (
            _one_line(_to_str(found.get("name"), MAX_NAME)) or "tool",
            _one_line(_to_str(summary, MAX_HINT)),
        )

    def _command(self, cmd, msg):
        """Desktop's ``cmd`` messages; each gets exactly one ack.

        ``status`` is polled about every 2 s and must stay cheap. The
        folder push (``char_*``/``file``/``chunk``) isn't implemented
        and is refused with ``ok: false``, as is anything unknown, which
        the reference allows. ``unpair`` is acked but erases nothing:
        this firmware can't bond.
        """
        if cmd == "status":
            return [self._status_ack()]
        if cmd == "name":
            return [self._set_setting("name", msg.get("name"))]
        if cmd == "owner":
            return [self._set_setting("owner", msg.get("name", msg.get("owner")))]
        if cmd == "unpair":
            # This firmware can't bond, so there are no keys to erase.
            return [{"ack": "unpair", "ok": True, "n": 0}]
        if cmd in _UNSUPPORTED_CMDS:
            return [{"ack": cmd, "ok": False, "n": 0, "error": "not supported"}]
        return [{"ack": cmd, "ok": False, "n": 0, "error": "unknown command"}]

    def _set_setting(self, key, value):
        """Store a name/owner. A missing value is refused (ok: false, as
        the reference does) instead of erasing the saved one. Flash is
        only written when the value changes; Desktop sends owner on
        every connect."""
        if not isinstance(value, str):
            return {"ack": key, "ok": False, "n": 0, "error": "missing name"}
        value = _one_line(_to_str(value, MAX_NAME))
        if value != self.settings.get(key):
            self.settings[key] = value
            self._save()
        return {"ack": key, "ok": True, "n": 0}

    def _status_ack(self):
        """The reply to ``{"cmd":"status"}``, shown in Desktop's Hardware
        Buddy stats panel.

        ``sec`` is always False: the link can't be encrypted on this
        firmware. ``appr``/``deny`` count decisions made on the badge.
        ``vel``, ``nap`` and ``lvl`` aren't implemented and are sent as
        0. ``bat``/``sys`` come from the app (cached battery reading, no
        fresh ADC sample per poll); a failure there still sends the ack.
        """
        data = {
            "name": self.display_name(),
            "sec": False,
            "stats": {
                "appr": self.settings.get("appr", 0),
                "deny": self.settings.get("deny", 0),
                "vel": 0,
                "nap": 0,
                "lvl": 0,
            },
        }
        if self._status_provider is not None:
            try:
                extra = self._status_provider() or {}
                for key in ("bat", "sys"):
                    if key in extra:
                        data[key] = extra[key]
            except Exception as e:  # noqa: BLE001 - a sensor glitch must not drop the ack
                print("buddy_model: status provider failed:", e)
        return {"ack": "status", "ok": True, "data": data}

    # -- outbound decisions ---------------------------------------------

    def can_answer(self, now_ms):
        """True if the badge may answer the pending prompt: connected,
        a prompt whose id can be echoed exactly (see MAX_PROMPT_ID), not
        yet answered, and the link not stale (header "No data"), since
        Desktop has probably stopped listening."""
        return (
            self.connected
            and self.prompt is not None
            and self.prompt[0] is not None
            and not (self.answered and self.answered[0] == self.prompt[0])
            and not self.is_stale(now_ms)
        )

    def prompt_doc(self):
        """The S_DOC value of the pending prompt's screen, or None."""
        if self.prompt is None:
            return None
        # An id that can't be echoed is never answerable, so its doc only
        # has to mark "a prompt" for paging.
        return "p:" + (self.prompt[0] if self.prompt[0] is not None else "?")

    def permission_message(self, approve, now_ms, shown_doc):
        """The permission message for the pending prompt, or None.

        ``shown_doc`` is the S_DOC of the answerable prompt actually on
        the panel (Painter.answerable_doc). A/B only answer that prompt:
        a newer one that hasn't been drawn yet is never approved unseen.

        Does not change state; call ``record_decision`` once it is sent.
        """
        if not self.can_answer(now_ms) or shown_doc != self.prompt_doc():
            return None
        return {
            "cmd": "permission",
            "id": self.prompt[0],
            "decision": "once" if approve else "deny",
        }

    def record_decision(self, message):
        """Remember a decision the app has sent: the prompt shows
        "Allowed"/"Denied" and can't be answered twice, and the
        appr/deny count is saved (one flash write per button press).
        The prompt stays until Desktop's next heartbeat drops it."""
        tool = self.prompt[1] if self.prompt else ""
        self.answered = (message["id"], message["decision"], tool)
        key = "appr" if message["decision"] == "once" else "deny"
        self.settings[key] = self.settings.get(key, 0) + 1
        self._save()

    # -- battery ----------------------------------------------------------

    def set_usb(self, usb):
        """Record USB power presence (cheap pin read, every loop).
        Returns True if it changed, so the app can take a fresh battery
        reading straight away."""
        usb = bool(usb)
        changed = usb != self.on_usb
        self.on_usb = usb
        if usb:
            self.battery_low = False
        else:
            self.charging = False
        return changed

    def set_battery(self, pct, usb, charging=False):
        """Record a battery reading (pct 0-100 or None if unreadable).
        ``charging`` is badge.is_charging(), which is only ever true on
        USB power."""
        self.on_usb = bool(usb)
        self.charging = self.on_usb and bool(charging)
        self.battery_pct = None if pct is None else max(0, min(100, int(pct)))
        if self.on_usb or self.battery_pct is None:
            self.battery_low = False
        elif self.battery_pct < BATTERY_LOW_PCT:
            self.battery_low = True
        elif self.battery_pct >= BATTERY_LOW_CLEAR_PCT:
            self.battery_low = False

    def battery_label(self):
        """Header battery text: ``Charging``/``Full``/``USB`` on USB power,
        else a percentage in 25% steps (5% steps once low, never below
        5%), or "" if unreadable. Coarse steps keep ADC jitter from
        changing it; it's a passenger, so a change never causes an
        e-ink refresh by itself (only battery_low and on_usb do)."""
        if self.on_usb:
            if self.charging:
                return "Charging"
            if self.battery_pct is not None and self.battery_pct >= BATTERY_FULL_PCT:
                return "Full"
            return "USB"
        if self.battery_pct is None:
            return ""
        step = BATTERY_LOW_STEP if self.battery_low else BATTERY_STEP
        pct = int((self.battery_pct + step / 2) // step * step)
        if self.battery_low:
            pct = max(pct, BATTERY_LOW_STEP)
        return "{}%".format(min(pct, 100))

    def tokens_label(self):
        """``31k today`` from the heartbeat's tokens_today, for the bottom
        row. A passenger: it climbs during every reply, and redrawing
        the e-ink for each change would flash constantly."""
        if self.tokens_today is None:
            return ""
        return format_tokens(self.tokens_today) + " today"

    # -- presentation ---------------------------------------------------

    def display_name(self):
        return self.settings.get("name") or self.ble_name

    def screen(self, now_ms):
        """Everything the view needs, as a comparable tuple:

        (name, status, kind, emphasis, title, lines, actionable,
         battery_low, doc, on_usb, battery_label, tokens_label)

        lines is a tuple of (mode, text); emphasis is True when the
        screen needs the user; doc identifies the document for paging.
        Only the first KEY_LEN fields decide whether to repaint (see
        screen_key); the battery and token labels ride along with
        repaints caused by something else.
        """
        base = self._screen(now_ms)
        kind = base[S_KIND]
        if kind in (KIND_PROMPT, KIND_ANSWERED) and self.prompt is not None:
            doc = self.prompt_doc()
        elif kind == KIND_STATUS:
            doc = "r:{}".format(self.reply_seq)
        elif kind == KIND_NO_SESSIONS:
            doc = "n:{}".format(self.reply_seq)
        else:
            doc = kind
        return base + (
            self.battery_low,
            doc,
            self.on_usb,
            self.battery_label(),
            self.tokens_label(),
        )

    def _screen(self, now_ms):
        """The first KEY_LEN-3 fields of the screen tuple. Screens in
        priority order, first match wins:

        1. not connected: pairing instructions ("Pair with Claude", or
           "Disconnected" after a link);
        2. a prompt: "Allow <tool>?" (A/B), or "Allowed/Denied <tool>"
           once answered;
        3. waiting without a prompt: Desktop's summary, answered in the
           app (Desktop sends no prompt for long commands or questions);
        4. no heartbeat yet since connecting;
        5. no sessions open for NO_SESSIONS_DELAY_MS;
        6. status: summary, Claude's reply, entries, counts.

        Called every loop, so it only assembles tuples from state that
        is already prepared (wrapping happens in the view, cached).
        """
        # The header always shows the advertised BLE name: it is what
        # Claude Desktop's device picker lists, so the user can match
        # them. A name set by Desktop ("name" command) is only reported
        # back in the status ack.
        name = self.ble_name
        if not self.connected:
            status = "Not connected"
        elif self.is_stale(now_ms):
            status = "No data"
        else:
            status = "Connected"

        if not self.connected:
            kind = KIND_PAIR
            title = "Disconnected" if self.ever_connected else "Pair with Claude"
            lines = (
                (WRAP, "In Claude Desktop: Developer > Open Hardware Buddy... > Connect"),
                (SINGLE, "Pick " + self.ble_name),
            )
            return (name, status, kind, False, title, lines, False)

        if self.prompt is not None:
            pid, tool, hint = self.prompt
            if self.answered and self.answered[0] == pid:
                verdict = "Allowed" if self.answered[1] == "once" else "Denied"
                lines = ((SINGLE, "Sent to Claude"),)
                return (name, status, KIND_ANSWERED, False, verdict + " " + tool, lines, False)
            # Keep the command's own line breaks (heredocs, scripts).
            lines = [(WRAP, part) for part in hint.split("\n") if part.strip()]
            if self.waiting > 1:
                lines.append((SINGLE, "{} more waiting".format(self.waiting - 1)))
            # Still shown when the link is stale ("No data") or the id
            # can't be echoed exactly, but not answerable: the footer
            # says to answer in the app instead.
            actionable = self.can_answer(now_ms)
            return (name, status, KIND_PROMPT, True, "Allow " + tool + "?", tuple(lines), actionable)

        if self.waiting > 0:
            # Desktop sometimes reports waiting without a prompt (e.g.
            # long commands, question dialogs), so it can only be answered
            # in the app; the footer says so. Title: Desktop's own summary
            # (e.g. "approve: Bash"). Body: what is waiting, when known.
            lines = []
            if self.waiting > 1:
                lines.append((SINGLE, "{} sessions waiting".format(self.waiting)))
            elif self.total <= 1 and self.last_tool is not None:
                tool, summary = self.last_tool
                # Desktop drops turn events over 4 KB, so the last tool
                # seen may not be the one waiting. Desktop's summary
                # names the tool ("approve: Bash", "(called Bash)"):
                # only show ours if it matches.
                if not self.msg or tool in self.msg:
                    lines.append((WRAP, tool + ": " + summary if summary else tool))
            title = self.msg or "Approval needed"
            return (name, status, KIND_WAITING, True, title, tuple(lines), False)

        if not self.heartbeat_seen:
            lines = ((WRAP, "Waiting for the first update from Claude."),)
            return (name, status, KIND_CONNECTED, False, "Connected", lines, False)

        if self.no_sessions(now_ms):
            # Claude's last reply stays as history; the bottom row shows
            # only today's tokens (an empty counts line), since
            # "0 running, 0 waiting" adds nothing.
            lines = ((WRAP, NO_SESSIONS_HINT),) + self._reply_lines + ((COUNTS, ""),)
            return (name, status, KIND_NO_SESSIONS, False, "No sessions", lines, False)

        title = self.msg or ("Idle" if self.running == 0 else "Working")
        counts = ((COUNTS, "{} running, {} waiting".format(self.running, self.waiting)),)
        entries = tuple((SINGLE, entry) for entry in self.entries)
        lines = counts + self._reply_lines + entries
        return (name, status, KIND_STATUS, False, title, lines, False)

    # -- persistence ----------------------------------------------------

    def _save(self):
        """Persist settings through the store (a flash write on the
        badge). Callers save only on real changes; a failure is logged
        and ignored so a flash error can't break the link."""
        if self._store is None:
            return
        try:
            self._store.save(self.settings)
        except Exception as e:  # noqa: BLE001 - flash errors must not break the link
            print("buddy_model: settings save failed:", e)
