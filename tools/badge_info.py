#!/usr/bin/env python3
"""Identify the Badgeware badge on USB and check its firmware.

The badge must be in normal mode (menu or an app running), not USB
disk mode. This stops whatever is running on it (mpremote interrupts
it); press RESET afterwards to get back to the menu.

    python3 tools/badge_info.py              # finds the badge
    python3 tools/badge_info.py --port /dev/cu.usbmodem201401
    python3 tools/badge_info.py --json       # machine-readable

It reports:
- the model, from badge.model ("badger" or "tufty");
- the MicroPython build and its build date;
- whether bluetooth and aioble are present (Claude Buddy needs both);
- whether Claude Buddy is installed;
- the latest Badgeware release for that model on GitHub, and whether
  the badge's firmware looks current. The firmware doesn't record its
  Pimoroni release number, so this compares build dates.

Needs mpremote (pip install mpremote). Standard library otherwise.
"""

import argparse
import json
import shutil
import subprocess
import sys

import badgeware_release as rel

# Runs on the badge. badge.model is the source of truth for the model.
# Badgeware v3 creates builtins.badge when the menu starts, but it is
# gone by the time mpremote's code runs (seen on a Tufty with v3.1.1),
# though the badgeware.badge module stays loaded. So: use builtins.badge
# if it's there, else make a Badge() from that module (its constructor
# only reads MODEL and switches the case lights off), else read the
# module's MODEL (older builds, MicroPython 1.27, have no Badge.model),
# and only then the os.uname() slice Badgeware itself uses.
DEVICE_SNIPPET = r"""
import builtins, json, os, sys
u = os.uname()
info = {"machine": u.machine, "release": u.release, "version": u.version,
        "build": getattr(sys.implementation, "_build", "")}
try:
    import badgeware.badge
except Exception:
    pass
b = getattr(builtins, "badge", None)
mod = None
for key in sys.modules:
    if key == "badgeware.badge" or key.endswith("badgeware/badge"):
        mod = sys.modules[key]
src = "badge.model"
if b is None and mod is not None and hasattr(mod, "Badge"):
    try:
        b = mod.Badge()
        src = "badge.model (new Badge object)"
    except Exception:
        b = None
if b is not None and hasattr(b, "model"):
    info["model"], info["model_source"] = b.model, src
elif mod is not None and hasattr(mod, "MODEL"):
    info["model"], info["model_source"] = mod.MODEL, "badgeware.badge.MODEL (no badge object)"
else:
    info["model"], info["model_source"] = u.machine[9:-17].lower(), "os.uname().machine"
for name in ("bluetooth", "aioble"):
    try:
        __import__(name)
        info[name] = True
    except ImportError:
        info[name] = False
try:
    info["apps"] = sorted(os.listdir("/system/apps"))
except OSError:
    info["apps"] = None
print("BADGE_INFO " + json.dumps(info))
"""


def run(cmd, timeout=30):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def choose_port(port):
    """The badge's serial port: ``port`` if given, else the only badge
    `mpremote devs` lists. Other serial devices are ignored, so
    mpremote can't pick the wrong board."""
    if port:
        return port
    devs = run(["mpremote", "devs"]).stdout
    badges = rel.badge_ports(devs)
    if not badges:
        sys.exit(
            "No badge found. Plug it in by USB in normal mode (menu showing),\n"
            "not disk mode, then try again. `mpremote devs` lists what's connected."
        )
    if len(badges) > 1:
        listed = "\n".join("  {}  ({})".format(p, m) for p, m in badges)
        sys.exit("More than one badge connected; pick one with --port:\n" + listed)
    return badges[0][0]


def parse_info(output):
    for line in output.splitlines():
        if line.startswith("BADGE_INFO "):
            return json.loads(line[len("BADGE_INFO "):])
    raise ValueError("no BADGE_INFO line in:\n" + output)


def read_badge(port):
    result = run(["mpremote", "connect", port, "exec", DEVICE_SNIPPET])
    if result.returncode != 0:
        sys.exit("mpremote failed:\n" + (result.stderr or result.stdout))
    return parse_info(result.stdout)


def latest_for(model):
    """(release dict, None) or (None, reason)."""
    if model not in rel.MODELS:
        return None, "not a Claude Buddy target"
    try:
        return rel.fetch_release(model), None
    except Exception as e:  # offline, rate-limited ...
        return None, "couldn't reach GitHub ({})".format(e)


def report(port, info, release, why_not):
    model = info["model"]
    built = rel.build_date(info["version"])
    lines = [
        ("Port", port),
        ("Model", "{}  (from {})".format(model, info["model_source"])),
        ("Board", info["machine"]),
        ("MicroPython", "{}  ({})".format(info["release"], info["version"])),
        ("Bluetooth", "{}, aioble {}".format(
            "yes" if info["bluetooth"] else "NO", "yes" if info["aioble"] else "NO")),
    ]
    apps = info.get("apps")
    if apps is None:
        lines.append(("Claude Buddy", "unknown (no /system/apps)"))
    else:
        lines.append(("Claude Buddy", "installed" if "claude_buddy" in apps else "not installed"))

    if release:
        published = release.get("published_at", "")[:10]
        status = rel.firmware_status(built, published)
        verdict = {
            "current": "looks current (built {})".format(built),
            "older": "OLDER: built {}, before the latest release".format(built),
            "newer": "built {}, after the latest release (pre-release or custom?)".format(built),
            "unknown": "can't tell (no build date in the version string)",
        }[status]
        lines.append(("Latest", "{} {}, published {}".format(
            rel.repo_for(model), release["tag_name"], published)))
        lines.append(("Firmware", verdict))
    else:
        lines.append(("Latest", why_not))

    width = max(len(k) for k, _ in lines) + 1
    for key, value in lines:
        print("{} {}".format((key + ":").ljust(width), value))
    if model not in rel.MODELS:
        print("\nClaude Buddy supports {} only.".format(" and ".join(rel.MODELS)))
    if not (info["bluetooth"] and info["aioble"]):
        print("\nThis firmware lacks Bluetooth support Claude Buddy needs; update it.")
    print("\nThe badge's running program was stopped; press RESET to get back to the menu.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", help="the badge's serial port (default: find it)")
    parser.add_argument("--json", action="store_true", help="print the raw details as JSON")
    parser.add_argument("--offline", action="store_true", help="don't look up the latest release")
    args = parser.parse_args()

    if not shutil.which("mpremote"):
        sys.exit("mpremote not found. Install it with: pip install mpremote")
    port = choose_port(args.port)
    info = read_badge(port)
    release, why_not = (None, "not checked (--offline)") if args.offline else latest_for(info["model"])

    if args.json:
        info["port"] = port
        info["build_date"] = rel.build_date(info["version"])
        if release:
            info["latest_tag"] = release["tag_name"]
            info["latest_published"] = release.get("published_at", "")[:10]
            info["firmware_status"] = rel.firmware_status(
                info["build_date"], info["latest_published"])
        print(json.dumps(info, indent=2))
    else:
        report(port, info, release, why_not)


if __name__ == "__main__":
    main()
