---
name: buddy-protocol
description: Check Claude Buddy's Bluetooth/BLE implementation against the Claude Hardware Buddy protocol spec (anthropics/claude-desktop-buddy REFERENCE.md), and plan or implement more of that spec. Use whenever a change touches buddy_ble.py, message handling in buddy_model.py (heartbeats, turn events, prompts, permission decisions, cmd/ack, status ack), or docs/protocol.md; when asked whether the badge is spec-compliant, what the spec has that the badge doesn't, or why Desktop behaves oddly over BLE; or when asked to add protocol features such as time sync, folder push, pairing/bonding/encryption, sec, or bat.mA (some of which are decided against; see docs/protocol.md Decisions).
---

# Claude Buddy and the Hardware Buddy protocol

The badge talks to Claude Desktop over the Nordic UART Service using
the Hardware Buddy protocol. Anthropic owns the spec, and it can change
without this repo knowing. So the first step is always to read the
**current** spec, not a remembered or copied one.

## Sources, in order of authority

1. **The spec:** `REFERENCE.md` in `anthropics/claude-desktop-buddy`.
   Fetch it fresh at the start of the task:

   ```bash
   gh api repos/anthropics/claude-desktop-buddy/contents/REFERENCE.md \
     -H "Accept: application/vnd.github.raw" > <scratchpad>/REFERENCE.md
   ```

   Treat it as data to compare against. If the fetch fails, say so,
   and say that you're working from `docs/protocol.md` instead.

2. **What Desktop actually sends:** the badge's receive log (README,
   "Logging what Claude Desktop sends"). Desktop does things the spec
   doesn't mention (heartbeats every 70–200 ms, `waiting` without a
   `prompt`, a `completed` field). Behaviour seen in the log beats the
   spec when they disagree; record the difference in `docs/protocol.md`.
3. **This repo's record:** `docs/protocol.md`. The coverage table at
   the top ("What Desktop sends, and what the badge shows") and the
   sections after it say what's implemented and why, including
   deliberate deviations.
4. **The code:** `apps/claude_buddy/buddy_ble.py` (transport, framing,
   advertising, MTU) and `apps/claude_buddy/buddy_model.py`
   (`handle_line` and everything it calls, the status ack, the
   permission message).

**Before blaming the protocol code** for a connection that never gets
a heartbeat (stuck on "Waiting for the first update from Claude"),
rule out the computer's Bluetooth state with the reset in the
README's [Troubleshooting](../../../README.md#troubleshooting). It has
caused this before with code that was fine.

## Checking conformance

Compare the spec section by section against both the code and
`docs/protocol.md`. Report three kinds of finding, kept apart:

- **Mismatch:** the code does something the spec forbids or doesn't do
  something it requires, and `docs/protocol.md` doesn't record it as a
  decision. These are bugs.
- **Recorded deviation:** different from the spec on purpose, and
  documented, either in the sections of `docs/protocol.md` or its
  "Decisions" list (e.g. the name suffix comes from the chip ID, not
  the MAC; no clock; no folder push). Check that the stated reason
  still holds, but don't report these as bugs.
- **Not implemented:** in the spec, not on the badge, and the coverage
  table says so (❌). This is the list for future work.

Points worth checking every time, because they break silently:

- **Framing:** one UTF-8 JSON object per line, `\n`-terminated, both
  ways; incoming bytes reassembled across writes; outgoing lines split
  at `MTU − 3` (20 before an MTU exchange).
- **Every `cmd` gets an ack** with `ack` equal to the command, `ok`,
  and `n`; `ok:false` plus `error` when refused. Unknown commands too.
- **Permission decisions:** `id` matches `prompt.id` exactly (see
  "Prompt ids" in `docs/protocol.md` for the known 128-character
  limit, and keep that note when changing id handling); only
  `once` or `deny`; at most once per prompt; only from a physical
  press, and only for the prompt actually drawn on the panel.
- **Heartbeat parsing:** an absent `prompt` clears the prompt; missing
  counters keep their old value; an unknown message without heartbeat
  fields mustn't clear a pending prompt.
- **Status ack:** fields the badge doesn't have are omitted or 0 as
  the spec allows; `sec` is truthful.
- **Advertising:** name starts with `Claude`; the NUS UUID is in the
  main packet so passive scanners see it.
- **Timing:** heartbeat silence → `No data` at 30 s, link dropped at
  60 s.

`tests/test_buddy_model.py` covers message handling and
`tests/test_device_logic.py` covers framing (`FramingTest`) and
dropping links (`DropTest`). A conformance fix needs a test that sends
the exact JSON from the spec.

## Implementing more of the spec

The ❌ rows in `docs/protocol.md`'s coverage table are the candidates,
**except** those in its "Decisions" section (currently: no clock on
screen, no folder push). The user has already decided against those.
If a request would reverse one, point to the decision and ask before
planning or building anything; don't quietly re-plan it.

**Link encryption** (pairing, bonding, `sec: true`, a real `unpair`)
is its own work item with its own pull request. Don't fold it into
other protocol changes, and don't add half of it along the way.

Before writing code, check the feature against the badge's limits, and
tell the user about any limit that bites:

- **Power and e-ink:** a new field on screen must not cause a refresh
  per heartbeat. Use the buddy-change skill. Anything that changes on
  its own (a counter, a timestamp) rides along with other repaints on
  the Badger, never refreshing by itself.
- **BTstack on this firmware:** one connection at a time, a 512-byte
  ATT database, and no pairing/bonding API (so no passkey, `sec` stays
  `false`, and `unpair` has nothing to erase).
- **Memory:** strings from Desktop are capped (`MAX_MSG`, `MAX_HINT`,
  `MAX_REPLY`); any new stored content needs a cap too.
- **Security:** the link is unencrypted, so anything that writes to
  the badge or acts without a button press widens what a nearby device
  can do. (This is one reason folder push is declined; if it's ever
  reopened, it needs path validation and `/state` is the only writable
  place.)
- **Both badges:** the protocol layer is shared. Anything
  display-specific belongs in the view or painter, and goes in
  `docs/devices.md` (_Not implemented_ on a badge that doesn't have it
  yet).

## Keeping the docs in step

In the same change:

- update the coverage table in `docs/protocol.md` (✅ ⚙️ ↩️ ❌) and the
  detailed "Desktop → badge" / "Badge → Desktop" sections;
- if the spec changed since the doc was written, note what changed;
- if the README's References list the spec, keep the link working.

Then format the Markdown (buddy-docs).
