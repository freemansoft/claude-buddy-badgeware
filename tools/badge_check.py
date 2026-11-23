#!/usr/bin/env python3
"""Check the installed copy of Claude Buddy from the badge's side.

    python3 tools/badge_check.py files
    python3 tools/badge_check.py files --port /dev/cu.usbmodem201401

files: lists /system/apps/claude_buddy on the badge itself and compares
it with apps/claude_buddy here (names and sizes), so it shows what the
badge really holds. Run it after the eject, with the badge back in
normal mode (menu or an app on screen): until the eject, the computer
may still be holding writes, so the mounted drive can look right when
the badge isn't. A file cut short (as when app files were once cut to
4096 bytes by a RESET before the eject) shows as "different size".

mpremote stops the running app to read the files, so this ends with
machine.reset(), like tools/badge_info.py.

Needs mpremote (pip install mpremote). Standard library otherwise.
(Adapted from freemansoft/MoodBadger2350.)
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

import badge_info
from install import APP, SRC, app_files

TAG = "BADGE_CHECK "

# Runs on the badge: every file under the app folder, with its size.
FILES_SNIPPET = r"""
import json, os
root = "/system/apps/APP"
files = {}
def walk(path):
    for name in os.listdir(path):
        full = path + "/" + name
        st = os.stat(full)
        if st[0] & 0x4000:
            walk(full)
        else:
            files[full[len(root) + 1:]] = st[6]
try:
    walk(root)
    print("TAG" + json.dumps({"files": files}))
except OSError:
    print("TAG" + json.dumps({"files": None}))
""".replace("APP", APP).replace("TAG", TAG)


def mpremote_command(port, snippet):
    """Run ``snippet`` on the badge, then restart it (machine.reset()) so
    it isn't left frozen at the REPL."""
    return ["mpremote", "connect", port, "exec", snippet, "reset"]


def parse_tagged(output):
    for line in output.splitlines():
        if line.startswith(TAG):
            return json.loads(line[len(TAG):])
    raise ValueError("no {}line in:\n{}".format(TAG, output))


def local_files(folder):
    """{relative path: size} of the files tools/install.py copies from ``folder``."""
    return {name: (Path(folder) / name).stat().st_size for name in app_files(folder)}


def compare_files(local, badge):
    """Problems found comparing {path: size} here with the badge's; {} if none."""
    junk = sorted(n for n in badge if n.split("/")[-1].startswith("._") or "__pycache__" in n)
    problems = {
        "missing": sorted(n for n in local if n not in badge),
        "different size": sorted(n for n in local if n in badge and badge[n] != local[n]),
        "not in the app": sorted(n for n in badge if n not in local and n not in junk),
        "macOS junk": junk,
    }
    return {k: v for k, v in problems.items() if v}


def read(port, snippet):
    result = badge_info.run(mpremote_command(port, snippet))
    if result.returncode != 0:
        sys.exit("mpremote failed:\n" + (result.stderr or result.stdout))
    return parse_tagged(result.stdout)


def check_files(port, src=SRC):
    badge = read(port, FILES_SNIPPET)["files"]
    if badge is None:
        sys.exit("Claude Buddy isn't installed on the badge (no /system/apps/{}).".format(APP))
    local = local_files(src)
    problems = compare_files(local, badge)
    print("{} files on the badge, {} in apps/{}".format(len(badge), len(local), APP))
    if not problems:
        print("The badge's copy matches.")
        return
    for kind, names in problems.items():
        print("{}: {}".format(kind, ", ".join(names)))
    print("Reinstall with tools/install.py and let it eject the drive.")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("check", choices=("files",))
    parser.add_argument("--port", help="the badge's serial port (default: find it)")
    args = parser.parse_args()

    if not shutil.which("mpremote"):
        sys.exit("mpremote not found. Install it with: pip install mpremote")
    check_files(badge_info.choose_port(args.port))


if __name__ == "__main__":
    main()
