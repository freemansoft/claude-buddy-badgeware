"""The prettier version lives in one place, .prettier-version. The hook,
CI, README and skills read it or point at it; this fails if any tracked
file writes the version out again."""

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINNED = re.compile(r"prettier@\d")


def tracked_files():
    """Tracked files, and new ones not yet added (but not ignored ones)."""
    cmd = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / name for name in out.split("\0") if name]


class PrettierVersionTest(unittest.TestCase):
    def test_version_file_holds_just_a_version(self):
        self.assertRegex((ROOT / ".prettier-version").read_text(), r"^\d+\.\d+\.\d+\n?$")

    def test_no_other_tracked_file_pins_prettier(self):
        pinned = []
        for path in tracked_files():
            if path.name == ".prettier-version" or not path.is_file():
                continue  # submodules are directories
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue  # images
            if PINNED.search(text):
                pinned.append(str(path.relative_to(ROOT)))
        self.assertEqual(pinned, [])

    def test_hook_and_ci_read_the_version_file(self):
        for name in (".githooks/pre-commit", ".github/workflows/ci.yml"):
            self.assertIn(".prettier-version", (ROOT / name).read_text(), name)


if __name__ == "__main__":
    unittest.main()
