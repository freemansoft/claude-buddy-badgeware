"""Host tests for tools/import_buddies.py and the module it generates
(apps/claude_buddy/buddy_species.py): parsing upstream's species files,
the poses kept, the licence copy, and that the generated files match
the pinned submodule."""

import ast
import unittest

import support  # noqa: F401 - puts tools/ and the app on sys.path
from support import ROOT

import buddy_species
import import_buddies as ib
import install

# A cut-down upstream species file: two poses for idle, the rest one.
SOURCE = r"""
namespace toy {
static void doSleep(uint32_t t) {
  static const char* const A[5] = { "  ", " zz ", " (-) ", " /\\ ", "\"\"" };
  const char* const* P[1] = { A };
  static const uint8_t SEQ[] = { 0,0 };
}
static void doIdle(uint32_t t) {
  static const char* const REST[5] = { "", " o ", "(o)", "/ \\", "^" };
  static const char* const LOOK[5] = { "", " o ", "(O)", "/ \\", "^" };
  const char* const* P[2] = { REST, LOOK };
  static const uint8_t SEQ[] = {
    1,0,
    0 };
}
static void doBusy(uint32_t t) {
  static const char* const B[5] = { "", "", "(v)", "", "" };
  const char* const* P[1] = { B };
  static const uint8_t SEQ[] = { 0 };
}
static void doAttention(uint32_t t) {
  static const char* const B[5] = { "", "", "(!)", "", "" };
  const char* const* P[1] = { B };
  static const uint8_t SEQ[] = { 0 };
}
static void doCelebrate(uint32_t t) {
  static const char* const CROUCH[5] = { "", "", "(_)", "", "" };
  static const char* const POSE[5] = { "\\o/", "", "(^)", "", "" };
  const char* const* P[2] = { CROUCH, POSE };
  static const uint8_t SEQ[] = { 0,1 };
}
static void doDizzy(uint32_t t) {}
static void doHeart(uint32_t t) {}
}
extern const Species TOY_SPECIES = {
  "toy",
  0xC2A6,
  { toy::doSleep }
};
"""


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.name, self.colour, self.states = ib.parse_species(SOURCE)

    def test_name_colour_and_states(self):
        self.assertEqual((self.name, self.colour), ("toy", 0xC2A6))
        self.assertEqual(list(self.states), list(ib.STATES))

    def test_c_escapes_are_undone(self):
        self.assertEqual(self.states["sleep"]["poses"]["A"], ["  ", " zz ", " (-) ", " /\\ ", '""'])

    def test_sequence_names_the_poses(self):
        self.assertEqual(self.states["idle"]["seq"], ["LOOK", "REST", "REST"])

    def test_first_pose_of_the_sequence_is_kept(self):
        self.assertEqual(ib.chosen(self.states)["idle"], ("LOOK", ["", " o", "(O)", "/ \\", "^"]))

    def test_celebrate_keeps_the_final_pose(self):
        self.assertEqual(ib.chosen(self.states)["celebrate"][0], "POSE")

    def test_rgb565(self):
        self.assertEqual(ib.rgb(0xF800), (255, 0, 0))
        self.assertEqual(ib.rgb(0x07E0), (0, 255, 0))
        self.assertEqual(ib.rgb(0x001F), (0, 0, 255))

    def test_missing_state_is_an_error(self):
        with self.assertRaises(ValueError):
            ib.parse_species(SOURCE.replace("doBusy", "doNothing"))


class AsciiTest(unittest.TestCase):
    def test_acute_accent_becomes_an_apostrophe(self):
        self.assertEqual(ib.to_ascii("( \u00b4 ) "), "( ' )")

    def test_unknown_character_is_an_error(self):
        with self.assertRaises(ValueError):
            ib.to_ascii("\u2603")

    def test_quotes_round_trip(self):
        for text in ('(")_(")', "it's", "both ' and \"", "back\\slash\nnew line", ""):
            self.assertEqual(ast.literal_eval(ib._quote(text)), text, text)


class GeneratedModuleTest(unittest.TestCase):
    def test_every_species_has_a_pose_per_state(self):
        self.assertEqual(buddy_species.STATES, ("sleep", "idle", "busy", "attention", "celebrate"))
        self.assertEqual(len(buddy_species.SPECIES), 18)
        for name, (colour, poses) in buddy_species.SPECIES.items():
            self.assertEqual(len(colour), 3, name)
            self.assertEqual(len(poses), len(buddy_species.STATES), name)
            for pose in poses:
                lines = pose.split("\n")
                self.assertEqual(len(lines), 5, (name, pose))
                self.assertTrue(all(len(line) <= 16 for line in lines), (name, pose))
                self.assertTrue(all(" " <= ch <= "~" for line in lines for ch in line), (name, pose))

    def test_names_the_source_and_licence(self):
        doc = buddy_species.__doc__
        self.assertIn(ib.UPSTREAM_URL, doc)
        self.assertIn("Copyright 2026 Anthropic, PBC", doc)
        self.assertIn("LICENSE-claude-desktop-buddy", doc)

    def test_licence_ships_with_the_app(self):
        licence = ib.LICENSE_OUT.read_text(encoding="utf-8")
        self.assertIn("Copyright 2026 Anthropic, PBC.", licence)
        self.assertIn("Permission is hereby granted", licence)
        # tools/install.py copies every non-junk file in the app folder.
        self.assertIn(ib.LICENSE_OUT.name, install.app_files(ROOT / "apps" / "claude_buddy"))


@unittest.skipUnless((ib.UPSTREAM / "src" / "buddies").is_dir(), "needs git submodule update --init")
class UpToDateTest(unittest.TestCase):
    def test_generated_files_match_the_submodule(self):
        species = ib.load_all()
        self.assertEqual(ib.render_module(species, ib.upstream_commit()), ib.OUT.read_text(encoding="utf-8"),
                         "run python3 tools/import_buddies.py")
        self.assertEqual((ib.UPSTREAM / "LICENSE").read_text(encoding="utf-8"),
                         ib.LICENSE_OUT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
