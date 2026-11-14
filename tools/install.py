#!/usr/bin/env python3
"""Copy the Claude Buddy app onto a Badgeware badge in USB disk mode.

1. Double-tap RESET on the back of the badge. It mounts as a USB drive
   (BADGER, or TUFTY for a Tufty 2350).
2. Run:  python3 tools/install.py            (finds the drive)
     or  python3 tools/install.py --dest /Volumes/BADGER
     or  python tools\\install.py --dest E:\\
3. Eject the drive; the badge reboots into the menu.

Standard library only; works on macOS, Windows and Linux.
"""

import argparse
import os
import shutil
import string
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


def find_badge():
    candidates = []
    if sys.platform == "darwin":
        candidates = [Path("/Volumes") / label for label in LABELS]
    elif os.name == "nt":
        for letter in string.ascii_uppercase[3:]:
            drive = "{}:\\".format(letter)
            if os.path.exists(drive) and _windows_label(drive).upper() in LABELS:
                candidates.append(Path(drive))
    else:
        user = os.environ.get("USER", "")
        for base in (Path("/media") / user, Path("/run/media") / user, Path("/mnt")):
            candidates += [base / label for label in LABELS]
    return [c for c in candidates if c.is_dir() and _looks_like_badge(c)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", help="root of the badge's USB drive (contains apps/ and main.py)")
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

    target = root / "apps" / APP
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(SRC, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    print("Installed to", target)
    print("Eject the drive; the badge restarts into the menu.")


if __name__ == "__main__":
    main()
