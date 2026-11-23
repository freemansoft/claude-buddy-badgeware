"""The badgeware-platforms skill: its frontmatter, that every firmware
file it cites as evidence exists in the pinned submodules, and that the
other docs point to it. (Adapted from freemansoft/MoodBadger2350.)"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
        text = SKILL.read_text()
        for path in ("docs/devices.md", "apps/claude_buddy/buddy_profile.py",
                     ".claude/skills/buddy-change/references/power-invariants.md",
                     "tests/test_ruff_config.py", "tests/test_platform_skill.py"):
            self.assertIn(path, text)
            self.assertTrue((ROOT / path).exists(), path)

    def test_submodules_are_registered(self):
        gitmodules = (ROOT / ".gitmodules").read_text()
        for name in ("badger2350", "tufty2350"):
            self.assertIn("vendor/" + name, gitmodules)
            self.assertTrue((ROOT / "vendor" / name / "firmware" / "main.py").exists(), name)

    def test_other_skills_and_claude_md_point_to_it(self):
        for path in (ROOT / "CLAUDE.md", ROOT / ".claude/skills/buddy-change/SKILL.md",
                     ROOT / ".claude/skills/badge-bootstrap/SKILL.md"):
            self.assertIn("badgeware-platforms", path.read_text(), path)


if __name__ == "__main__":
    unittest.main()
