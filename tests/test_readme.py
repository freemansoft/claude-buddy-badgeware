"""The README keeps its key references, and its own #anchor links
resolve to headings. (The idea is from freemansoft/MoodBadger2350.)"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()

REQUIRED = [
    "https://youtu.be/UT2T0cCHS3o",
    "https://github.com/anthropics/claude-desktop-buddy",
    "https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md",
    "https://badgewa.re",
    "https://badgewa.re/docs",
    "https://github.com/pimoroni/badgeware-docs",
    "https://github.com/pimoroni/badger2350",
    "https://github.com/pimoroni/tufty2350",
    "https://github.com/pimoroni/picovector-micropython",
    "https://github.com/pimoroni/micropython/tree/bw-1.29.0-gc",
    "https://docs.micropython.org/en/latest/library/bluetooth.html",
    "https://github.com/freemansoft/build-with-claude",
    "https://github.com/amargandhi/claude-buddy-pico",
]


def slug(heading):
    """GitHub's heading anchor: lower case, punctuation dropped, spaces
    to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def headings(text):
    # Skip fenced code blocks, whose "#" lines aren't headings.
    text = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    return re.findall(r"^#+ (.+)$", text, re.MULTILINE)


class ReadmeTest(unittest.TestCase):
    def test_contains_key_references(self):
        for required in REQUIRED:
            with self.subTest(required):
                self.assertIn(required, README)

    def test_internal_links_resolve(self):
        anchors = {slug(h) for h in headings(README)}
        links = set(re.findall(r"\]\(#([\w-]+)\)", README))
        self.assertTrue(links)
        self.assertEqual(links - anchors, set())

    def test_slug_matches_githubs_rules(self):
        self.assertEqual(slug("Phase 2 design: Tufty display switch"), "phase-2-design-tufty-display-switch")
        self.assertEqual(slug("macOS vs Windows"), "macos-vs-windows")

    def test_install_covers_both_badges(self):
        install = README[README.index("## Install"):README.index("## Connect to Claude Desktop")]
        for needed in ("Badger 2350", "Tufty 2350", "BADGER", "TUFTY", "badge_info.py", "badge_check.py"):
            self.assertIn(needed, install)

    def test_setup_initialises_the_submodules(self):
        self.assertIn("git submodule update --init", README)


if __name__ == "__main__":
    unittest.main()
