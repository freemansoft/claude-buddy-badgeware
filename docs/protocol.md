# Hardware Buddy protocol: what this app implements

The authoritative spec is
[anthropics/claude-desktop-buddy `REFERENCE.md`](https://github.com/anthropics/claude-desktop-buddy/blob/main/REFERENCE.md)
(MIT). This page records the subset the badge uses and the decisions
made where the spec leaves room. Code: `apps/claude_buddy/buddy_model.py`
(messages) and `apps/claude_buddy/buddy_ble.py` (transport).

## Transport

Nordic UART Service. Each message is one UTF-8 JSON object terminated
by `\n`, sent in either direction.

| Role | UUID | Properties |
|---|---|---|
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | |
| RX (Desktop → badge) | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | write, write-without-response |
| TX (badge → Desktop) | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | read, notify |

- **Name:** `Claude_XXXXXX`. Claude Desktop's picker filters on the
  `Claude` prefix.
  - `XXXXXX` is the RP2350's 8-byte unique chip ID, XOR-folded to 3
    bytes, so it's stable across reboots.
  - The reference suggests MAC bytes instead. That's avoided here
    because BTstack falls back to a *random* static address when the
    controller reports no public one, and that address could change
    every boot.
  - The badge's header always shows this name, so it can be matched
    against the picker.
- **Advertising packet (29 of 31 bytes):** flags, the 128-bit NUS UUID,
  and the shortened name `Claude`. The scan response carries the
  complete name `Claude_XXXXXX`. Passive scanners (which never request
  a scan response) still see the service and a `Claude…` name. Active
  scanners see the full name.
- **MTU:** the badge asks BTstack for 247 and records whatever the
  central negotiates (`_IRQ_MTU_EXCHANGED`). Outgoing lines are split
  into `MTU − 3` byte notifications, or 20 bytes before any exchange.
  Claude Desktop reassembles them.
- **RX:** the characteristic buffer is in append mode (1 KB). Bytes are
  queued from the IRQ and split into lines in the main loop. A line
  longer than 6 KB is dropped whole. Turn events are capped at 4 KB by
  the Desktop.
- **Security:** the link is **not encrypted**. Badgeware's rp2
  MicroPython builds BTstack without
  `MICROPY_PY_BLUETOOTH_ENABLE_PAIRING_BONDING`, so there is no
  passkey or bonding API. The status ack reports `"sec": false`. Per the
  reference, Desktop still connects. Mitigations:
  - A permission decision is only ever sent from a physical A/B press.
  - Character-pack pushes (file writes) are refused.

## Desktop → badge

| Message | Handling |
|---|---|
| Heartbeat (no `cmd`): `total`, `running`, `waiting`, `msg`, `entries`, `tokens`, `tokens_today`, optional `prompt {id, tool, hint}` | Updates the screen. A `prompt` makes the screen actionable. Its `hint` is kept up to 2,000 characters, with line breaks, and paged with UP/DOWN. When `prompt` is absent, any prompt is cleared. Missing counters keep their previous value. `tokens_today` is shown rounded (`31k today`) with the session counts on the bottom row of the status screen, but never triggers a refresh by itself. `tokens` is ignored. |
| `{"evt":"turn", ...}` | Assistant turns: the `text` blocks become **Claude's latest reply** on the status screen. Simple markdown is stripped; it's capped at 3,000 characters and 40 paragraphs, and paged with UP/DOWN. A turn with no text (tool calls only) keeps the previous reply. The last `tool_use` name and a one-line summary are also kept; they're shown only when Desktop reports `waiting` without a `prompt`, a single session is open, and Desktop's `msg` names that tool (Desktop drops turn events over 4 KB, so the last tool seen may not be the one waiting). User turns are ignored. |
| `{"time":[epoch, tz_offset]}` | Ignored (no clock on screen yet). |
| Anything else without `cmd` or `evt` | Treated as a heartbeat only if it has at least one heartbeat field (`total`, `running`, `waiting`, `msg`, `entries`, `tokens`, `tokens_today`, `prompt`). Otherwise ignored, so an unknown one-shot message can't clear a pending prompt. |
| `{"cmd":"status"}` | Replies with the status ack (below). |
| `{"cmd":"name","name":...}` | Saved and reported back as `data.name` in the status ack. Ack `{"ack":"name","ok":true,"n":0}`. The advertised BLE name doesn't change, and the header keeps showing it so it matches the picker. Without a `name` string: ack `ok:false` and the saved name is kept. |
| `{"cmd":"owner","name":...}` | Saved (also accepts an `owner` key). Ack `ok:true`. Without a value: ack `ok:false` and the saved owner is kept. Flash is only written when the value changes (Desktop sends it on every connect). |
| `{"cmd":"unpair"}` | Ack `ok:true`. There are no bonds to erase on this firmware. |
| `char_begin` / `file` / `chunk` / `file_end` / `char_end` | Ack `ok:false`, `"error":"not supported"`. |
| Anything else with `cmd` | Ack `ok:false`, `"error":"unknown command"`. |

## Badge → Desktop

```json
{"cmd":"permission","id":"<prompt.id>","decision":"once"}
{"cmd":"permission","id":"<prompt.id>","decision":"deny"}
```

Sent on A (`once`) or B (`deny`), at most once per prompt id, and only
for the prompt currently drawn on the panel (not one that has arrived
but isn't on screen yet). A and B pressed together send nothing.

```json
{"ack":"status","ok":true,"data":{
  "name":"Claude_A1B2C3","sec":false,
  "bat":{"pct":87,"mV":3990,"usb":true},
  "sys":{"up":8412,"heap":84200},
  "stats":{"appr":42,"deny":3,"vel":0,"nap":0,"lvl":0}}}
```

- `bat.mA` is omitted because the badge has no current sensor.
- `bat` is the reading sampled every 10 s, which the header also uses.
  It isn't re-sampled on each `status` poll.
- `appr`/`deny` are counts of decisions made on the badge, persisted in
  `/state/claude_buddy.json`.
- `vel`, `nap` and `lvl` are pet/level features that aren't
  implemented; they are reported as 0, which means "no data".

No `hello` message is sent. The reference doesn't define one.

## Timing

- Desktop sends a heartbeat on every change, plus one every 10 s.
- After 30 s with no heartbeat while connected, the header shows
  **No data**.
- After 60 s with no heartbeat, the badge disconnects and advertises
  again. Session counts, summary, transcript lines and any pending
  prompt are cleared on every connect and disconnect; Claude's last
  reply and today's tokens are kept.
- In practice Desktop sends heartbeats much more often than the
  10 s minimum: every 70–200 ms, almost all identical.
- Desktop polls `status` every couple of seconds. Status replies never
  cause a screen refresh.
