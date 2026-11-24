"""The README's own #anchor links resolve to its headings, and its
Setup still has the submodule command the lint and tests need. (The idea
is from freemansoft/MoodBadger2350.)"""

import re
import unittest

from support import ROOT

README = (ROOT / "README.md").read_text()


def slug(heading):
    """GitHub's heading anchor: lower case, punctuation dropped, spaces
    to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def headings(text):
    # Skip fenced code blocks, whose "#" lines aren't headings.
    text = re.sub(r"^```.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
    return re.findall(r"^#+ (.+)$", text, re.MULTILINE)


class ReadmeTest(unittest.TestCase):
    def test_internal_links_resolve(self):
        anchors = {slug(h) for h in headings(README)}
        links = set(re.findall(r"\]\(#([\w-]+)\)", README))
        self.assertTrue(links)
        self.assertEqual(links - anchors, set())

    def test_setup_initialises_the_submodules(self):
        # Without vendor/, ruff.toml's extend and the vendor tests fail.
        self.assertIn("git submodule update --init", README)


if __name__ == "__main__":
    unittest.main()
