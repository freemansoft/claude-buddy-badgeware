---
name: buddy-docs
description: Writing and formatting standard for Claude Buddy's Markdown (README.md, docs/*.md, skill files). Use whenever you create or edit any .md file in this repo, and before every commit that includes Markdown, since a pre-commit hook rejects unformatted files. Covers prettier (pinned version), wrapping, tables, tone and spelling, which doc owns which topic, link anchors, and how to mark Tufty work that isn't implemented yet.
---

# Claude Buddy documentation standard

## Formatting: prettier, pinned

All Markdown is formatted with prettier, at the version in
`.prettier-version`, with the settings in `.prettierrc.json`
(`proseWrap: preserve`). The version is pinned so that everyone's
tables and lists come out byte-identical; an unpinned `npx prettier`
can reformat files nobody touched.

After editing Markdown, and before committing:

```bash
npx --yes prettier@$(cat .prettier-version) --write <changed .md files>
git ls-files -z '*.md' | xargs -0 npx --yes prettier@$(cat .prettier-version) --config .prettierrc.json --check
```

The check uses `git ls-files` so it skips the `vendor/` submodules
(Pimoroni's Markdown isn't ours to format); it misses new files until
they're added, so check those by name too.

`.githooks/pre-commit` checks the staged `.md` files and blocks the
commit if any aren't formatted (it also runs `ruff check` and
`mpy-cross` on staged Python). It's active when
`git config core.hooksPath` prints `.githooks`; if it doesn't, tell the
user rather than setting it silently. Don't bypass the hook with
`--no-verify`; format the files instead.

To change the prettier version, change `.prettier-version` only. The
hook and CI read it, and the docs point at it rather than repeating the
number; `tests/project/test_prettier_version.py` fails if a file writes the
version out again.

## Wrapping and layout

`proseWrap: preserve` means prettier won't rewrap prose, so wrap by
hand:

- Prose and list items at about **72 columns**. Continuation lines of a
  list item are indented to the item's text.
- Tables are never wrapped; prettier aligns them. Keep cells short
  enough to read, and move long explanations into prose below.
- Code, commands and file paths in backticks. Shell blocks are
  `bash`; JSON examples are `json`.
- `**Bold lead-in:**` for the key term at the start of a bullet.

## Tone and spelling

The docs are written in plain, short sentences for someone who builds
badges, not someone who wrote this code.

- British spelling (_behaviour_, _colour_, _minimise_), matching the
  existing docs.
- Say what happens, with the number: "repaints at most every 15 s",
  not "repaints infrequently".
- Be honest about what's unverified. Anything not yet tried on the
  hardware says so (e.g. "not yet tested on hardware", "No
  measurements yet").
- Explain why, briefly, when a choice isn't obvious.

## Which doc owns what

Each topic has one home. Other docs link to it instead of copying it,
so the two can't drift apart.

| Topic                                                       | Home                                                         |
| ----------------------------------------------------------- | ------------------------------------------------------------ |
| What the badge does, install, buttons, screens, roadmap     | `README.md`                                                  |
| Checking and flashing badge firmware                        | `README.md` "Install"; `badge-bootstrap` skill               |
| Wire protocol, what's implemented, deviations from the spec | `docs/protocol.md`                                           |
| Decisions not to use parts of the spec                      | `docs/protocol.md` "Decisions"; README roadmap "Not planned" |
| Power: consumers, USB power vs battery, power constants     | `docs/power.md`                                              |
| Badger (e-ink) vs Tufty (LCD) display differences           | `docs/devices.md`                                            |
| Badger vs Tufty firmware facts, with `vendor/` citations    | `badgeware-platforms` skill                                  |
| ASCII pets: source, licence, poses, evaluation              | `docs/buddies.md`                                            |
| How Claude should change code / protocol / docs             | `.claude/skills/`                                            |
| Development setup and commands, in brief                    | `CLAUDE.md` (the README's "Development" in full)             |

When you change a number (a timeout, a step, a limit), grep the docs
for the old value and the constant's name: some numbers appear in more
than one place on purpose, as summaries.

## Devices: marking future work

Both badges run the app, each with its own profile in
`apps/claude_buddy/buddy_profile.py`. Some features aren't built yet
on one badge or either (for example, the Tufty's light sensor isn't
used). Wherever a doc compares the badges, the missing side says
_Not implemented_ and, where there's one, the plan (e.g. "Not
implemented (plan: set the backlight level)"). If
the code sets a value that hasn't been run on hardware, call it an
"untested placeholder". Every behaviour difference between the badges
gets a row in `docs/devices.md`.

## Links and anchors

- Link between docs with relative paths (`docs/power.md`,
  `../README.md#roadmap`).
- Renaming a heading changes its anchor. Before renaming, grep the repo
  for `#<old-anchor>` and fix every link.
- External references go in the README's References section, with
  what each one was used for.
