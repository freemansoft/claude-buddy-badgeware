# Claude Buddy on Badgeware

A Claude Desktop Hardware Buddy: a MicroPython Badgeware app for the
Pimoroni Badger 2350 (e-ink) and Tufty 2350 (colour LCD) that talks to
Claude Desktop over Bluetooth LE. One app folder, `apps/claude_buddy/`,
runs on both, with a profile per badge in `buddy_profile.py`. See
`README.md` for what it does, the layout and references.

## Development

Set up once per clone (the submodules are Pimoroni's firmware source,
pinned to `v3.1.1`; the venv holds the pinned ruff, mpy-cross and
mpremote):

```bash
git submodule update --init
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
git config core.hooksPath .githooks
```

Checks (the same as CI):

```bash
.venv/bin/python -m unittest discover -s tests   # unittest, not pytest
find apps/claude_buddy -name '*.py' -print0 | xargs -0 -n1 .venv/bin/python -m mpy_cross -o /dev/null
.venv/bin/ruff check .
git ls-files -z '*.md' | xargs -0 npx --yes prettier@$(cat .prettier-version) --config .prettierrc.json --check
```

- Tests are host-only (CPython with stand-ins for Badgeware); no badge
  needed
- Lint: `ruff.toml` extends Pimoroni's `vendor/tufty2350/ci/ruff.toml`,
  so it needs the submodules. `ruff format` is not used: Pimoroni's
  firmware CI only runs `ruff check`
- Markdown: the prettier version lives only in `.prettier-version`.
  Follow the `buddy-docs` skill for every `.md` edit
- Pre-commit hook (`.githooks/pre-commit`): prettier on staged `.md`,
  `ruff check` on staged `.py`, mpy-cross on staged
  `apps/claude_buddy/*.py`, all on the staged content. Don't bypass it
  with `--no-verify`
- CI (`.github/workflows/ci.yml`) runs the lint, MicroPython syntax,
  tests and Markdown checks on every PR and push to `main`
- Tools run as scripts from the repository root
  (`python3 tools/badge_info.py`, `tools/install.py`,
  `tools/badge_check.py files`, `tools/flash_firmware.py`). They need
  `mpremote` on `PATH`
- No simulator: the app lives on Bluetooth, which the Badgeware
  simulators don't have. Host tests, then a real badge
- Project skills: `buddy-change` (any change under `apps/claude_buddy/`:
  power and device rules, checks, installing on a badge),
  `buddy-protocol` (BLE and the Hardware Buddy spec), `buddy-docs`
  (Markdown standard), `badge-bootstrap` (identify a badge, check or
  flash firmware, first install) and `badgeware-platforms` (how the
  Badger and Tufty firmware differ, cited from `vendor/`; read it before
  touching the display, loop or buttons)

## On a real badge

- Before every install, check the firmware with
  `python3 tools/badge_info.py` (badge in normal mode). If it says OLDER, stop,
  tell the user and offer the update (`badge-bootstrap`). If the badge
  is already in disk mode, ask whether the firmware was checked, or have
  the user eject and press RESET first
- Install only with `python3 tools/install.py`, never a copy by hand.
  Nobody touches RESET or the cable until the drive has ejected: a
  restart before the eject once left app files cut to 4096 bytes (a
  `SyntaxError` at start-up)
- After the eject, check the copy from the badge's side with
  `python3 tools/badge_check.py files`, not by reading the mounted
  drive: the computer holds writes in its cache until the eject
- Button presses (RESET, double-tap RESET, BOOT) need the user's hands:
  give exact instructions and wait for them; never assume a press
  happened
- Ad-hoc `mpremote`: pick the port whose `mpremote devs` line names the
  badge (`Badger 2350` or `Tufty 2350`; other boards are often plugged
  in), and end with `reset`
  (`mpremote connect <port> exec "..." reset`), or the badge stays
  frozen on its last screen until RESET.
  `badge_info.py` and `badge_check.py` do this themselves. Any of these
  restarts the badge and drops its Claude Desktop link, so check the
  user isn't in the middle of something
- `/system` (the drive) is read-only from MicroPython, so app files only
  change in disk mode; the receive log and saved settings are in
  `/state`

Read hardware and runtime behaviour from the firmware source in
`vendor/badger2350` and `vendor/tufty2350`, not only from
badgewa.re/docs: the docs can lag the source.
