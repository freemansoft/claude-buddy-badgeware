#!/usr/bin/env python3
"""Copy the Claude Buddy app onto a Badgeware badge in USB disk mode.

0. With the badge on USB in normal mode, check its firmware first:
   python3 tools/badge_info.py. If it says OLDER, update the firmware
   (README "Check and update the firmware") before installing.
1. Double-tap RESET on the back of the badge. It mounts as a USB drive
   (BADGER, or TUFTY for a Tufty 2350).
2. Run:  python3 tools/install.py            (finds the drive)
     or  python3 tools/install.py --dest /Volumes/BADGER
     or  python tools\\install.py --dest E:\\
3. On macOS and Linux the script ejects the drive itself and the badge
   restarts into the menu. On Windows, eject it from the taskbar.
4. Check the copy from the badge's side: python3 tools/badge_check.py files

Never press RESET or unplug the badge before the drive is ejected: the
computer writes to the drive lazily, and files cut short on the badge
show up later as a SyntaxError when the app starts.

Rules this script keeps, so a failed install can't break the badge:

- Never delete the installed app before the new copy is complete and
  checked. The copy is built in .claude_buddy.new at the drive's root,
  outside apps/ so the menu never lists it, compared file by file with
  the repo, and only then swapped in with renames.
- Always eject the drive afterwards, or tell the user to.

Standard library only; works on macOS, Windows and Linux.
"""

import argparse
import filecmp
import os
import shutil
import string
import subprocess
import sys
from pathlib import Path

APP = "claude_buddy"
LABELS = ("BADGER", "TUFTY", "BADGER2350", "TUFTY2350")
SRC = Path(__file__).resolve().parent.parent / "apps" / APP


def _looks_like_badge(root):
    return (root / "apps").is_dir() and (root / "main.py").is_file()


def _windows_label(drive):
    import ctypes

    buf = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(drive), buf, len(buf), None, None, None, None, 0
    )
    return buf.value if ok else ""


def _ignore_missing(_func, _path, exc):
    """rmtree error handler. On macOS the badge's FAT drive holds "._"
    companion files that vanish along with their main file, so
    deleting one that's already gone isn't an error."""
    if not isinstance(exc, FileNotFoundError):
        raise exc


def _remove_tree(path):
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_ignore_missing)
    else:  # onerror is deprecated from 3.12
        shutil.rmtree(path, onerror=lambda f, p, info: _ignore_missing(f, p, info[1]))


def _is_junk(name):
    """Files and folders never copied to the badge."""
    return name in ("__pycache__", ".DS_Store") or name.endswith(".pyc") or name.startswith("._")


def _ignore_junk(_folder, names):
    return {name for name in names if _is_junk(name)}


def app_files(folder):
    """Relative paths of the files in ``folder`` that go to the badge."""
    folder = Path(folder)
    return [
        str(path.relative_to(folder))
        for path in sorted(folder.rglob("*"))
        if path.is_file() and not any(_is_junk(part) for part in path.relative_to(folder).parts)
    ]


def verify_copy(src, copy):
    """Relative paths of app files missing from ``copy`` or different
    from ``src``. This reads the copy back through the computer's
    cache, so it catches a bad copy but not writes lost by resetting
    the badge before the drive is ejected; only the eject prevents
    that."""
    return [
        name
        for name in app_files(src)
        if not (Path(copy) / name).is_file() or not filecmp.cmp(Path(src) / name, Path(copy) / name, shallow=False)
    ]


def remove_apple_double(target):
    """Delete the "._" files macOS writes next to each copied file.

    The badge's drive is FAT, which can't hold extended attributes, so
    macOS stores them (com.apple.provenance at least, which it stamps on
    every new file, so copying without metadata doesn't avoid it) in a
    "._<name>" companion file. That includes one beside ``target``
    itself, in its parent folder. The badge never uses them. Returns how
    many were removed; on other OSes there are none.
    """
    target = Path(target)
    partner = target.parent / ("._" + target.name)
    paths = ([partner] if partner.is_file() else []) + sorted(target.rglob("._*"))
    removed = 0
    for path in paths:
        if path.is_file():
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            removed += 1
    return removed


def install_app(src, root):
    """Replace apps/<APP> on the drive at ``root`` with ``src``; return
    the installed folder.

    The new copy is built and checked in .<APP>.new at the drive's root,
    then swapped in with two renames. If the copy or the check fails
    (drive full, cable pulled, badge reset), OSError is raised and the
    installed app is untouched. Leftover .new and .old folders from an
    interrupted run are removed first.
    """
    root = Path(root)
    target = root / "apps" / APP
    staging = root / ".{}.new".format(APP)
    old = root / ".{}.old".format(APP)
    for leftover in (staging, old):
        if leftover.exists():
            _remove_tree(leftover)

    shutil.copytree(src, staging, ignore=_ignore_junk, copy_function=shutil.copyfile)
    remove_apple_double(staging)
    bad = verify_copy(src, staging)
    if bad:
        raise OSError("copy check failed for {}".format(", ".join(bad)))

    if target.exists():
        target.rename(old)
    try:
        staging.rename(target)
    except OSError:
        if old.exists():
            old.rename(target)  # put the installed app back
        raise
    remove_apple_double(target)
    if old.exists():
        try:
            _remove_tree(old)
        except OSError as e:  # the new app is in place; this is only tidying
            print("Couldn't remove {} ({}); the next install removes it.".format(old, e), file=sys.stderr)
    return target


def _run(cmd, run):
    """Run ``cmd``; return its stdout, or None (printing why) on failure."""
    try:
        result = run(cmd, capture_output=True, text=True)
    except OSError as e:  # the command isn't installed
        print("{}: {}".format(cmd[0], e), file=sys.stderr)
        return None
    if result.returncode != 0:
        print((result.stderr or result.stdout).strip(), file=sys.stderr)
        return None
    return result.stdout


def eject(root, run=subprocess.run, platform=sys.platform):
    """Eject the badge drive so every write reaches it before it restarts.

    Copying returns once the data is in the computer's cache, not on the
    badge. A RESET or unplug in that gap leaves truncated files (seen on
    a Badger: several files cut to 4096 bytes, one FAT cluster), which
    the app reports as a SyntaxError. Ejecting flushes everything first.
    A badge put in drive mode by a double-tap of RESET then restarts into
    the menu by itself; one put there over mpremote (import _msc) needs a
    press of RESET, which is safe once ejected.

    Returns True if the drive was ejected, False if the user must eject
    it (a command failed, or an OS this doesn't handle). Windows isn't
    handled; main() tells the user to eject from the taskbar instead.
    """
    if platform == "darwin":
        return _run(["diskutil", "eject", str(root)], run) is not None
    if platform.startswith("linux"):
        # Find the block device while it's still mounted, unmount it,
        # then power it off: power-off is the eject the badge sees.
        # udisksctl works without root for a desktop automount.
        device = _run(["findmnt", "-no", "SOURCE", str(root)], run)
        if not device or not device.strip():
            return False
        device = device.strip()
        return (
            _run(["udisksctl", "unmount", "-b", device], run) is not None
            and _run(["udisksctl", "power-off", "-b", device], run) is not None
        )
    return False


def find_badge():
    candidates = []
    if os.name == "nt":
        for letter in string.ascii_uppercase[3:]:
            drive = "{}:\\".format(letter)
            if os.path.exists(drive) and _windows_label(drive).upper() in LABELS:
                candidates.append(Path(drive))
    else:
        # Labels vary in case and form (TUFTY, Tufty2350), and
        # Linux paths are case-sensitive, so compare names upper-cased.
        if sys.platform == "darwin":
            bases = [Path("/Volumes")]
        else:
            user = os.environ.get("USER", "")
            bases = [Path("/media") / user, Path("/run/media") / user, Path("/mnt")]
        for base in bases:
            if base.is_dir():
                candidates += [c for c in base.iterdir() if c.name.upper() in LABELS]
    return [c for c in candidates if c.is_dir() and _looks_like_badge(c)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", help="root of the badge's USB drive (contains apps/ and main.py)")
    parser.add_argument("--no-eject", action="store_true", help="leave the drive mounted (eject it yourself)")
    args = parser.parse_args()

    if args.dest:
        root = Path(args.dest)
        if not _looks_like_badge(root):
            sys.exit("{} doesn't look like a Badgeware drive (no apps/ or main.py)".format(root))
    else:
        found = find_badge()
        if not found:
            sys.exit("No badge drive found. Double-tap RESET on the badge, or pass --dest.")
        if len(found) > 1:
            sys.exit("Several badge drives found ({}); pass --dest.".format(", ".join(map(str, found))))
        root = found[0]

    print("Reminder: check the badge's firmware before installing (tools/badge_info.py,")
    print("in normal mode). If you didn't, run it after the eject and update the")
    print("firmware if it says OLDER.")
    print("Copying to {} ...".format(root), flush=True)
    try:
        target = install_app(SRC, root)
    except OSError as e:
        sys.exit(
            "The copy failed ({}).\nThe app on the badge wasn't changed. Check the drive is "
            "still mounted and has free space, then run this again.".format(e)
        )
    print("Installed {} files to {}".format(len(app_files(SRC)), target))
    if args.no_eject or os.name == "nt":
        print("Eject the drive before pressing RESET or unplugging, or the copied")
        print("files may be cut short. The badge then restarts into the menu.")
    elif eject(root):
        print("Ejected {}. The badge restarts into the menu; if it doesn't,".format(root))
        print("press RESET (safe now). Then check the copy from the badge's side:")
        print("  python3 tools/badge_check.py files")
    else:
        print("Couldn't eject {}. Eject it yourself before pressing RESET or".format(root))
        print("unplugging, or the copied files may be cut short.")
        sys.exit(1)


if __name__ == "__main__":
    main()
