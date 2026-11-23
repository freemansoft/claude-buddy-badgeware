"""Host tests for tools/badge_check.py: the pure logic behind checking
the installed copy from the badge's side. No badge needed.
(Adapted from freemansoft/MoodBadger2350.)"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import badge_check  # noqa: E402


class SnippetTest(unittest.TestCase):
    def test_device_snippet_is_valid_python(self):
        compile(badge_check.FILES_SNIPPET, "<badge>", "exec")

    def test_device_snippet_reads_this_apps_folder(self):
        self.assertIn('"/system/apps/claude_buddy"', badge_check.FILES_SNIPPET)

    def test_mpremote_command_ends_with_a_reset(self):
        cmd = badge_check.mpremote_command("/dev/x", badge_check.FILES_SNIPPET)
        self.assertEqual(cmd[:4], ["mpremote", "connect", "/dev/x", "exec"])
        self.assertEqual(cmd[-1], "reset")


class LocalFilesTest(unittest.TestCase):
    def test_local_files_are_what_install_copies_with_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            (root / "__init__.py").write_text("app")
            (root / "assets" / "a.png").write_bytes(b"12345")
            (root / "._junk").write_bytes(b"x")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "x.pyc").write_bytes(b"c")
            self.assertEqual(badge_check.local_files(root), {"__init__.py": 3, "assets/a.png": 5})

    def test_real_app_folder_has_the_entry_point(self):
        self.assertIn("__init__.py", badge_check.local_files(badge_check.SRC))


class CompareFilesTest(unittest.TestCase):
    def test_matching(self):
        files = {"__init__.py": 3, "buddy_model.py": 5}
        self.assertEqual(badge_check.compare_files(files, dict(files)), {})

    def test_reports_missing_extra_size_and_junk(self):
        local = {"__init__.py": 5000, "buddy_view.py": 5, "buddy_model.py": 9}
        # __init__.py cut to one FAT cluster, as once seen on a Badger.
        badge = {"__init__.py": 4096, "buddy_view.py": 5, "old.py": 1, "._buddy_model.py": 4096}
        self.assertEqual(badge_check.compare_files(local, badge), {
            "missing": ["buddy_model.py"],
            "different size": ["__init__.py"],
            "not in the app": ["old.py"],
            "macOS junk": ["._buddy_model.py"],
        })

    def test_pycache_on_the_badge_is_junk(self):
        problems = badge_check.compare_files({}, {"__pycache__/x.mpy": 3})
        self.assertEqual(problems, {"macOS junk": ["__pycache__/x.mpy"]})


class ParseTaggedTest(unittest.TestCase):
    def test_finds_the_tagged_line(self):
        out = 'noise\nBADGE_CHECK {"files": {"a.py": 1}}\n'
        self.assertEqual(badge_check.parse_tagged(out), {"files": {"a.py": 1}})

    def test_missing_line_is_an_error(self):
        with self.assertRaises(ValueError):
            badge_check.parse_tagged("no tag here")


if __name__ == "__main__":
    unittest.main()
