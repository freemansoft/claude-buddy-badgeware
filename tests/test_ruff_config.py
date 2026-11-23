"""ruff.toml can extend only one of Pimoroni's two rule files. The app
runs on both badges, so the two must say the same thing: if a firmware
update makes them differ, this fails and someone decides which rules to
follow (see ruff.toml). (Adapted from freemansoft/dice-badgeware.)"""

import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR_RULES = ["vendor/tufty2350/ci/ruff.toml", "vendor/badger2350/ci/ruff.toml"]


def rules(path):
    with open(ROOT / path, "rb") as f:
        return tomllib.load(f)


class RuffConfigTest(unittest.TestCase):
    def test_tufty_and_badger_lint_rules_match(self):
        tufty, badger = (rules(p) for p in VENDOR_RULES)
        self.assertEqual(tufty, badger)

    def test_ruff_toml_extends_pimoronis_rules(self):
        config = rules("ruff.toml")
        self.assertIn(config["extend"], VENDOR_RULES)
        self.assertIn("vendor", config["extend-exclude"])


if __name__ == "__main__":
    unittest.main()
