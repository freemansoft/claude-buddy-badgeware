#!/usr/bin/env python3
"""Download Pimoroni's Badgeware firmware and flash it onto a badge.

First find the model with tools/badge_info.py (it reads badge.model).
The bootloader drive can't say which badge it is, so you pass it here.

Pimoroni ships two images per release; choose one every time:

  --firmware-only    replaces only the firmware; apps and files stay.
                     Right for a badge you already use.
  --with-filesystem  ALSO replaces every app and file on the badge with
                     Pimoroni's defaults. Claude Buddy, and possibly its
                     saved settings in /state, are lost. Good for a new
                     badge, so its default apps match the firmware.

Then put the badge in bootloader mode: hold BOOT (back, far left), tap
RESET, let go of BOOT. A drive named RP2350 appears. Run:

    python3 tools/flash_firmware.py --model tufty --firmware-only
    python3 tools/flash_firmware.py --model tufty --with-filesystem
    python3 tools/flash_firmware.py --model badger --firmware-only --tag v3.1.1
    python3 tools/flash_firmware.py --model tufty --firmware-only --download-only

The badge restarts into the menu when the copy finishes. Standard
library only; works on macOS, Windows and Linux.
"""

import argparse
import os
import shutil
import string
import sys
import tempfile
import urllib.request
from pathlib import Path

import badgeware_release as rel

BOOT_LABEL = "RP2350"
CACHE = Path(tempfile.gettempdir()) / "badgeware-firmware"


def _windows_label(drive):
    import ctypes

    buf = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(drive), buf, len(buf), None, None, None, None, 0
    )
    return buf.value if ok else ""


def find_boot_drive():
    """Mounted RP2350 bootloader drives (they hold INFO_UF2.TXT)."""
    candidates = []
    if sys.platform == "darwin":
        candidates = [Path("/Volumes") / BOOT_LABEL]
    elif os.name == "nt":
        for letter in string.ascii_uppercase[3:]:
            drive = "{}:\\".format(letter)
            if os.path.exists(drive) and _windows_label(drive).upper() == BOOT_LABEL:
                candidates.append(Path(drive))
    else:
        user = os.environ.get("USER", "")
        for base in (Path("/media") / user, Path("/run/media") / user, Path("/mnt")):
            candidates.append(base / BOOT_LABEL)
    return [c for c in candidates if (c / "INFO_UF2.TXT").is_file()]


def download(asset):
    """Fetch ``asset`` into the cache (reused if already complete) and
    check it is a whole UF2 file."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / asset["name"]
    size = asset.get("size")
    if not (path.is_file() and path.stat().st_size == size):
        print("Downloading {} ({:.1f} MB) ...".format(asset["name"], (size or 0) / 1e6))
        req = urllib.request.Request(
            asset["browser_download_url"], headers={"User-Agent": rel.USER_AGENT})
        part = path.with_suffix(".part")
        with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
            shutil.copyfileobj(resp, out)
        part.replace(path)
    if size is not None and path.stat().st_size != size:
        sys.exit("Download is {} bytes, expected {}; try again.".format(path.stat().st_size, size))
    with open(path, "rb") as f:
        if not rel.is_uf2(f.read(8)):
            sys.exit("{} isn't a UF2 file; not flashing it.".format(path))
    return path


def confirm_wipe(model, yes):
    print(
        "\n--with-filesystem replaces EVERY app and file on the badge with\n"
        "Pimoroni's defaults. Claude Buddy and possibly its saved settings\n"
        "(/state) will be lost. Use --firmware-only to keep them."
    )
    if yes:
        return
    answer = input("Type the model name ({}) to go ahead: ".format(model)).strip().lower()
    if answer != model:
        sys.exit("Not flashed.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, choices=rel.MODELS,
                        help="badge.model, as tools/badge_info.py reports it")
    flavour = parser.add_mutually_exclusive_group(required=True)
    flavour.add_argument("--firmware-only", action="store_true", help="keep apps and files")
    flavour.add_argument("--with-filesystem", action="store_true",
                         help="also reset all apps and files to Pimoroni's defaults")
    parser.add_argument("--tag", help="release tag, e.g. v3.1.1 (default: latest release)")
    parser.add_argument("--dest", help="the RP2350 drive (default: find it)")
    parser.add_argument("--download-only", action="store_true",
                        help="download and check the file, but don't flash")
    parser.add_argument("--yes", action="store_true", help="skip the --with-filesystem prompt")
    args = parser.parse_args()

    try:
        release = rel.fetch_release(args.model, args.tag)
        asset = rel.pick_asset(release, args.model, args.with_filesystem)
    except (OSError, ValueError, LookupError) as e:  # offline, bad JSON, no such asset
        sys.exit("Couldn't get the release from GitHub: {}".format(e))
    print("{} {} (published {})".format(
        rel.repo_for(args.model), release["tag_name"], release.get("published_at", "")[:10]))
    path = download(asset)
    print("Firmware file: {}".format(path))
    if args.download_only:
        return

    if args.dest:
        dest = Path(args.dest)
        if not (dest / "INFO_UF2.TXT").is_file():
            sys.exit("{} isn't an RP2350 bootloader drive (no INFO_UF2.TXT).".format(dest))
    else:
        drives = find_boot_drive()
        if not drives:
            sys.exit(
                "No RP2350 drive found. Hold BOOT, tap RESET, let go of BOOT,\n"
                "wait for the RP2350 drive, then run this again (or pass --dest)."
            )
        if len(drives) > 1:
            sys.exit("More than one RP2350 drive; pick one with --dest: "
                     + ", ".join(str(d) for d in drives))
        dest = drives[0]

    if args.with_filesystem:
        confirm_wipe(args.model, args.yes)
    print("Flashing {} firmware to {} ...".format(args.model, dest))
    print("(This must be a {}: the bootloader can't tell.)".format(args.model.capitalize()))
    try:
        shutil.copyfile(path, dest / path.name)
    except OSError as e:
        # The drive disappears as soon as the badge takes the image,
        # which some systems report as an error at the very end.
        print("The drive went away during the copy ({}).".format(e))
        print("If the badge restarted into the menu, it worked; otherwise run this again.")
        return
    print("Done. The badge restarts into the menu by itself.")
    print("Check it with: python3 tools/badge_info.py")


if __name__ == "__main__":
    main()
