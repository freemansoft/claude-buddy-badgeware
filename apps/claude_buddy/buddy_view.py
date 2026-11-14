"""Draws the Claude Buddy screen with the Badgeware drawing API.

Layout (Badger 2350, 264x176; everything is derived from screen size
and font heights so the Tufty 2350 can reuse it):

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
BAR_FONT = "nope"
TITLE_FONT = "absolute"
BODY_FONT = "nope"
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
# badge can't answer (163 px in nope; 188 px fit before "C: Exit").
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


def _font(name):
    f = getattr(font, name, None)
    return f if f is not None else font.sins


def _height(f, fallback=12):
    return int(getattr(f, "height", fallback) or fallback)


class Theme:
    def __init__(self, model):
        if model == "badger":
            self.bg = color.white
            self.fg = color.black
        else:  # Tufty (colour LCD): light on dark
            self.bg = color.black
            self.fg = color.white


class BuddyView:
    def __init__(self):
        self.theme = Theme(badge.model)
        self.f_bar = _font(BAR_FONT)
        self.f_title = _font(TITLE_FONT)
        self.f_body = _font(BODY_FONT)
        self.h_bar = _height(self.f_bar)
        self.h_title = _height(self.f_title)
        self.h_body = _height(self.f_body)

        self.w = screen.width
        self.h = screen.height
        bar = self.h_bar + 4
        self.top_rule = bar
        self.bottom_rule = self.h - bar - 1
        self.body_x = PAD
        self.body_w = self.w - 2 * PAD
        self.body_top = self.top_rule + 1 + PAD
        self.body_bottom = self.bottom_rule - PAD
        self._layout_key = None
        self._layout_value = None

    # -- text helpers -----------------------------------------------------

    def _width(self, text):
        return int(screen.measure_text(escape(text))[0])

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
        screen.text(escape(text), int(x), int(y))

    # -- drawing ----------------------------------------------------------

    def draw(self, scr, page=0):
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
        self._draw_body(scr[S_TITLE], scr[S_LINES], scr[S_TOKENS], page)
        self._draw_footer(scr[S_ACTIONABLE], scr[S_KIND])

    def _draw_header(self, name, status, battery):
        """Device identifier (left), battery, link status (right).

        The identifier is never dropped: it is what the user matches in
        Claude Desktop's picker. Low battery shows in 5% steps (see
        BuddyModel.battery_label).
        """
        screen.font = self.f_bar
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
        screen.font = self.f_bar
        screen.pen = self.theme.fg
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

    def _layout(self, title, lines):
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
        key = (title, lines)
        if key == self._layout_key:
            return self._layout_value

        screen.font = self.f_title
        title_lines = self.wrap(title, self.body_w, TITLE_MAX_LINES) if title else []
        top = self.body_top
        if title_lines:
            top += len(title_lines) * self.h_title + LINE_GAP * 2

        screen.font = self.f_body
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
            rows.extend(self.wrap(text, self.body_w, max_lines))

        bottom = self.body_bottom - self.h_body
        reserved = counts is not None
        pages = self._paginate(rows, top, bottom if reserved else self.body_bottom)
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
        return len(self._layout(scr[S_TITLE], scr[S_LINES])[2])

    def _draw_body(self, title, lines, tokens, page):
        screen.pen = self.theme.fg
        title_lines, top, pages, counts = self._layout(title, lines)
        page = max(0, min(page, len(pages) - 1))

        screen.font = self.f_title
        y = self.body_top
        for line in title_lines:
            self._text(line, self.body_x, y)
            y += self.h_title

        screen.font = self.f_body
        y = top
        for row in pages[page]:
            if row is None:
                y += LINE_GAP
                continue
            self._text(row, self.body_x, y)
            y += self.h_body

        marker = "{}/{}".format(page + 1, len(pages)) if len(pages) > 1 else ""
        self._draw_bottom_row(counts, tokens, marker)

    def _draw_bottom_row(self, counts, tokens, marker):
        """Counts (and today's tokens) on the left, page marker on the
        right. The counts give way to the marker: full labels, then
        "run"/"wait", then cut with "...". Empty counts ("") show today's
        tokens alone; None means there's no counts row at all."""
        text = ", ".join(part for part in (counts, tokens if counts is not None else "") if part)
        if not text and not marker:
            return
        y = self.body_bottom - self.h_body + 1
        room = self.body_w
        if marker:
            mw = self._width(marker)
            self._text(marker, self.body_x + self.body_w - mw, y)
            room -= mw + HEADER_GAP
        if not text:
            return
        if self._width(text) > room:
            for full, short in _SHORT_LABELS:
                text = text.replace(full, short)
        fitted = self.wrap(text, max(room, 0), 1)
        if fitted:
            self._text(fitted[0], self.body_x, y)
