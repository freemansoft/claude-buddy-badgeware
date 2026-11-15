"""Helpers shared by badge_info.py and flash_firmware.py.

Looks up Pimoroni's Badgeware firmware releases on GitHub and finds a
badge on USB. Standard library only; the GitHub API is used without a
token (60 requests an hour is plenty).
"""

import datetime
import json
import re
import urllib.request

# badge.model values that Claude Buddy knows about. Badgeware derives
# badge.model from os.uname().machine, so it is "badger", "tufty" or
# "blinky" (Blinky, an LED matrix, isn't a target).
MODELS = ("badger", "tufty")

# Each model's firmware lives in its own repo: pimoroni/badger2350 ...
REPO = "pimoroni/{}2350"
API = "https://api.github.com/repos/{repo}/releases/{which}"
USER_AGENT = "claude-buddy-badgeware-tools"

# A badge in normal (MicroPython) mode, as `mpremote devs` lists it:
#   /dev/cu.usbmodem201401 bb71... 2e8a:1101 Pimoroni Pimoroni Tufty 2350 MicroPython
DEVICE_RE = re.compile(r"\b(Badger|Tufty|Blinky) 2350\b", re.IGNORECASE)

# MicroPython's os.uname().version ends "... on YYYY-MM-DD" (build date).
BUILD_DATE_RE = re.compile(r"\bon (\d{4}-\d{2}-\d{2})\b")

# UF2 blocks start with these two little-endian magic numbers.
UF2_MAGIC = b"UF2\n" + (0x9E5D5157).to_bytes(4, "little")

# A release built more than this many days before the latest release's
# publish date counts as older. CI builds and publishes within hours,
# so a few days' slack only absorbs time zones and re-runs.
BUILD_SLACK_DAYS = 3


def repo_for(model):
    return REPO.format(model)


def fetch_release(model, tag=None, timeout=15):
    """The latest (non-pre-release) release for ``model``, or ``tag``."""
    which = "tags/" + tag if tag else "latest"
    url = API.format(repo=repo_for(model), which=which)
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def asset_name(model, tag, with_filesystem):
    """Pimoroni's file name, e.g. tufty-v3.1.1-micropython.uf2."""
    suffix = "-with-filesystem" if with_filesystem else ""
    return "{}-{}-micropython{}.uf2".format(model, tag, suffix)


def pick_asset(release, model, with_filesystem):
    """The release asset (a dict from the API) for this model and flavour."""
    want = asset_name(model, release["tag_name"], with_filesystem)
    for asset in release.get("assets", ()):
        if asset.get("name") == want:
            return asset
    names = ", ".join(a.get("name", "?") for a in release.get("assets", ()))
    raise LookupError("{} has no {} (assets: {})".format(release["tag_name"], want, names or "none"))


def build_date(version):
    """'YYYY-MM-DD' from os.uname().version, or None."""
    match = BUILD_DATE_RE.search(version or "")
    return match.group(1) if match else None


def _days(date):
    return datetime.date.fromisoformat(date).toordinal()


def firmware_status(built, published):
    """Compare a firmware build date with the latest release's publish
    date (both 'YYYY-MM-DD'). Returns "current", "older", "newer" or
    "unknown". It's a heuristic: the firmware doesn't record which
    Pimoroni release it came from, only when it was built."""
    if not built or not published:
        return "unknown"
    gap = _days(built) - _days(published[:10])
    if gap < -BUILD_SLACK_DAYS:
        return "older"
    if gap > BUILD_SLACK_DAYS:
        return "newer"
    return "current"


def is_uf2(head):
    """True if ``head`` (the first bytes of a file) is a UF2 block."""
    return head[:8] == UF2_MAGIC


def badge_ports(devs_output):
    """[(port, model)] for every badge in `mpremote devs` output."""
    found = []
    for line in devs_output.splitlines():
        match = DEVICE_RE.search(line)
        if match and line.split():
            found.append((line.split()[0], match.group(1).lower()))
    return found
