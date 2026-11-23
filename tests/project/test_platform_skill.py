"""The badgeware-platforms skill: its frontmatter, and that every file it
cites, as firmware evidence in the pinned submodules or as a repository
path, still exists. (Adapted from freemansoft/MoodBadger2350.)"""

import re
import unittest

from support import ROOT

SKILL = ROOT / ".claude" / "skills" / "badgeware-platforms" / "SKILL.md"


class PlatformSkillTest(unittest.TestCase):
    def test_skill_has_frontmatter_name_and_description(self):
        self.assertTrue(SKILL.read_text().startswith("---\nname: badgeware-platforms\ndescription: "))

    def test_every_vendor_path_cited_in_the_skill_exists(self):
        cited = set(re.findall(r"vendor/(?:badger2350|tufty2350)/[\w./-]+", SKILL.read_text()))
        self.assertTrue(cited, "the skill must cite firmware source")
        missing = [p for p in sorted(cited) if not (ROOT / p.rstrip(".")).exists()]
        self.assertEqual(missing, [], "run `git submodule update --init` if vendor/ is empty")

    def test_repo_paths_cited_in_the_skill_exist(self):
        # Paths in this repository (not ones inside vendor/, such as
        # vendor/.../firmware/apps/menu).
        pattern = r"(?<![\w/.-])(?:apps|docs|tools|tests|\.claude)/[\w./-]+"
        cited = set(re.findall(pattern, SKILL.read_text()))
        self.assertTrue(cited)
        missing = [p for p in sorted(cited) if not (ROOT / p.rstrip(".")).exists()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
