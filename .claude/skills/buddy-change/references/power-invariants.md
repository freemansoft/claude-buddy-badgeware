# Power invariants

Each rule the app relies on to save power, why it matters, where it
lives, and what protects it. Paths are under `apps/claude_buddy/`
unless noted. "No test" means only reading the code protects it, so
check those by hand when a change comes near.

Desktop sends a heartbeat every 70–200 ms, almost all identical, and
polls `status` about every 2 s. Any rule below that breaks usually
breaks at that rate.

## Display (e-ink, Badger)

| Rule                                                                                              | Why                                                                               | Where                                                       | Protected by                                                                                                             |
| ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Repaint only when the screen key or page changes                                                  | Each e-ink refresh is ~1–2 s of panel power and a visible flash                   | `buddy_painter.py` `Painter.tick`; `buddy_model.screen_key` | `test_painter.test_no_repaint_without_change`                                                                            |
| Battery and token labels sit after `KEY_LEN` in the tuple (ride along)                            | They change often; in the key they would cause a refresh every 10 s or every turn | `buddy_model.py` `screen()`, `KEY_LEN`                      | `test_battery_change_does_not_change_key`, `test_token_change_does_not_change_key`, `test_battery_and_tokens_ride_along` |
| `Charging` → `Full` doesn't change the key                                                        | It flips on its own while plugged in                                              | `buddy_model.py` `battery_label`                            | `test_charging_to_full_does_not_change_key`                                                                              |
| Low battery (below 20%, clears at 25%) is in the key, with hysteresis                             | The warning must appear on its own, but must not flap on voltage jitter           | `buddy_model.py` `set_battery`, `S_BATTERY_LOW`             | `test_low_battery_changes_key_with_hysteresis`                                                                           |
| USB plug/unplug is in the key and urgent                                                          | The user expects to see it; it happens rarely                                     | `buddy_model.py` `is_urgent`, `S_ON_USB`                    | `test_usb_plug_and_unplug_are_urgent`, `test_usb_change_repaints_after_settle_not_throttle`                              |
| Only prompts, header and kind changes are urgent; the rest is throttled 10 s (Badger on USB: 5 s) | Status text (summary, transcript, counts) changes on most heartbeats              | `buddy_model.is_urgent`; `Refresh.status_interval_ms`       | `test_status_text_change_is_throttled`, `test_status_change_is_throttled`                                                |
| Urgent repaints settle 300 ms first                                                               | Coalesces a heartbeat plus a status poll into one refresh                         | `Refresh.settle_ms`                                         | `test_first_paint_after_settle`                                                                                          |
| ~1 s hold after A/B                                                                               | Desktop's follow-up heartbeat lands in the same refresh as the result             | `Refresh.answer_hold_ms`, `Painter.hold`                    | `test_hold_delays_paint`                                                                                                 |
| "No sessions" only after 5 s of `total == 0`                                                      | Closing one session and opening another would otherwise cost two refreshes        | `NO_SESSIONS_DELAY_MS`                                      | `test_no_sessions_screen_after_delay`                                                                                    |
| No new refresh while the panel is busy                                                            | Stacking refreshes wastes power and loses frames                                  | `Painter.tick` with `busy`; `_display_busy()`               | `test_waits_while_display_busy`                                                                                          |
| Page turns refresh only on a button press                                                         | Paging must not become an animation                                               | `Painter.turn`                                              | `test_page_turn_repaints_without_throttle`, `test_status_update_keeps_page`                                              |
| `NON_BLOCKING` mode                                                                               | The loop keeps serving buttons and BLE during a refresh                           | `__init__.py` `badge.mode(...)`                             | No test                                                                                                                  |
| Nothing animates                                                                                  | Any animation on e-ink is a refresh per frame                                     | `buddy_view.py`                                             | No test                                                                                                                  |

## CPU, sensors and storage

| Rule                                                                 | Why                                                                     | Where                                    | Protected by                           |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------- | ---------------------------------------- | -------------------------------------- |
| Loop ends with `time.sleep_ms(LOOP_SLEEP_MS)` (20 ms)                | CPU idle between passes; ~50 passes/s is enough for buttons and BLE     | `__init__.py` `update()`                 | No test                                |
| Battery ADC every `BATTERY_POLL_MS` (10 s), or at once on USB change | ADC reads cost power; Desktop's `status` poll reuses the cached reading | `__init__.py` `_poll_battery`, `_status` | No test                                |
| USB presence is a pin read every pass, not an ADC read               | Cheap, and lets plug/unplug show in ~0.3 s                              | `__init__.py` `_usb_present`             | No test                                |
| `State.save()` only on a real change or a recorded decision          | Flash writes cost power and wear; Desktop resends `owner` per connect   | `buddy_model.py` (settings), `_Store`    | `test_unchanged_owner_not_saved_again` |
| Receive log flushes every 2 s, off unless its file exists            | Avoids a flash write per received line                                  | `buddy_rxlog.py` `FLUSH_MS`              | `tests/test_rxlog.py`                  |

## Radio and lights

| Rule                                                            | Why                                                                      | Where                                        | Protected by                                                      |
| --------------------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------- | ----------------------------------------------------------------- |
| Never `badge.sleep()` while the app runs                        | Sleep powers down and drops the BLE link; BLE can't wake the badge       | `__init__.py` (absence of sleep)             | No test (`docs/power.md`: "Why the badge never sleeps")           |
| Advertise only while unconnected, every 100 ms                  | Advertising keeps the radio busy; a longer interval is a phase 3 item    | `buddy_ble.py` `_ADV_INTERVAL_US`, `service` | No test                                                           |
| Drop a silent link after 60 s                                   | A silent central would hold the only slot; Desktop could never reconnect | `buddy_model.DEAD_LINK_MS`, `ble.drop`       | `test_dead_link_after_timeout`, `DropTest`                        |
| Radio off on exit                                               | Nothing should draw power for Claude Buddy once the user leaves the app  | `__init__.py` `on_exit`, `buddy_ble.close`   | No test                                                           |
| Waiting double-blink only on USB power, and not on a stale link | The lights cost charge every cycle on battery                            | `__init__.py` `lights.tick(...)` condition   | No test (`test_lights.py` covers the pattern, not the USB gating) |
| Lights only change hardware on a level change                   | `tick()` runs 50 times a second                                          | `buddy_lights.py` `CaseLights.tick`          | `test_only_changes_reach_hardware`                                |
| A/B blink instead of a "sending…" screen                        | Instant feedback without an extra e-ink refresh                          | `CaseLights.ack`                             | `test_ack_blink`                                                  |

## Backlight (Tufty)

| Rule                                                                  | Why                                                        | Where                                        | Protected by                                                                          |
| --------------------------------------------------------------------- | ---------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------- |
| Dims after the profile's `Backlight.idle_ms` on battery; never on USB | The always-on backlight is likely the Tufty's biggest draw | `buddy_backlight.py` `Backlight.tick`        | `test_dims_after_idle_on_battery`, `test_never_dims_on_usb`                           |
| Bright while a prompt waits or after an urgent change                 | The user must see what needs them                          | `__init__.py` `backlight.tick(..., keep_on)` | `test_stays_bright_while_something_needs_the_user`, `test_keep_on_wakes_a_dim_screen` |
| First press while dim only wakes                                      | A/B/C must never act on a screen the user can't see        | `__init__.py` `woke`; `Backlight.press`      | `test_first_press_while_dim_only_wakes`                                               |
| Only level changes reach the hardware                                 | `tick()` runs 50 times a second                            | `Backlight._apply`                           | `test_only_changes_reach_the_hardware`                                                |
| Back to bright on exit                                                | The menu mustn't be left dim                               | `on_exit()`; `Backlight.restore`             | `test_restore_on_exit`                                                                |

## Refresh per power source

| Rule                                                                                      | Why                                                              | Where                                          | Protected by                                            |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------- |
| The Badger uses the e-ink timings on USB and battery (status 5 s on USB, 10 s on battery) | Every e-ink refresh flashes and costs power, whatever the supply | `buddy_profile.BADGER`                         | `test_badger_uses_the_eink_rules_on_both_power_sources` |
| The Tufty is live only on USB; on battery it uses the e-ink timings                       | Every redraw costs power on battery; on USB it's free            | `buddy_profile.TUFTY`                          | `test_tufty_is_live_on_usb_and_eink_on_battery`         |
| Live still skips identical screens                                                        | Heartbeats arrive every ~100 ms, almost all identical            | `Painter.tick` (`state == shown_state`)        | `test_identical_heartbeats_still_paint_nothing`         |
| Unplugging switches back to the e-ink timings at once                                     | `on_usb` is in the key and urgent                                | `__init__.py` `painter.set_refresh` every pass | `test_unplugged_passengers_ride_along_again`            |

## Planned (don't break the path to these)

From the README roadmap and `docs/power.md`: a longer advertising
interval, a lower CPU clock, a slower idle loop, sleeping while
disconnected on battery (relaunch on button wake), and setting the
Tufty backlight level from its light sensor. Prefer changes that keep
these easy: timings as named constants at the top of the module, and
refresh decisions inside the painter.
