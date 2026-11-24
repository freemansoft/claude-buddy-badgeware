"""Host tests for tools/install.py: which files go to the badge, the
staged copy and swap, removing macOS "._" files, and ejecting the drive.
No badge needed."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # noqa: F401 - puts tools/ on sys.path

import install


class FakeRun:
    """Stands in for subprocess.run: records each command and answers
    from ``results`` ({command name, or "udisksctl <verb>": (returncode,
    stdout)}); a missing key raises FileNotFoundError (an OSError), as
    for a command that isn't installed."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        key = " ".join(cmd[:2]) if cmd[0] == "udisksctl" else cmd[0]
        if key not in self.results:
            raise FileNotFoundError(cmd[0])
        code, out = self.results[key]
        return type("Result", (), {"returncode": code, "stdout": out, "stderr": ""})()


class EjectTest(unittest.TestCase):
    def test_macos_uses_diskutil(self):
        run = FakeRun({"diskutil": (0, "")})
        self.assertTrue(install.eject(Path("/Volumes/BADGER"), run, "darwin"))
        self.assertEqual(run.calls, [["diskutil", "eject", "/Volumes/BADGER"]])

    def test_macos_failure_reported(self):
        run = FakeRun({"diskutil": (1, "")})
        self.assertFalse(install.eject(Path("/Volumes/BADGER"), run, "darwin"))

    def test_linux_unmounts_then_powers_off_the_mounted_device(self):
        run = FakeRun({
            "findmnt": (0, "/dev/sdb1\n"),
            "udisksctl unmount": (0, ""),
            "udisksctl power-off": (0, ""),
        })
        self.assertTrue(install.eject(Path("/media/me/BADGER"), run, "linux"))
        self.assertEqual(run.calls, [
            ["findmnt", "-no", "SOURCE", "/media/me/BADGER"],
            ["udisksctl", "unmount", "-b", "/dev/sdb1"],
            ["udisksctl", "power-off", "-b", "/dev/sdb1"],
        ])

    def test_linux_without_udisksctl(self):
        run = FakeRun({"findmnt": (0, "/dev/sdb1\n")})
        self.assertFalse(install.eject(Path("/media/me/BADGER"), run, "linux"))

    def test_linux_stops_if_unmount_fails(self):
        run = FakeRun({"findmnt": (0, "/dev/sdb1\n"), "udisksctl unmount": (1, ""), "udisksctl power-off": (0, "")})
        self.assertFalse(install.eject(Path("/media/me/BADGER"), run, "linux"))
        self.assertNotIn("power-off", [c[1] for c in run.calls if c[0] == "udisksctl"])

    def test_other_platforms_dont_eject(self):
        run = FakeRun({})
        self.assertFalse(install.eject(Path("E:\\"), run, "win32"))
        self.assertEqual(run.calls, [])


class AppleDoubleTest(unittest.TestCase):
    def test_removes_only_dot_underscore_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "assets").mkdir()
            for name in ("main.py", "._main.py", "icon.png", "._icon.png", "assets/a.png", "assets/._a.png"):
                (root / name).write_text("x")
            self.assertEqual(install.remove_apple_double(root), 3)
            left = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
            self.assertEqual(left, ["assets/a.png", "icon.png", "main.py"])

    def test_nothing_to_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "main.py").write_text("x")
            self.assertEqual(install.remove_apple_double(tmp), 0)

    def test_removes_the_folders_own_partner(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "app"
            app.mkdir()
            (Path(tmp) / "._app").write_text("x")
            self.assertEqual(install.remove_apple_double(app), 1)
            self.assertFalse((Path(tmp) / "._app").exists())


def _write(folder, files):
    for name, text in files.items():
        path = Path(folder) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _tree(folder):
    """{relative path: text} for every file under ``folder``."""
    folder = Path(folder)
    return {str(p.relative_to(folder)): p.read_text() for p in sorted(folder.rglob("*")) if p.is_file()}


class InstallAppTest(unittest.TestCase):
    APP = {"__init__.py": "new", "buddy_model.py": "model", "assets/icon.png": "png"}
    JUNK = {"__pycache__/x.pyc": "c", "buddy_view.pyc": "c", ".DS_Store": "d", "._buddy_model.py": "a"}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.src = Path(tmp.name) / "src"
        self.root = Path(tmp.name) / "BADGER"
        _write(self.src, {**self.APP, **self.JUNK})
        _write(self.root, {"main.py": "menu", "apps/other/__init__.py": "other"})
        self.target = self.root / "apps" / install.APP

    def test_app_files_skip_junk(self):
        self.assertEqual(install.app_files(self.src), ["__init__.py", "assets/icon.png", "buddy_model.py"])

    def test_fresh_install(self):
        self.assertEqual(install.install_app(self.src, self.root), self.target)
        self.assertEqual(_tree(self.target), self.APP)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["apps", "main.py"])

    def test_replaces_the_old_app_and_keeps_other_apps(self):
        _write(self.target, {"__init__.py": "old", "removed.py": "gone"})
        install.install_app(self.src, self.root)
        self.assertEqual(_tree(self.target), self.APP)
        self.assertEqual(_tree(self.root / "apps" / "other"), {"__init__.py": "other"})

    def test_removes_leftovers_of_an_interrupted_run(self):
        _write(self.root / ".claude_buddy.new", {"__init__.py": "half"})
        _write(self.root / ".claude_buddy.old", {"__init__.py": "older"})
        install.install_app(self.src, self.root)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["apps", "main.py"])

    def test_failed_check_leaves_the_old_app(self):
        _write(self.target, {"__init__.py": "old"})
        with mock.patch.object(install, "verify_copy", return_value=["__init__.py"]):
            with self.assertRaises(OSError):
                install.install_app(self.src, self.root)
        self.assertEqual(_tree(self.target), {"__init__.py": "old"})

    def test_failed_swap_puts_the_old_app_back(self):
        _write(self.target, {"__init__.py": "old"})
        real_rename = Path.rename

        def rename(path, dest):
            if path.name == ".claude_buddy.new":
                raise OSError("rename failed")
            return real_rename(path, dest)

        with mock.patch.object(install.Path, "rename", autospec=True, side_effect=rename):
            with self.assertRaises(OSError):
                install.install_app(self.src, self.root)
        self.assertEqual(_tree(self.target), {"__init__.py": "old"})


class VerifyCopyTest(unittest.TestCase):
    def test_reports_missing_and_different_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, copy = Path(tmp) / "src", Path(tmp) / "copy"
            _write(src, {"a.py": "x" * 5000, "b.py": "b", "c.py": "c", "._a.py": "junk"})
            _write(copy, {"a.py": "x" * 4096, "b.py": "b"})  # a.py cut to one FAT cluster; c.py missing
            self.assertEqual(install.verify_copy(src, copy), ["a.py", "c.py"])

    def test_identical_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, copy = Path(tmp) / "src", Path(tmp) / "copy"
            _write(src, {"a.py": "a", "sub/b.py": "b"})
            _write(copy, {"a.py": "a", "sub/b.py": "b"})
            self.assertEqual(install.verify_copy(src, copy), [])


if __name__ == "__main__":
    unittest.main()
