"""The prettier version lives in one place, .prettier-version. The hook
and CI read it, and the README and skills point at it; these fail if the
file isn't a bare version, if any tracked file writes the version out
again, or if the hook or CI stop reading it."""

import re
import subprocess
import unittest

from support import ROOT

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
        # In a command, not just a comment: both files also mention the
        # file in comments.
        reads = re.compile(r'prettier@\$\(cat "?[^)"]*\.prettier-version')
        for name in (".githooks/pre-commit", ".github/workflows/ci.yml"):
            code = [line for line in (ROOT / name).read_text().splitlines()
                    if not line.lstrip().startswith("#")]
            self.assertTrue(any(reads.search(line) for line in code), name)


if __name__ == "__main__":
    unittest.main()
