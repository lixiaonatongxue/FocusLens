"""报表聚合测试：临时库 + 合成事件。"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from agent.classifier import Classifier
from agent.report import (
    clipped,
    day_bounds,
    focus_sessions,
    render_day,
    render_week,
    summarize_day,
    top_apps,
)
from agent.store import Event, Store

RULES = [
    {"match": {"exe": ["Code.exe"]}, "category": "dev", "name": "VS Code"},
    {"match": {"exe": ["WeChat.exe"]}, "category": "im", "name": "微信"},
]


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")
        self.classifier = Classifier(RULES, [])

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_clip_crossing_midnight(self):
        day = date(2026, 10, 24)
        s0, _ = day_bounds(day)
        ev = [Event(s0 + 82800, s0 + 93600, "Code.exe", "", "dev")]  # 23:00 → 次日 02:00
        day1 = list(clipped(ev, s0, s0 + 86400))
        day2 = list(clipped(ev, s0 + 86400, s0 + 172800))
        self.assertEqual(day1[0].duration, 3600)
        self.assertEqual(day2[0].duration, 7200)

    def test_focus_sessions_merge_gap(self):
        events = [
            Event(0, 1800, "Code.exe", "", "dev"),
            Event(2100, 2700, "Code.exe", "", "dev"),  # 间隔 300s：合并
        ]
        sessions = focus_sessions(events, {"dev"}, merge_gap=300, min_len=60)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0][2], 2400)

        events[1] = Event(2101, 2701, "Code.exe", "", "dev")  # 间隔 301s：切段
        sessions = focus_sessions(events, {"dev"}, merge_gap=300, min_len=60)
        self.assertEqual(len(sessions), 2)

    def test_focus_sessions_min_length_filter(self):
        events = [Event(0, 600, "Code.exe", "", "dev")]
        self.assertEqual(focus_sessions(events, {"dev"}, min_len=900), [])
        self.assertEqual(focus_sessions(events, {"dev"}, min_len=60), [(0, 600, 600)])

    def test_focus_sessions_ignore_idle(self):
        events = [
            Event(0, 1800, "", "", "idle"),
            Event(1800, 2000, "Code.exe", "", "dev"),
        ]
        sessions = focus_sessions(events, {"dev"}, merge_gap=300, min_len=60)
        self.assertEqual(len(sessions), 1)

    def test_summarize_day(self):
        day = date(2026, 10, 24)
        s0, _ = day_bounds(day)
        self.store.add_event(s0 + 3600, s0 + 4800, "Code.exe", "", "dev")
        self.store.add_event(s0 + 4800, s0 + 5100, "WeChat.exe", "", "im")
        self.store.add_event(s0 + 5600, s0 + 6200, "", "", "idle")
        s = summarize_day(self.store, self.classifier, day)
        self.assertEqual(s["active_seconds"], 1500)
        self.assertEqual(s["idle_seconds"], 600)
        self.assertEqual(s["top_apps"][0]["name"], "VS Code")
        self.assertEqual(s["focus"]["total_seconds"], 1200)
        text = render_day(self.store, self.classifier, day)
        self.assertIn("VS Code", text)
        self.assertIn("类别占比", text)

    def test_render_week_empty(self):
        text = render_week(self.store, self.classifier)
        self.assertIn("近 7 天", text)


if __name__ == "__main__":
    unittest.main()
