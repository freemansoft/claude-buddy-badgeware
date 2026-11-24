#!/usr/bin/env python3
"""Show every buddy's still poses on a badge, to judge them by eye.

    python3 tools/buddy_gallery.py
    python3 tools/buddy_gallery.py --port /dev/cu.usbmodem201401

Install Claude Buddy first (tools/install.py), so the badge has
buddy_species.py and buddy_sprite.py, and have the badge in normal mode
(menu or an app on screen). This runs tools/buddy_gallery_device.py on
the badge over mpremote:

    DOWN / UP   next / previous page (one species per page)
    B / A       next / previous font
    C           stop

The badge then restarts (machine.reset()). Like tools/badge_info.py it
stops whatever was running, including a Claude Desktop connection.

Needs mpremote (pip install mpremote). Standard library otherwise.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import badge_info

DEVICE_SCRIPT = Path(__file__).resolve().parent / "buddy_gallery_device.py"


def mpremote_command(port):
    """Run the gallery on the badge, then restart it, so it isn't left
    frozen at the REPL."""
    return ["mpremote", "connect", port, "run", str(DEVICE_SCRIPT), "reset"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="the badge's serial port (default: find it)")
    args = parser.parse_args()

    if not shutil.which("mpremote"):
        sys.exit("mpremote not found. Install it with: pip install mpremote")
    port = badge_info.choose_port(args.port)
    print("Gallery running on the badge: DOWN/UP pages, B/A fonts, C stops.", flush=True)
    sys.exit(subprocess.run(mpremote_command(port), check=False).returncode)


if __name__ == "__main__":
    main()
