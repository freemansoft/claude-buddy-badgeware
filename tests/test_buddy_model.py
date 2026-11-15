"""Host-side tests for the protocol model (CPython, no badge needed).

    python3 -m unittest discover -s tests -v
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "claude_buddy"))

import buddy_model as bm  # noqa: E402


class MemoryStore:
    def __init__(self, initial=None):
        self.data = dict(initial or {})
        self.saves = 0

    def load(self, defaults):
        defaults.update(self.data)

    def save(self, data):
        self.data = dict(data)
        self.saves += 1


def line(obj):
    return (json.dumps(obj) + "\n").encode()


def heartbeat(**fields):
    base = {"total": 1, "running": 1, "waiting": 0, "msg": "working", "entries": []}
    base.update(fields)
    return line(base)


PROMPT = {"id": "req_1", "tool": "Bash", "hint": "rm -rf ./build"}


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.model = bm.BuddyModel(
            "Claude_ABC123",
            store=self.store,
            status_provider=lambda: {"bat": {"pct": 80}, "sys": {"up": 5, "heap": 1000}},
        )

    def connect(self, now=0):
        self.model.on_connect(now)

    def answer(self, approve, now):
        """A/B with the current prompt on the panel (see Painter)."""
        return self.model.permission_message(approve, now, self.model.prompt_doc())

    # -- screens --------------------------------------------------------

    def test_pair_screen_before_connect(self):
        scr = self.model.screen(0)
        self.assertEqual(scr[bm.S_KIND], bm.KIND_PAIR)
        self.assertEqual(scr[bm.S_STATUS], "Not connected")
        self.assertEqual(scr[bm.S_NAME], "Claude_ABC123")
        self.assertFalse(scr[bm.S_EMPHASIS])
        self.assertIn("Claude_ABC123", scr[bm.S_LINES][-1][1])

    def test_connected_before_first_heartbeat(self):
        self.connect()
        scr = self.model.screen(10)
        self.assertEqual(scr[bm.S_KIND], bm.KIND_CONNECTED)
        self.assertEqual(scr[bm.S_STATUS], "Connected")

    def test_status_heartbeat_is_dimmed(self):
        self.connect()
        self.model.handle_line(heartbeat(entries=["10:42 git push", "10:41 yarn test"]), 100)
        scr = self.model.screen(100)
        self.assertEqual(scr[bm.S_KIND], bm.KIND_STATUS)
        self.assertFalse(scr[bm.S_EMPHASIS])
        self.assertFalse(scr[bm.S_ACTIONABLE])
        self.assertEqual(scr[bm.S_TITLE], "working")
        texts = [t for _, t in scr[bm.S_LINES]]
        self.assertIn("10:42 git push", texts)

    def test_prompt_is_full_contrast_and_actionable(self):
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 100)
        scr = self.model.screen(100)
        self.assertEqual(scr[bm.S_KIND], bm.KIND_PROMPT)
        self.assertTrue(scr[bm.S_EMPHASIS])
        self.assertTrue(scr[bm.S_ACTIONABLE])
        self.assertEqual(scr[bm.S_TITLE], "Allow Bash?")
        self.assertEqual(scr[bm.S_LINES][0], (bm.WRAP, "rm -rf ./build"))

    def test_waiting_without_prompt(self):
        self.connect()
        self.model.handle_line(
            line({"evt": "turn", "role": "assistant", "content": [
                {"type": "text", "text": "running it"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "make   release"}},
            ]}),
            50,
        )
        self.model.handle_line(heartbeat(waiting=1, total=1, msg="(called Bash)"), 100)
        scr = self.model.screen(100)
        self.assertEqual(scr[bm.S_KIND], bm.KIND_WAITING)
        self.assertTrue(scr[bm.S_EMPHASIS])
        self.assertFalse(scr[bm.S_ACTIONABLE])
        self.assertEqual(scr[bm.S_LINES], ((bm.WRAP, "Bash: make release"),))
        self.assertEqual(scr[bm.S_TITLE], "(called Bash)")  # Desktop's msg

    def test_waiting_hides_tool_that_msg_does_not_name(self):
        # The Write turn event was over 4 KB and dropped by Desktop, so
        # the last tool seen (Bash) isn't the one waiting.
        self.connect()
        self.model.handle_line(
            line({"evt": "turn", "role": "assistant", "content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            ]}),
            50,
        )
        self.model.handle_line(heartbeat(waiting=1, total=1, msg="approve: Write"), 100)
        scr = self.model.screen(100)
        self.assertEqual(scr[bm.S_TITLE], "approve: Write")
        self.assertEqual(scr[bm.S_LINES], ())

    def test_waiting_title_falls_back_without_msg(self):
        self.connect()
        self.model.handle_line(line({"total": 2, "running": 2, "waiting": 2}), 100)
        scr = self.model.screen(100)
        self.assertEqual(scr[bm.S_TITLE], "Approval needed")
        self.assertEqual(scr[bm.S_LINES], ((bm.SINGLE, "2 sessions waiting"),))

    def test_stale_after_heartbeat_timeout(self):
        self.connect(0)
        self.model.handle_line(heartbeat(), 1000)
        self.assertEqual(self.model.screen(1000 + bm.HEARTBEAT_TIMEOUT_MS)[bm.S_STATUS], "Connected")
        self.assertEqual(self.model.screen(1001 + bm.HEARTBEAT_TIMEOUT_MS)[bm.S_STATUS], "No data")

    def test_disconnect_clears_prompt(self):
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 100)
        self.model.on_disconnect()
        scr = self.model.screen(200)
        self.assertEqual(scr[bm.S_KIND], bm.KIND_PAIR)
        self.assertEqual(scr[bm.S_TITLE], "Disconnected")
        self.assertIsNone(self.answer(True, 200))

    def test_header_always_shows_ble_identifier(self):
        # The header must match what Claude Desktop's picker lists, even
        # after Desktop renames the buddy; the new name goes in the ack.
        replies = self.model.handle_line(line({"cmd": "name", "name": "Clawd"}), 0)
        self.assertEqual(replies, [{"ack": "name", "ok": True, "n": 0}])
        self.assertEqual(self.store.data["name"], "Clawd")
        for connected in (False, True):
            if connected:
                self.connect()
            self.assertEqual(self.model.screen(0)[bm.S_NAME], "Claude_ABC123")
        (ack,) = self.model.handle_line(line({"cmd": "status"}), 0)
        self.assertEqual(ack["data"]["name"], "Clawd")

    # -- decisions ------------------------------------------------------

    def test_accept_sends_once_and_records(self):
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 100)
        msg = self.answer(True, 200)
        self.assertEqual(msg, {"cmd": "permission", "id": "req_1", "decision": "once"})
        self.model.record_decision(msg)
        self.assertEqual(self.store.data["appr"], 1)
        scr = self.model.screen(150)
        self.assertEqual(scr[bm.S_KIND], bm.KIND_ANSWERED)
        self.assertEqual(scr[bm.S_TITLE], "Allowed Bash")
        self.assertFalse(scr[bm.S_ACTIONABLE])
        # No double answer while the same prompt is still listed.
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 200)
        self.assertIsNone(self.answer(True, 200))

    def test_deny(self):
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 100)
        msg = self.answer(False, 200)
        self.assertEqual(msg["decision"], "deny")
        self.model.record_decision(msg)
        self.assertEqual(self.store.data["deny"], 1)
        self.assertEqual(self.model.screen(150)[bm.S_TITLE], "Denied Bash")

    def test_prompt_cleared_by_next_heartbeat(self):
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 100)
        self.model.record_decision(self.answer(True, 200))
        self.model.handle_line(heartbeat(waiting=0), 300)
        self.assertEqual(self.model.screen(300)[bm.S_KIND], bm.KIND_STATUS)

    def test_new_prompt_after_answer_is_answerable(self):
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 100)
        self.model.record_decision(self.answer(True, 200))
        self.model.handle_line(heartbeat(waiting=1, prompt=dict(PROMPT, id="req_2")), 200)
        self.assertEqual(self.answer(False, 200)["id"], "req_2")

    # -- prompt ids: echoed exactly, or not answered on the badge --------

    def test_spec_example_heartbeat_id_echoed_exactly(self):
        # The heartbeat and decisions exactly as in REFERENCE.md.
        spec_heartbeat = (
            '{"total": 3, "running": 1, "waiting": 1, "msg": "approve: Bash",'
            ' "entries": ["10:42 git push", "10:41 yarn test", "10:39 reading file..."],'
            ' "tokens": 184502, "tokens_today": 31200,'
            ' "prompt": {"id": "req_abc123", "tool": "Bash", "hint": "rm -rf /tmp/foo"}}'
        )
        self.connect()
        self.model.handle_line(spec_heartbeat, 100)
        self.assertTrue(self.model.screen(100)[bm.S_ACTIONABLE])
        self.assertEqual(
            json.dumps(self.answer(True, 100), separators=(",", ":")),
            '{"cmd":"permission","id":"req_abc123","decision":"once"}',
        )
        self.assertEqual(
            json.dumps(self.answer(False, 100), separators=(",", ":")),
            '{"cmd":"permission","id":"req_abc123","decision":"deny"}',
        )

    def test_longest_allowed_id_echoed_exactly(self):
        pid = "r" * bm.MAX_PROMPT_ID
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, prompt=dict(PROMPT, id=pid)), 100)
        self.assertEqual(self.answer(True, 100)["id"], pid)

    def assert_answer_in_app(self, bad_id):
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, prompt=dict(PROMPT, id=bad_id)), 100)
        scr = self.model.screen(100)
        # The prompt is still shown, with the header "Connected" (not
        # "No data"), but A/B are hidden and do nothing.
        self.assertEqual(scr[bm.S_KIND], bm.KIND_PROMPT)
        self.assertEqual(scr[bm.S_TITLE], "Allow Bash?")
        self.assertEqual(scr[bm.S_STATUS], "Connected")
        self.assertFalse(scr[bm.S_ACTIONABLE])
        self.assertIsNone(self.answer(True, 100))
        self.assertIsNone(self.model.permission_message(False, 100, scr[bm.S_DOC]))

    def test_too_long_id_is_answered_in_the_app(self):
        # Cutting it would send back an id Desktop doesn't recognise.
        self.assert_answer_in_app("r" * (bm.MAX_PROMPT_ID + 1))

    def test_number_id_is_answered_in_the_app(self):
        # Sending back "12345" for 12345 wouldn't match exactly.
        self.assert_answer_in_app(12345)

    def test_object_id_is_answered_in_the_app(self):
        self.assert_answer_in_app({"n": 1})

    def test_good_id_after_bad_one_is_answerable(self):
        self.assert_answer_in_app(12345)
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 200)
        self.assertTrue(self.model.screen(200)[bm.S_ACTIONABLE])
        self.assertEqual(self.answer(True, 200)["id"], "req_1")

    def test_stale_link_hides_accept_deny(self):
        self.connect(0)
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 1000)
        late = 1001 + bm.HEARTBEAT_TIMEOUT_MS
        scr = self.model.screen(late)
        self.assertEqual(scr[bm.S_STATUS], "No data")
        self.assertEqual(scr[bm.S_KIND], bm.KIND_PROMPT)  # still shown
        self.assertFalse(scr[bm.S_ACTIONABLE])
        self.assertIsNone(self.answer(True, late))
        # A fresh heartbeat makes it answerable again.
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), late)
        self.assertTrue(self.model.screen(late)[bm.S_ACTIONABLE])
        self.assertIsNotNone(self.answer(True, late))

    def test_nothing_to_answer(self):
        self.connect()
        self.model.handle_line(heartbeat(), 100)
        self.assertIsNone(self.answer(True, 200))

    def test_only_the_prompt_on_screen_is_answered(self):
        # Prompt req_1 is on the panel; req_2 arrives before it's drawn.
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 100)
        shown = self.model.prompt_doc()
        self.model.handle_line(heartbeat(waiting=1, prompt=dict(PROMPT, id="req_2")), 200)
        self.assertIsNone(self.model.permission_message(True, 300, shown))
        self.assertIsNone(self.model.permission_message(True, 300, None))  # nothing shown
        self.assertEqual(self.model.permission_message(True, 300, "p:req_2")["id"], "req_2")

    def test_reconnect_forgets_old_waiting(self):
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, total=1, msg="approve: Bash"), 100)
        self.model.on_disconnect()
        self.connect(200)
        scr = self.model.screen(300)
        self.assertEqual(scr[bm.S_KIND], bm.KIND_CONNECTED)  # not "approve: Bash"
        self.assertEqual((self.model.waiting, self.model.msg), (0, ""))

    def test_no_sessions_delay_can_be_zero(self):
        # The Tufty on USB power shows "No sessions" straight away.
        self.model.no_sessions_delay_ms = 0
        self.connect()
        self.model.handle_line(heartbeat(total=1), 100)
        self.model.handle_line(heartbeat(total=0, running=0), 1000)
        self.assertEqual(self.model.screen(1000)[bm.S_KIND], bm.KIND_NO_SESSIONS)

    def test_exact_tokens_label(self):
        self.connect()
        self.model.handle_line(heartbeat(tokens_today=31204), 100)
        self.assertEqual(self.model.tokens_label(), "31k today")
        self.model.exact_tokens = True
        self.assertEqual(self.model.tokens_label(), "31,204 today")

    def test_exact_tokens_grouping(self):
        for n, text in ((0, "0"), (999, "999"), (1000, "1,000"), (31204, "31,204"),
                        (1234567, "1,234,567")):
            self.assertEqual(bm.exact_tokens(n), text)

    def test_no_sessions_screen_after_delay(self):
        self.connect()
        self.model.handle_line(heartbeat(total=1), 100)
        self.model.handle_line(heartbeat(total=0, running=0), 1000)
        delay = bm.NO_SESSIONS_DELAY_MS
        self.assertEqual(self.model.screen(1000 + delay - 1)[bm.S_KIND], bm.KIND_STATUS)
        scr = self.model.screen(1000 + delay)
        self.assertEqual(scr[bm.S_KIND], bm.KIND_NO_SESSIONS)
        self.assertEqual(scr[bm.S_TITLE], "No sessions")
        self.assertEqual(scr[bm.S_LINES], ((bm.WRAP, bm.NO_SESSIONS_HINT), (bm.COUNTS, "")))
        self.assertFalse(scr[bm.S_EMPHASIS])
        # More heartbeats with total 0 don't restart the delay.
        self.model.handle_line(heartbeat(total=0, running=0), 1000 + delay + 50)
        self.assertEqual(self.model.screen(1000 + delay + 60)[bm.S_KIND], bm.KIND_NO_SESSIONS)
        # A session opens: straight back to status.
        self.model.handle_line(heartbeat(total=1), 1000 + delay + 100)
        self.assertEqual(self.model.screen(1000 + delay + 100)[bm.S_KIND], bm.KIND_STATUS)

    def test_brief_zero_total_keeps_status(self):
        # 0 -> 1 -> 0: the delay restarts from the second zero, so the
        # screen stays on status until a full delay after it.
        delay = bm.NO_SESSIONS_DELAY_MS
        self.connect()
        self.model.handle_line(heartbeat(total=0, running=0), 100)
        self.model.handle_line(heartbeat(total=1), 200)
        self.model.handle_line(heartbeat(total=0, running=0), 300)
        self.assertEqual(self.model.screen(300 + delay - 1)[bm.S_KIND], bm.KIND_STATUS)
        self.assertEqual(self.model.screen(300 + delay)[bm.S_KIND], bm.KIND_NO_SESSIONS)

    def test_no_sessions_keeps_last_reply(self):
        self.connect()
        self.model.handle_line(
            line({"evt": "turn", "role": "assistant", "content": [{"type": "text", "text": "Done."}]}),
            50,
        )
        self.model.handle_line(heartbeat(total=0, running=0), 100)
        scr = self.model.screen(100 + bm.NO_SESSIONS_DELAY_MS)
        self.assertIn((bm.WRAP, "Claude: Done."), scr[bm.S_LINES])

    def test_waiting_beats_no_sessions_and_reconnect_resets(self):
        self.connect()
        self.model.handle_line(heartbeat(total=0, running=0, waiting=1), 100)
        later = 100 + 2 * bm.NO_SESSIONS_DELAY_MS
        self.assertEqual(self.model.screen(later)[bm.S_KIND], bm.KIND_WAITING)
        self.model.handle_line(heartbeat(total=0, running=0), later)
        self.model.on_disconnect()
        self.connect(later)
        # The old link's zero doesn't count: a fresh delay starts from
        # the first zero on the new link.
        self.model.handle_line(heartbeat(total=0, running=0), later + 10)
        delay = bm.NO_SESSIONS_DELAY_MS
        self.assertEqual(self.model.screen(later + 10 + delay - 1)[bm.S_KIND], bm.KIND_STATUS)
        self.assertEqual(self.model.screen(later + 10 + delay)[bm.S_KIND], bm.KIND_NO_SESSIONS)

    def test_dead_link_after_timeout(self):
        self.connect(0)
        self.assertFalse(self.model.is_dead(bm.DEAD_LINK_MS))
        self.assertTrue(self.model.is_dead(bm.DEAD_LINK_MS + 1))
        self.model.handle_line(heartbeat(), bm.DEAD_LINK_MS + 1)  # any heartbeat revives
        self.assertFalse(self.model.is_dead(bm.DEAD_LINK_MS + 2))
        self.model.on_disconnect()
        self.assertFalse(self.model.is_dead(10 * bm.DEAD_LINK_MS))

    def test_silence_past_tick_wrap_is_stale_not_live(self):
        # MicroPython ticks_diff goes negative after 2^29 ms; that must
        # read as "a long time", not "Connected" again.
        self.connect(0)
        self.model.last_heartbeat_ms = 1000  # "later" than now after a wrap
        self.assertTrue(self.model.is_stale(0))
        self.assertTrue(self.model.is_dead(0))

    def test_unknown_one_shot_does_not_clear_prompt(self):
        self.connect()
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 100)
        for msg in ({"foo": 1}, {"time": [1775731234, -25200]}, {"time": [1, 2], "x": 3}):
            self.model.handle_line(line(msg), 150)
            self.assertIsNotNone(self.model.prompt, msg)
        self.assertEqual(self.answer(True, 200)["id"], "req_1")

    # -- commands -------------------------------------------------------

    def test_status_ack_shape(self):
        (ack,) = self.model.handle_line(line({"cmd": "status"}), 0)
        self.assertEqual(ack["ack"], "status")
        self.assertTrue(ack["ok"])
        data = ack["data"]
        self.assertEqual(data["name"], "Claude_ABC123")
        self.assertIs(data["sec"], False)
        self.assertEqual(data["bat"], {"pct": 80})
        self.assertEqual(data["sys"], {"up": 5, "heap": 1000})
        self.assertEqual(set(data["stats"]), {"appr", "deny", "vel", "nap", "lvl"})

    def test_status_provider_failure_still_acks(self):
        def boom():
            raise RuntimeError("adc")

        model = bm.BuddyModel("Claude_X", status_provider=boom)
        (ack,) = model.handle_line(line({"cmd": "status"}), 0)
        self.assertTrue(ack["ok"])
        self.assertNotIn("bat", ack["data"])

    def test_owner_accepts_name_or_owner_key(self):
        self.model.handle_line(line({"cmd": "owner", "name": "Felix"}), 0)
        self.assertEqual(self.store.data["owner"], "Felix")
        self.model.handle_line(line({"cmd": "owner", "owner": "Joe"}), 0)
        self.assertEqual(self.store.data["owner"], "Joe")

    def test_name_and_owner_without_value_refused(self):
        self.model.handle_line(line({"cmd": "name", "name": "Clawd"}), 0)
        self.model.handle_line(line({"cmd": "owner", "name": "Felix"}), 0)
        for cmd in ("name", "owner"):
            (ack,) = self.model.handle_line(line({"cmd": cmd}), 0)
            self.assertFalse(ack["ok"], cmd)
        self.assertEqual(self.store.data["name"], "Clawd")
        self.assertEqual(self.store.data["owner"], "Felix")

    def test_unchanged_owner_not_saved_again(self):
        self.model.handle_line(line({"cmd": "owner", "name": "Felix"}), 0)
        saves = self.store.saves
        (ack,) = self.model.handle_line(line({"cmd": "owner", "name": "Felix"}), 0)
        self.assertTrue(ack["ok"])
        self.assertEqual(self.store.saves, saves)  # every connect sends it

    def test_character_push_refused(self):
        (ack,) = self.model.handle_line(line({"cmd": "char_begin", "name": "bufo", "total": 10}), 0)
        self.assertEqual(ack["ack"], "char_begin")
        self.assertFalse(ack["ok"])
        # Known but unsupported, not "unknown command".
        self.assertEqual(ack["error"], "not supported")

    def test_unpair_acks(self):
        self.assertEqual(
            self.model.handle_line(line({"cmd": "unpair"}), 0),
            [{"ack": "unpair", "ok": True, "n": 0}],
        )

    def test_garbage_and_time_lines_ignored(self):
        self.connect()
        self.assertEqual(self.model.handle_line(b"not json\n", 0), [])
        self.assertEqual(self.model.handle_line(b"\xff\xfe\n", 0), [])
        self.assertEqual(self.model.handle_line(b"[1,2]\n", 0), [])
        self.assertEqual(self.model.handle_line(line({"time": [1775731234, -25200]}), 0), [])
        self.assertFalse(self.model.heartbeat_seen)

    def test_settings_persist_across_instances(self):
        self.model.handle_line(line({"cmd": "name", "name": "Clawd"}), 0)
        again = bm.BuddyModel("Claude_ABC123", store=self.store)
        self.assertEqual(again.display_name(), "Clawd")

    def test_long_fields_are_capped(self):
        self.connect()
        self.model.handle_line(
            heartbeat(msg="m" * 1000, entries=["e" * 1000] * 50, waiting=1,
                      prompt=dict(PROMPT, hint="h" * 5000)),
            0,
        )
        self.assertLessEqual(len(self.model.msg), bm.MAX_MSG)
        self.assertLessEqual(len(self.model.entries), bm.MAX_ENTRIES)
        self.assertLessEqual(len(self.model.prompt[2]), bm.MAX_HINT)


class ReplyTest(unittest.TestCase):
    def setUp(self):
        self.model = bm.BuddyModel("Claude_X")
        self.model.on_connect(0)
        self.model.handle_line(heartbeat(), 0)

    def turn(self, *blocks, role="assistant"):
        self.model.handle_line(line({"evt": "turn", "role": role, "content": list(blocks)}), 0)

    def test_reply_shown_after_counts(self):
        self.turn({"type": "text", "text": "Done.\n\nAll tests pass."})
        scr = self.model.screen(0)
        lines = scr[bm.S_LINES]
        self.assertEqual(lines[0][0], bm.COUNTS)
        self.assertEqual(lines[1], (bm.WRAP, "Claude: Done."))
        self.assertEqual(lines[2], (bm.WRAP, "All tests pass."))

    def test_markdown_stripped(self):
        paras = bm.reply_paragraphs("# Title\n**bold** and `code`\n```python\nx = 1\n```\n- item")
        self.assertEqual(paras, ("Title", "bold and code", "x = 1", "- item"))

    def test_tool_only_turn_keeps_previous_reply(self):
        self.turn({"type": "text", "text": "first"})
        seq = self.model.reply_seq
        self.turn({"type": "tool_use", "name": "Bash", "input": {"command": "ls"}})
        self.assertEqual(self.model.reply, ("first",))
        self.assertEqual(self.model.reply_seq, seq)
        self.assertEqual(self.model.last_tool, ("Bash", "ls"))

    def test_user_turn_ignored(self):
        self.turn({"type": "text", "text": "a question"}, role="user")
        self.assertEqual(self.model.reply, ())

    def test_reply_capped(self):
        self.turn({"type": "text", "text": "x" * 10000})
        self.assertLessEqual(sum(len(p) for p in self.model.reply), bm.MAX_REPLY)
        self.turn({"type": "text", "text": "\n".join("p{}".format(i) for i in range(500))})
        self.assertEqual(len(self.model.reply), bm.MAX_PARAGRAPHS)

    def test_doc_changes_with_new_reply_not_status(self):
        self.turn({"type": "text", "text": "one"})
        doc = self.model.screen(0)[bm.S_DOC]
        self.model.handle_line(heartbeat(msg="other", entries=["x"]), 10)
        self.assertEqual(self.model.screen(10)[bm.S_DOC], doc)
        self.turn({"type": "text", "text": "two"})
        self.assertNotEqual(self.model.screen(20)[bm.S_DOC], doc)

    def test_prompt_doc_is_prompt_id_and_keeps_line_breaks(self):
        hint = "cat <<EOF > f.txt\nhello\nEOF"
        self.model.handle_line(heartbeat(waiting=1, prompt=dict(PROMPT, hint=hint)), 0)
        scr = self.model.screen(0)
        self.assertEqual(scr[bm.S_DOC], "p:req_1")
        self.assertEqual(scr[bm.S_LINES], (
            (bm.WRAP, "cat <<EOF > f.txt"), (bm.WRAP, "hello"), (bm.WRAP, "EOF")))

    def test_long_hint_kept_up_to_cap(self):
        self.model.handle_line(heartbeat(waiting=1, prompt=dict(PROMPT, hint="y" * 1500)), 0)
        self.assertEqual(len(self.model.prompt[2]), 1500)


class PassengerTest(unittest.TestCase):
    """Battery and token labels: shown, but don't trigger repaints."""

    def setUp(self):
        self.model = bm.BuddyModel("Claude_ABC123")
        self.model.on_connect(0)
        self.model.handle_line(heartbeat(tokens_today=31200), 0)

    def test_format_tokens(self):
        cases = {0: "0", 999: "999", 1000: "1k", 1234: "1.2k", 9990: "10k",
                 31200: "31k", 999999: "999k", 1000000: "1M", 1250000: "1.2M", 12000000: "12M"}
        for n, text in cases.items():
            self.assertEqual(bm.format_tokens(n), text, n)

    def test_tokens_on_status_counts_line(self):
        scr = self.model.screen(0)
        self.assertEqual(scr[bm.S_TOKENS], "31k today")
        self.assertEqual(scr[bm.S_LINES][0][0], bm.COUNTS)

    def test_no_tokens_label_until_received(self):
        model = bm.BuddyModel("Claude_X")
        model.on_connect(0)
        model.handle_line(line({"total": 1, "running": 0, "waiting": 0}), 0)
        self.assertEqual(model.screen(0)[bm.S_TOKENS], "")

    def test_token_change_does_not_change_key(self):
        old = self.model.screen(0)
        self.model.handle_line(heartbeat(tokens_today=45000), 10)
        new = self.model.screen(10)
        self.assertNotEqual(new[bm.S_TOKENS], old[bm.S_TOKENS])
        self.assertEqual(bm.screen_key(new), bm.screen_key(old))

    def test_battery_labels(self):
        cases = [(100, "100%"), (87, "75%"), (88, "100%"), (60, "50%"), (30, "25%")]
        for pct, text in cases:
            self.model.set_battery(pct, usb=False)
            self.assertEqual(self.model.screen(0)[bm.S_BATTERY], text, pct)
        self.model.set_battery(40, usb=True)
        self.assertEqual(self.model.screen(0)[bm.S_BATTERY], "USB")
        self.model.set_battery(None, usb=False)
        self.assertEqual(self.model.screen(0)[bm.S_BATTERY], "")

    def test_usb_labels_charging_full_usb(self):
        label = lambda: self.model.screen(0)[bm.S_BATTERY]  # noqa: E731
        self.model.set_battery(60, usb=True, charging=True)
        self.assertEqual(label(), "Charging")
        self.model.set_battery(bm.BATTERY_FULL_PCT, usb=True, charging=False)
        self.assertEqual(label(), "Full")
        # Not charging but not near full: charging paused, or no battery.
        self.model.set_battery(bm.BATTERY_FULL_PCT - 1, usb=True, charging=False)
        self.assertEqual(label(), "USB")
        self.model.set_battery(None, usb=True, charging=False)
        self.assertEqual(label(), "USB")
        # Charging is never reported off USB, and unplugging clears it.
        self.model.set_battery(60, usb=False, charging=True)
        self.assertEqual(label(), "50%")
        self.model.set_battery(60, usb=True, charging=True)
        self.model.set_usb(False)
        self.assertFalse(self.model.charging)

    def test_charging_to_full_does_not_change_key(self):
        self.model.set_battery(90, usb=True, charging=True)
        old = self.model.screen(0)
        self.model.set_battery(100, usb=True, charging=False)
        new = self.model.screen(0)
        self.assertEqual(new[bm.S_BATTERY], "Full")
        self.assertEqual(bm.screen_key(old), bm.screen_key(new))

    def test_battery_change_does_not_change_key(self):
        self.model.set_battery(90, usb=False)
        old = self.model.screen(0)
        self.model.set_battery(60, usb=False)
        self.assertEqual(bm.screen_key(self.model.screen(0)), bm.screen_key(old))

    def test_usb_plug_and_unplug_are_urgent(self):
        self.model.set_battery(60, usb=False)
        unplugged = self.model.screen(0)
        self.assertTrue(self.model.set_usb(True))
        plugged = self.model.screen(0)
        self.assertEqual(plugged[bm.S_BATTERY], "USB")
        self.assertNotEqual(bm.screen_key(plugged), bm.screen_key(unplugged))
        self.assertTrue(bm.is_urgent(plugged, unplugged))
        self.assertFalse(self.model.set_usb(True))  # no change, no fresh reading
        self.assertTrue(self.model.set_usb(False))
        self.assertTrue(bm.is_urgent(self.model.screen(0), plugged))

    def test_plugging_in_clears_low_battery(self):
        self.model.set_battery(10, usb=False)
        self.assertTrue(self.model.battery_low)
        self.model.set_usb(True)
        self.assertFalse(self.model.battery_low)

    def test_low_battery_changes_key_with_hysteresis(self):
        self.model.set_battery(30, usb=False)
        normal = bm.screen_key(self.model.screen(0))
        self.model.set_battery(19, usb=False)
        low = self.model.screen(0)
        self.assertNotEqual(bm.screen_key(low), normal)
        self.assertTrue(low[bm.S_BATTERY_LOW])
        self.assertEqual(low[bm.S_BATTERY], "20%")  # 5% steps when low
        # Hovering just above the threshold stays low (no flip-flop).
        for pct in (21, 19, 23, 20):
            self.model.set_battery(pct, usb=False)
            self.assertTrue(self.model.battery_low, pct)
        self.model.set_battery(2, usb=False)
        self.assertEqual(self.model.screen(0)[bm.S_BATTERY], "5%")
        self.model.set_battery(25, usb=False)
        self.assertFalse(self.model.battery_low)
        self.model.set_battery(5, usb=True)  # plugged in: never "low"
        self.assertFalse(self.model.battery_low)


class UrgencyTest(unittest.TestCase):
    def setUp(self):
        self.model = bm.BuddyModel("Claude_ABC123")
        self.model.on_connect(0)
        self.model.handle_line(heartbeat(msg="a"), 0)

    def test_first_paint_is_urgent(self):
        self.assertTrue(bm.is_urgent(self.model.screen(0), None))

    def test_status_text_change_is_throttled(self):
        old = self.model.screen(0)
        self.model.handle_line(heartbeat(msg="b"), 10)
        self.assertFalse(bm.is_urgent(self.model.screen(10), old))

    def test_prompt_is_urgent(self):
        old = self.model.screen(0)
        self.model.handle_line(heartbeat(waiting=1, prompt=PROMPT), 10)
        self.assertTrue(bm.is_urgent(self.model.screen(10), old))

    def test_connection_change_is_urgent(self):
        old = self.model.screen(0)
        self.assertTrue(bm.is_urgent(self.model.screen(bm.HEARTBEAT_TIMEOUT_MS + 1), old))

    def test_identical_heartbeat_gives_identical_screen(self):
        old = self.model.screen(0)
        self.model.handle_line(heartbeat(msg="a"), 5000)
        self.assertEqual(self.model.screen(5000), old)

    def test_no_screen_has_no_key(self):
        # Before the first paint the painter compares against None.
        self.assertIsNone(bm.screen_key(None))


if __name__ == "__main__":
    unittest.main()
