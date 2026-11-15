"""Draws the Claude Buddy screen with the Badgeware drawing API.

Layout (shown for the Badger 2350, 264x176; everything is derived
from screen size and font heights, so the Tufty 2350 at 320x240 uses
the same layout with its own fonts and colours):

    +------------------------------------------+
    | Claude_A1B2C3              75% Connected |  header: id, battery, link
    +------------------------------------------+  divider
    | Allow Bash?                              |  title
    | rm -rf ./build && make release           |  body, wrapped
    |                                          |
    +------------------------------------------+  divider
    |  A: Accept       B: Deny        C: Exit  |  button labels
    +------------------------------------------+

All text is drawn at full contrast. Grey text was tried for status but
was too hard to read on e-ink. A prompt that can be answered on the
badge is signalled by the footer instead: "A: Accept" and "B: Deny"
appear only then.

Text is wrapped here rather than by the native layout, so long tokens
(paths, commands) are hard-broken across lines instead of clipped,
without inserting characters that could change what a command reads
as.
"""

from buddy_model import (
    COUNTS,
    KIND_PAIR,
    KIND_PROMPT,
    KIND_WAITING,
    S_KIND,
    S_ACTIONABLE,
    S_BATTERY,
    S_TOKENS,
    S_LINES,
    S_NAME,
    S_STATUS,
    S_TITLE,
    WRAP,
)

PAD = 4
# The not-connected screens ("Pair with Claude", "Disconnected") draw a
# thick frame around the content area, so they can't be mistaken for a
# screen with Claude's data on it. Black only, like all Badger text; it
# is drawn as part of the refresh the connection change already causes.
# The frame sits well inside the content area, with blank space all
# round it, so it reads as a box rather than as part of the dividers.
FRAME_MARGIN_X = 16  # space between the screen edge and the frame
FRAME_MARGIN_Y = 10  # space between the dividers and the frame
FRAME_W = 3  # frame thickness
FRAME_GAP = 4  # space between the frame and the text
# Inside the frame the title is centred, with a rule across the frame
# between it and the instructions, FRAME_GAP each side.
TITLE_RULE_W = 2  # thickness of that rule
TITLE_MAX_LINES = 2
LINE_GAP = 2
HEADER_GAP = 8
ELLIPSIS = "..."
# Upper bound on wrapped lines for one item (a 3,000-character reply is
# well under this); only stops pathological input.
MAX_WRAP_LINES = 400
# Shorter count labels for the bottom row when the full ones don't fit.
_SHORT_LABELS = ((" running", " run"), (" waiting", " wait"))
# Footer text in place of A/B when Claude waits for an approval the
# badge can't answer. The footer measures it and cuts it with "..." if
# it doesn't fit before "C: Exit" (it fits on both badges: 163 of
# 188 px in nope on the Badger, 191 of about 210 px in 18 px MonaSans
# on the Tufty).
APP_ONLY_NOTE = "Answer in the Claude App"

# Unicode punctuation Claude commonly sends, mapped to ASCII the ROM
# pixel fonts can draw. Anything else above Latin-1 becomes "?".
_SUBS = {
    0x00A0: " ",
    0x2010: "-",
    0x2011: "-",
    0x2013: "-",
    0x2014: "-",
    0x2018: "'",
    0x2019: "'",
    0x201C: '"',
    0x201D: '"',
    0x2022: "*",
    0x2026: "...",
    0x2190: "<-",
    0x2192: "->",
    0x2713: "v",
    0x2717: "x",
}


def plain(text):
    """Map text to characters the pixel fonts can draw (no markup)."""
    out = []
    for ch in text:
        o = ord(ch)
        if o < 0x20 or o == 0x7F:
            out.append(" ")
        elif o < 0x7F or 0xA0 < o <= 0xFF:
            out.append(ch)
        else:
            out.append(_SUBS.get(o, "?"))
    return "".join(out)


def escape(text):
    """Escape Badgeware text markup: "[" starts a glyph tag, "[[" is a
    literal "["."""
    return text.replace("[", "[[")


def _markup_active():
    """True if text() parses "[" as glyph markup, so "[[" draws one "[".

    picovector documents this markup, but on Badgeware v3.1.1
    (picovector v3.1.0) "[[" measures and draws as two brackets, even
    with a glyph registered. Escaping there would show every "[" from
    Claude doubled, so the view only escapes when "[[" really is one
    bracket wide. Uses the current screen.font."""
    try:
        return screen.measure_text("[[")[0] == screen.measure_text("[")[0]
    except Exception:  # noqa: BLE001
        return True


def _height(f, fallback=12):
    return int(getattr(f, "height", fallback) or fallback)


class Face:
    """A font at a size. ``size`` is 0 for a ROM pixel font (it has one
    size; passing a size would scale it up by that factor) or the pixel
    size a vector font is drawn at. ``height`` is the line height."""

    def __init__(self, f, size, height):
        self.font = f
        self.size = size
        self.height = height


_loaded = {}


def _face(choices):
    """The first of ``choices`` that loads. Each choice is a ROM pixel
    font by name (one fixed size), or (path, px) for a vector font file
    drawn at that size. Fonts per badge are in buddy_profile."""
    for choice in choices:
        if isinstance(choice, str):
            f = getattr(font, choice, None)
            if f is not None:
                return Face(f, 0, _height(f))
            continue
        path, size = choice
        try:
            if path not in _loaded:
                _loaded[path] = font.load(path)
            return Face(_loaded[path], size, size)
        except Exception as e:  # noqa: BLE001
            print("claude_buddy: font", path, "not loaded:", e)
    return Face(font.sins, 0, _height(font.sins))


def _color(spec):
    """A ``color`` attribute name ("white") or an (r, g, b) tuple."""
    return getattr(color, spec) if isinstance(spec, str) else color.rgb(*spec)


class Theme:
    """Colours from the badge's profile (buddy_profile). ``fg`` is the
    header, body text, dividers and frame; ``title``, ``footer`` (button
    labels) and ``meta`` (counts, tokens and page number) set the fixed
    parts apart from the body."""

    def __init__(self, spec):
        self.bg = _color(spec["bg"])
        self.fg = _color(spec["fg"])
        self.title = _color(spec["title"])
        self.footer = _color(spec["footer"])
        self.meta = _color(spec["meta"])


class BuddyView:
    """Draws one screen tuple into the framebuffer. It never pushes to
    the panel (that's the painter's job, and the expensive part on
    e-ink). Layout is derived from the screen size and font heights, so
    both badges share it; only the fonts and colours, from the badge's
    profile (buddy_profile), differ."""

    def __init__(self, profile):
        self.theme = Theme(profile.theme)
        bar, title, body = profile.fonts
        self.f_bar = _face(bar)
        self.f_title = _face(title)
        self.f_body = _face(body)
        self.h_bar = self.f_bar.height
        self.h_title = self.f_title.height
        self.h_body = self.f_body.height
        self._size = 0
        self._use(self.f_body)
        self._markup = _markup_active()

        self.w = screen.width
        self.h = screen.height
        bar = self.h_bar + 4
        self.top_rule = bar
        self.bottom_rule = self.h - bar - 1
        self.body_x = PAD
        self.body_w = self.w - 2 * PAD
        self.body_top = self.top_rule + 1 + PAD
        self.body_bottom = self.bottom_rule - PAD
        # Content areas as (x, w, top, bottom): plain, and inset inside
        # the frame of the not-connected screens.
        inset_x = FRAME_MARGIN_X + FRAME_W + FRAME_GAP
        inset_y = FRAME_MARGIN_Y + FRAME_W + FRAME_GAP
        self.plain_area = (self.body_x, self.body_w, self.body_top, self.body_bottom)
        self.framed_area = (
            inset_x,
            self.w - 2 * inset_x,
            self.top_rule + 1 + inset_y,
            self.bottom_rule - inset_y,
        )
        self._layout_key = None
        self._layout_value = None

    # -- text helpers -----------------------------------------------------

    def _use(self, face):
        """Make ``face`` the font for the following measures and draws."""
        screen.font = face.font
        self._size = face.size

    def _esc(self, text):
        return escape(text) if self._markup else text

    def _width(self, text):
        if self._size:
            return int(screen.measure_text(self._esc(text), font_size=self._size)[0])
        return int(screen.measure_text(self._esc(text))[0])

    def _split_long(self, word, width):
        """Hard-break one word wider than ``width`` into pieces."""
        pieces = []
        current = ""
        for ch in word:
            if current and self._width(current + ch) > width:
                pieces.append(current)
                current = ch
            else:
                current += ch
        if current:
            pieces.append(current)
        return pieces

    def wrap(self, text, width, max_lines):
        """Greedy word wrap with the current screen.font. The last line
        gets "..." if text was cut."""
        words = plain(text).split()
        lines = []
        current = ""
        i = 0
        while i < len(words):
            word = words[i]
            candidate = word if not current else current + " " + word
            if self._width(candidate) <= width:
                current = candidate
                i += 1
                continue
            if current:
                lines.append(current)
                current = ""
            else:
                pieces = self._split_long(word, width)
                lines.extend(pieces[:-1])
                current = pieces[-1]
                i += 1
            if len(lines) >= max_lines:
                break
        if current and len(lines) < max_lines:
            lines.append(current)
            current = ""
        truncated = i < len(words) or current != "" or len(lines) > max_lines
        lines = lines[:max_lines]
        if truncated and lines:
            last = lines[-1]
            while last and self._width(last + ELLIPSIS) > width:
                last = last[:-1]
            lines[-1] = last.rstrip() + ELLIPSIS
        return lines

    def _text(self, text, x, y):
        if self._size:
            screen.text(self._esc(text), int(x), int(y), font_size=self._size)
        else:
            screen.text(self._esc(text), int(x), int(y))

    # -- drawing ----------------------------------------------------------

    def draw(self, scr, page=0):
        """Redraw the whole framebuffer for ``scr`` at ``page``: header,
        rules, body, bottom row, footer. Always a full redraw; the panel
        has no partial refresh, so drawing less would save nothing."""
        t = self.theme
        try:
            screen.antialias = image.OFF  # crisp pixel fonts on e-ink
        except Exception:  # noqa: BLE001, S110
            pass
        screen.pen = t.bg
        screen.clear()

        self._draw_header(scr[S_NAME], scr[S_STATUS], scr[S_BATTERY])
        screen.pen = t.fg
        screen.rectangle(0, self.top_rule, self.w, 1)
        screen.rectangle(0, self.bottom_rule, self.w, 1)
        area = self._area(scr)
        if area is self.framed_area:
            self._draw_frame()
        self._draw_body(scr[S_TITLE], scr[S_LINES], scr[S_TOKENS], page, area)
        self._draw_footer(scr[S_ACTIONABLE], scr[S_KIND])

    def _area(self, scr):
        """The content area for ``scr``: framed when not connected."""
        return self.framed_area if scr[S_KIND] == KIND_PAIR else self.plain_area

    def _draw_frame(self):
        """A FRAME_W-thick box inset from the dividers and screen
        edges, as four bars."""
        x = FRAME_MARGIN_X
        y = self.top_rule + 1 + FRAME_MARGIN_Y
        w = self.w - 2 * FRAME_MARGIN_X
        h = self.bottom_rule - FRAME_MARGIN_Y - y
        screen.rectangle(x, y, w, FRAME_W)  # top
        screen.rectangle(x, y + h - FRAME_W, w, FRAME_W)  # bottom
        screen.rectangle(x, y, FRAME_W, h)  # left
        screen.rectangle(x + w - FRAME_W, y, FRAME_W, h)  # right

    def _draw_title_rule(self, y):
        """The rule under a framed title, joining the frame's sides."""
        x = FRAME_MARGIN_X
        screen.rectangle(x, y, self.w - 2 * x, TITLE_RULE_W)

    def _draw_header(self, name, status, battery):
        """Device identifier (left), battery, link status (right).

        The identifier is never dropped: it is what the user matches in
        Claude Desktop's picker. Low battery shows in 5% steps (see
        BuddyModel.battery_label).
        """
        self._use(self.f_bar)
        y = (self.top_rule - self.h_bar) // 2
        name = plain(name)
        status = plain(status)
        battery = plain(battery or "")

        # Priority when space is short: identifier, then status, then
        # battery. Battery is dropped first; status is shortened next.
        name_end = PAD + self._width(name)
        room = self.w - PAD - name_end - HEADER_GAP
        sw = self._width(status)
        bw = self._width(battery) + HEADER_GAP if battery else 0
        if sw + bw > room:
            battery, bw = "", 0
        if sw > room:
            fitted = self.wrap(status, max(room, 0), 1)
            status = fitted[0] if fitted else ""
            sw = self._width(status)

        screen.pen = self.theme.fg
        self._text(name, PAD, y)
        right = self.w - PAD - sw
        self._text(status, right, y)
        if battery:
            self._text(battery, right - bw, y)

    def _draw_footer(self, actionable, kind):
        """Each label sits in the third of the screen above its button.

        A and B are only shown when there is a prompt to answer on the
        badge. When Claude is waiting for an approval the badge can't
        answer (no prompt sent, or a prompt on a stale "No data" link),
        their space says so instead (APP_ONLY_NOTE).
        """
        self._use(self.f_bar)
        screen.pen = self.theme.footer
        third = self.w // 3
        y = self.bottom_rule + 1 + (self.h - self.bottom_rule - 1 - self.h_bar) // 2
        labels = ("A: Accept", "B: Deny", "C: Exit") if actionable else (None, None, "C: Exit")
        exit_x = None
        for i, label in enumerate(labels):
            if label:
                x = i * third + (third - self._width(label)) // 2
                self._text(label, x, y)
                if i == 2:
                    exit_x = x
        if not actionable and kind in (KIND_WAITING, KIND_PROMPT):
            room = exit_x - PAD - HEADER_GAP
            fitted = self.wrap(APP_ONLY_NOTE, room, 1)
            if fitted:
                self._text(fitted[0], PAD, y)

    # -- layout and paging --------------------------------------------------

    def _layout(self, title, lines, area):
        """Wrap the title and body once per content change, then split
        the body rows into pages.

        Returns (title_lines, body_top, pages, counts). Each page is a
        list of text rows, or None for the small gap between items. The
        title repeats on every page so a later page of a prompt still
        says what it is for.

        The counts line ("1 running, 0 waiting") isn't part of the body:
        it goes on the bottom row of every page, with the page marker on
        the right (see _draw_bottom_row). That row is kept free whenever
        there are counts (status screen) or more than one page.
        """
        key = (title, lines, area)
        if key == self._layout_key:
            return self._layout_value

        _, body_w, body_top, body_bottom = area
        self._use(self.f_title)
        title_lines = self.wrap(title, body_w, TITLE_MAX_LINES) if title else []
        top = body_top
        if title_lines:
            top += len(title_lines) * self.h_title
            if area is self.framed_area:
                top += FRAME_GAP + TITLE_RULE_W + FRAME_GAP  # the title rule
            else:
                top += LINE_GAP * 2

        self._use(self.f_body)
        rows = []
        counts = None
        for mode, text in lines:
            if mode == COUNTS:
                counts = text  # "" = tokens only (no-sessions screen)
                continue
            if not text:
                continue
            if rows:
                rows.append(None)
            max_lines = MAX_WRAP_LINES if mode == WRAP else 1
            rows.extend(self.wrap(text, body_w, max_lines))

        bottom = body_bottom - self.h_body
        reserved = counts is not None
        pages = self._paginate(rows, top, bottom if reserved else body_bottom)
        if len(pages) > 1 and not reserved:
            pages = self._paginate(rows, top, bottom)

        self._layout_key = key
        self._layout_value = (title_lines, top, pages, counts)
        return self._layout_value

    def _paginate(self, rows, top, bottom):
        pages = [[]]
        y = top
        for row in rows:
            if row is None:
                if pages[-1]:  # no gap at the top of a page
                    pages[-1].append(None)
                    y += LINE_GAP
                continue
            if y + self.h_body > bottom and pages[-1]:
                pages.append([])
                y = top
            pages[-1].append(row)
            y += self.h_body
        return pages

    def page_count(self, scr):
        """Number of pages for ``scr``. The painter calls this every loop
        (about 50 times a second); it's cheap because _layout caches the
        wrapped text until the title or lines change. Wrapping a 3,000
        character reply from scratch each time would not be."""
        return len(self._layout(scr[S_TITLE], scr[S_LINES], self._area(scr))[2])

    def _draw_body(self, title, lines, tokens, page, area):
        screen.pen = self.theme.fg
        title_lines, top, pages, counts = self._layout(title, lines, area)
        page = max(0, min(page, len(pages) - 1))
        body_x, body_w = area[0], area[1]
        framed = area is self.framed_area

        self._use(self.f_title)
        screen.pen = self.theme.title
        y = area[2]
        for line in title_lines:
            x = body_x
            if framed:
                x += (body_w - self._width(line)) // 2
            self._text(line, x, y)
            y += self.h_title
        screen.pen = self.theme.fg
        if framed and title_lines:
            self._draw_title_rule(y + FRAME_GAP)

        self._use(self.f_body)
        y = top
        for row in pages[page]:
            if row is None:
                y += LINE_GAP
                continue
            self._text(row, body_x, y)
            y += self.h_body

        marker = "{}/{}".format(page + 1, len(pages)) if len(pages) > 1 else ""
        self._draw_bottom_row(counts, tokens, marker, area)

    def _draw_bottom_row(self, counts, tokens, marker, area):
        """Counts (and today's tokens) on the left, page marker on the
        right. The counts give way to the marker: full labels, then
        "run"/"wait", then cut with "...". Empty counts ("") show today's
        tokens alone; None means there's no counts row at all."""
        text = ", ".join(part for part in (counts, tokens if counts is not None else "") if part)
        if not text and not marker:
            return
        screen.pen = self.theme.meta
        body_x, body_w, _, body_bottom = area
        y = body_bottom - self.h_body + 1
        room = body_w
        if marker:
            mw = self._width(marker)
            self._text(marker, body_x + body_w - mw, y)
            room -= mw + HEADER_GAP
        if not text:
            return
        if self._width(text) > room:
            for full, short in _SHORT_LABELS:
                text = text.replace(full, short)
        fitted = self.wrap(text, max(room, 0), 1)
        if fitted:
            self._text(fitted[0], body_x, y)
