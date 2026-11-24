#!/usr/bin/env python3
"""Import the ASCII buddies from Anthropic's claude-desktop-buddy.

    python3 tools/import_buddies.py            write the app's species module
    python3 tools/import_buddies.py --check    fail if it is out of date
    python3 tools/import_buddies.py --show     print every pose (a contact sheet)
    python3 tools/import_buddies.py --show cat owl

The source is the submodule vendor/claude-desktop-buddy, pinned to the
commit the generated file names (git submodule update --init). Each of
its src/buddies/<name>.cpp files has seven animated states, each a
sequence of 5-line ASCII poses. Claude Buddy doesn't animate, so this
keeps one pose per state, and only five states:

- sleep, idle, busy, attention, celebrate;
- not dizzy (shaking the M5Stick) or heart (petting it, or approving
  within 5 s), which need sensors or are left for later.

The pose kept is the first one the state's sequence shows, unless
PREFERRED below picks another (chosen from --show, because some first poses
don't say what the state is without the motion around them).

The art is Copyright 2026 Anthropic, PBC, under the MIT licence. The
generated module says so in its header, and the licence is copied next
to it in the app folder (LICENSE-claude-desktop-buddy), so every copy on
a badge carries it. Upstream's characters/bufo GIFs are not MIT and are
never read.

Standard library only.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "vendor" / "claude-desktop-buddy"
UPSTREAM_URL = "https://github.com/anthropics/claude-desktop-buddy"
APP_DIR = ROOT / "apps" / "claude_buddy"
OUT = APP_DIR / "buddy_species.py"
LICENSE_OUT = APP_DIR / "LICENSE-claude-desktop-buddy"

# Upstream's state functions, in our order. dizzy and heart are skipped.
STATES = ("sleep", "idle", "busy", "attention", "celebrate")
FUNCTIONS = {"sleep": "doSleep", "idle": "doIdle", "busy": "doBusy", "attention": "doAttention",
             "celebrate": "doCelebrate"}
ROWS = 5

# The pose to keep for a state, where the sequence's first pose doesn't
# read as that state on a still screen; the first name the species has
# wins. Every celebrate sequence starts with a crouch before the jump,
# which looks like nothing much without the motion, so celebrate keeps
# the final pose instead: arms up ("POSE"), or the cactus's "BLOOM".
# Chosen from --show.
PREFERRED = {"celebrate": ("POSE", "BLOOM")}

# Characters the badge fonts may not have, mapped to ASCII.
_ASCII = {"\u00b4": "'"}  # the duck's acute accent

_FUNC = re.compile(r"static void (do\w+)\(uint32_t t\)\s*\{")
_POSE = re.compile(r"static const char\* const (\w+)\[(\d+)\]\s*=\s*\{(.*?)\};", re.S)
_TABLE = re.compile(r"const char\* const\* P\[\d+\]\s*=\s*\{([^}]*)\};")
_SEQ = re.compile(r"static const uint8_t SEQ\[\]\s*=\s*\{([^}]*)\};")
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
_SPECIES = re.compile(r'extern const Species \w+\s*=\s*\{\s*"(\w+)",\s*(0x[0-9A-Fa-f]+)')


def _unescape(text):
    return re.sub(r"\\(.)", r"\1", text)


def _functions(source):
    """{function name: body} for each state function in a species file."""
    starts = list(_FUNC.finditer(source))
    return {
        m.group(1): source[m.end():(starts[i + 1].start() if i + 1 < len(starts) else len(source))]
        for i, m in enumerate(starts)
    }


def parse_species(source):
    """(name, rgb565, {state: {"poses": {name: lines}, "seq": [pose names]}})
    from one upstream species file."""
    m = _SPECIES.search(source)
    if not m:
        raise ValueError("no Species definition")
    name, colour = m.group(1), int(m.group(2), 16)
    functions = _functions(source)
    states = {}
    for state in STATES:
        body = functions.get(FUNCTIONS[state])
        if body is None:
            raise ValueError("{}: no {}()".format(name, FUNCTIONS[state]))
        poses = {}
        for pose, rows, text in _POSE.findall(body):
            lines = [_unescape(s) for s in _STRING.findall(text)]
            if int(rows) != ROWS or len(lines) != ROWS:
                raise ValueError("{} {} {}: {} rows".format(name, state, pose, len(lines)))
            poses[pose] = lines
        table = _TABLE.search(body)
        seq = _SEQ.search(body)
        if not table or not seq:
            raise ValueError("{} {}: no pose table or sequence".format(name, state))
        order = [p.strip() for p in table.group(1).split(",") if p.strip()]
        steps = [int(s) for s in seq.group(1).replace("\n", " ").split(",") if s.strip()]
        states[state] = {"poses": poses, "seq": [order[i] for i in steps]}
    return name, colour, states


def rgb(colour565):
    """An RGB565 colour as (r, g, b), 0-255 each."""
    r, g, b = (colour565 >> 11) & 0x1F, (colour565 >> 5) & 0x3F, colour565 & 0x1F
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)


def to_ascii(line):
    out = "".join(_ASCII.get(ch, ch) for ch in line)
    bad = [ch for ch in out if not " " <= ch <= "~"]
    if bad:
        raise ValueError("no ASCII mapping for {!r} in {!r}".format(bad, line))
    return out.rstrip()


def chosen(states, preferred=PREFERRED):
    """{state: (pose name, 5 ASCII lines)} for one species."""
    out = {}
    for state in STATES:
        names = [p for p in preferred.get(state, ()) if p in states[state]["poses"]]
        pose = names[0] if names else states[state]["seq"][0]
        out[state] = (pose, [to_ascii(line) for line in states[state]["poses"][pose]])
    return out


def load_all(upstream=UPSTREAM):
    folder = upstream / "src" / "buddies"
    files = sorted(folder.glob("*.cpp"))
    if not files:
        sys.exit("No species in {}. Run: git submodule update --init".format(folder))
    return [parse_species(f.read_text(encoding="utf-8")) for f in files]


def upstream_commit(upstream=UPSTREAM):
    result = subprocess.run(["git", "-C", str(upstream), "rev-parse", "--short=7", "HEAD"],
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _quote(text):
    """``text`` as a Python literal in the quotes ruff wants: double,
    unless the text has double quotes and no single ones."""
    q = "'" if '"' in text and "'" not in text else '"'
    body = text.replace("\\", "\\\\").replace("\n", "\\n").replace(q, "\\" + q)
    return q + body + q


def render_module(species, commit):
    """The source of apps/claude_buddy/buddy_species.py."""
    out = [
        '"""ASCII buddies for Claude Buddy, one still pose per state.',
        "",
        "Generated by tools/import_buddies.py from",
        "{} at commit {}".format(UPSTREAM_URL, commit),
        "(src/buddies/*.cpp). Don't edit by hand: change the tool and run it",
        "again.",
        "",
        "The art is Copyright 2026 Anthropic, PBC, and is used under the MIT",
        "licence, which is in LICENSE-claude-desktop-buddy next to this file.",
        "",
        "SPECIES maps a name to ((r, g, b), poses): the body colour upstream",
        "draws it in, and one pose per entry of STATES. A pose is its 5 lines",
        "joined with newlines; trailing spaces are removed, and leading spaces",
        "are part of the art. One string per pose keeps the objects few on",
        "the badge.",
        '"""',
        "",
        "STATES = ({})".format(", ".join(_quote(s) for s in STATES)),
        "",
        "SPECIES = {",
    ]
    for name, colour, states in species:
        out.append("    {}: (".format(_quote(name)))
        out.append("        {},".format(rgb(colour)))
        out.append("        (")
        for state, (pose, lines) in chosen(states).items():
            out.append("            # {}: {}".format(state, pose))
            out.append("            {},".format(_quote("\n".join(lines))))
        out.append("        ),")
        out.append("    ),")
    out.append("}")
    return "\n".join(out) + "\n"


def contact_sheet(species, names=None):
    """Every kept pose, the states side by side, as plain text."""
    out = []
    for name, _colour, states in species:
        if names and name not in names:
            continue
        poses = chosen(states)
        width = max(len(line) for _pose, lines in poses.values() for line in lines) + 2
        out.append(name)
        out.append("".join("{:<{}}".format(state, width) for state in STATES).rstrip())
        out.append("".join("{:<{}}".format(pose, width) for pose, _lines in poses.values()).rstrip())
        for row in range(ROWS):
            out.append("".join("{:<{}}".format(lines[row], width) for _pose, lines in poses.values()).rstrip())
        out.append("")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if the generated files are out of date")
    parser.add_argument("--show", nargs="*", metavar="SPECIES", help="print the kept poses (all species by default)")
    args = parser.parse_args()

    species = load_all()
    if args.show is not None:
        print(contact_sheet(species, args.show))
        return

    module = render_module(species, upstream_commit())
    licence = (UPSTREAM / "LICENSE").read_text(encoding="utf-8")
    if args.check:
        stale = [p.name for p, text in ((OUT, module), (LICENSE_OUT, licence))
                 if not p.is_file() or p.read_text(encoding="utf-8") != text]
        if stale:
            sys.exit("Out of date: {}. Run python3 tools/import_buddies.py".format(", ".join(stale)))
        print("buddy_species.py and the licence match the upstream submodule.")
        return
    OUT.write_text(module, encoding="utf-8")
    LICENSE_OUT.write_text(licence, encoding="utf-8")
    print("Wrote {} species to {} and {}".format(len(species), OUT.relative_to(ROOT), LICENSE_OUT.relative_to(ROOT)))


if __name__ == "__main__":
    main()
