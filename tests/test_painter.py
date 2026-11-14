"""Host-side tests for the repaint policy and paging (buddy_painter)."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "claude_buddy"))

import buddy_model as bm  # noqa: E402
from buddy_painter import Painter  # noqa: E402

SETTLE = 300
INTERVAL = 15000


class FakeView:
    def __init__(self, pages=1):
        self.pages = pages
        self.draws = []

    def page_count(self, scr):
        return self.pages

    def draw(self, scr, page):
        self.draws.append((scr, page))


def line(obj):
    return (json.dumps(obj) + "\n").encode()


class PainterTest(unittest.TestCase):
    def setUp(self):
        self.view = FakeView()
        self.busy = False
        self.presented = 0
        self.painter = Painter(self.view, present=self.present, busy=lambda: self.busy,
                               settle_ms=SETTLE, status_interval_ms=INTERVAL)
        self.model = bm.BuddyModel("Claude_X")
        self.model.on_connect(0)
        self.model.handle_line(line({"total": 1, "running": 1, "waiting": 0, "msg": "a"}), 0)

    def present(self):
        self.presented += 1

    def tick(self, now):
        return self.painter.tick(self.model.screen(now), now)

    def heartbeat(self, now, **fields):
        base = {"total": 1, "running": 1, "waiting": 0, "msg": "a"}
        base.update(fields)
        self.model.handle_line(line(base), now)

    def test_first_paint_after_settle(self):
        self.assertFalse(self.tick(0))
        self.assertFalse(self.tick(SETTLE - 1))
        self.assertTrue(self.tick(SETTLE))
        self.assertEqual(self.presented, 1)

    def test_no_repaint_without_change(self):
        self.tick(0)
        self.tick(SETTLE)
        for t in range(SETTLE, 60000, 1000):
            self.heartbeat(t)
            self.assertFalse(self.tick(t))
        self.assertEqual(self.presented, 1)

    def test_status_change_is_throttled(self):
        self.tick(0)
        self.tick(SETTLE)
        self.heartbeat(1000, msg="b")
        self.assertFalse(self.tick(1000 + SETTLE))
        self.assertFalse(self.tick(SETTLE + INTERVAL - 1))
        self.assertTrue(self.tick(SETTLE + INTERVAL))

    def test_prompt_is_not_throttled(self):
        self.tick(0)
        self.tick(SETTLE)
        self.heartbeat(1000, waiting=1, prompt={"id": "r1", "tool": "Bash", "hint": "ls"})
        self.tick(1000)
        self.assertTrue(self.tick(1000 + SETTLE))

    def test_waits_while_display_busy(self):
        self.tick(0)
        self.busy = True
        self.assertFalse(self.tick(SETTLE))
        self.busy = False
        self.assertTrue(self.tick(SETTLE + 20))

    def test_hold_delays_paint(self):
        self.tick(0)
        self.tick(SETTLE)
        self.heartbeat(1000, waiting=1, prompt={"id": "r1", "tool": "Bash", "hint": "ls"})
        self.painter.hold(1000, 1000)
        self.assertFalse(self.tick(1500))
        self.tick(2000)
        self.assertTrue(self.tick(2000 + SETTLE))

    def test_usb_change_repaints_after_settle_not_throttle(self):
        self.tick(0)
        self.tick(SETTLE)
        self.model.set_usb(True)
        self.tick(1000)
        self.assertTrue(self.tick(1000 + SETTLE))
        self.assertEqual(self.presented, 2)

    def test_answerable_doc_only_once_prompt_is_on_panel(self):
        r1 = {"id": "r1", "tool": "Bash", "hint": "ls"}
        self.tick(0)
        self.tick(SETTLE)
        self.assertIsNone(self.painter.answerable_doc())  # status screen
        self.heartbeat(1000, waiting=1, prompt=r1)
        self.tick(1000)
        self.assertIsNone(self.painter.answerable_doc())  # not drawn yet
        self.tick(1000 + SETTLE)
        self.assertEqual(self.painter.answerable_doc(), "p:r1")
        self.busy = True
        self.assertIsNone(self.painter.answerable_doc())  # mid-refresh
        self.busy = False
        # A newer prompt arrives: the panel still shows r1, so A/B
        # can't answer r2 until it's drawn (BuddyModel refuses).
        self.heartbeat(2000, waiting=1, prompt=dict(r1, id="r2"))
        self.assertEqual(self.painter.answerable_doc(), "p:r1")
        self.assertIsNone(
            self.model.permission_message(True, 2000, self.painter.answerable_doc())
        )

    def test_no_throttle_after_ticks_wrap(self):
        self.tick(0)
        self.tick(SETTLE)
        # After ~6 days without a paint, ticks_diff(now, last) goes
        # negative on MicroPython; that must not defer the repaint.
        self.painter.last_paint_ms = 10**9
        self.heartbeat(1000, msg="b")
        self.tick(1000)
        self.assertTrue(self.tick(1000 + SETTLE))

    def test_battery_and_tokens_ride_along(self):
        self.tick(0)
        self.tick(SETTLE)
        self.model.set_battery(40, usb=False)
        self.heartbeat(1000, tokens_today=12345)
        # Past both the throttle and the settle delay: a real change would
        # have painted by now.
        for t in (1000, 1000 + INTERVAL, 1000 + INTERVAL + SETTLE, 1000 + 2 * INTERVAL):
            self.assertFalse(self.tick(t), t)
        self.assertEqual(self.presented, 1)


class PagingPolicyTest(unittest.TestCase):
    def setUp(self):
        self.view = FakeView(pages=3)
        self.painter = Painter(self.view, present=lambda: None, busy=lambda: False,
                               settle_ms=SETTLE, status_interval_ms=INTERVAL)
        self.model = bm.BuddyModel("Claude_X")
        self.model.on_connect(0)
        self.prompt("r1", 0)
        self.paint(0)

    def prompt(self, pid, now, hint="ls"):
        self.model.handle_line(line({"total": 1, "running": 1, "waiting": 1, "msg": "a",
                                     "prompt": {"id": pid, "tool": "Bash", "hint": hint}}), now)

    def paint(self, now):
        scr = self.model.screen(now)
        self.painter.tick(scr, now)
        return self.painter.tick(scr, now + SETTLE)

    def test_turn_pages_and_clamp(self):
        scr = self.model.screen(0)
        self.assertFalse(self.painter.turn(scr, -1))  # already first
        self.assertTrue(self.painter.turn(scr, 1))
        self.assertTrue(self.painter.turn(scr, 1))
        self.assertFalse(self.painter.turn(scr, 1))  # already last
        self.assertEqual(self.painter.page, 2)

    def test_page_turn_repaints_without_throttle(self):
        # A status screen (prompts are always urgent, so they'd repaint
        # anyway): a page turn must still skip the 15 s status throttle.
        self.model.handle_line(line({"total": 1, "running": 1, "waiting": 0, "msg": "a"}), 500)
        self.paint(500)  # status screen on the panel; throttle starts
        scr = self.model.screen(1000)
        self.assertEqual(scr[bm.S_KIND], bm.KIND_STATUS)
        self.painter.turn(scr, 1)
        self.painter.tick(scr, 1000)
        self.assertTrue(self.painter.tick(scr, 1000 + SETTLE))
        self.assertEqual(self.view.draws[-1][1], 1)

    def test_new_prompt_resets_to_first_page(self):
        self.painter.turn(self.model.screen(0), 2)
        self.prompt("r2", 1000)
        self.paint(1000)
        self.assertEqual(self.painter.page, 0)

    def test_status_update_keeps_page(self):
        self.model.handle_line(line({"evt": "turn", "role": "assistant",
                                     "content": [{"type": "text", "text": "long reply"}]}), 0)
        self.model.handle_line(line({"total": 1, "running": 1, "waiting": 0, "msg": "a"}), 0)
        self.paint(0)
        self.painter.turn(self.model.screen(0), 2)
        self.model.handle_line(line({"total": 1, "running": 0, "waiting": 0, "msg": "b",
                                     "entries": ["10:42 git push"]}), 5000)
        self.paint(5000)
        self.assertEqual(self.painter.page, 2)

    def test_page_clamped_when_content_shrinks(self):
        self.painter.turn(self.model.screen(0), 2)
        self.view.pages = 2
        self.paint(1000)
        self.assertEqual(self.painter.page, 1)


if __name__ == "__main__":
    unittest.main()
