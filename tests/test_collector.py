"""采集状态机测试：假时钟/假输入/假前台窗口，不碰真实系统。"""

import unittest

from agent.classifier import Classifier
from agent.collector import Collector

RULES = [
    {"match": {"exe": ["Code.exe"]}, "category": "dev", "name": "VS Code"},
    {"match": {"exe": ["WeChat.exe"]}, "category": "im", "name": "微信"},
]


class FakeStore:
    def __init__(self):
        self.events = []

    def add_event(self, start_ts, end_ts, exe, title, category):
        if end_ts > start_ts:
            self.events.append(
                (int(start_ts), int(end_ts), exe, title, category)
            )


class Harness:
    def __init__(self, **kw):
        self.store = FakeStore()
        self.clock = 10000.0
        self.idle_ms = 0
        self.fg = ("Code.exe", "main.py - Code", 111)
        params = dict(
            idle_seconds=300,
            poll_interval=1.0,
            privacy="full",
            now_fn=lambda: self.clock,
            idle_ms_fn=lambda: self.idle_ms,
            foreground_fn=lambda: self.fg,
        )
        params.update(kw)
        self.collector = Collector(self.store, Classifier(RULES, []), **params)

    def tick(self, dt=1.0):
        self.clock += dt
        self.collector.sample()


class CollectorTest(unittest.TestCase):
    def test_app_switch_splits_segment(self):
        h = Harness()
        h.collector.sample()                      # 打开 Code
        h.fg = ("WeChat.exe", "微信", 222)
        h.tick(10)                                # 切到微信
        h.tick(15)
        h.collector.flush()
        self.assertEqual(
            h.store.events,
            [(10000, 10010, "Code.exe", "main.py - Code", "dev"),
             (10010, 10025, "WeChat.exe", "微信", "im")],
        )

    def test_title_change_splits_segment(self):
        h = Harness()
        h.collector.sample()
        h.fg = ("Code.exe", "other.py - Code", 111)   # 同进程换文件/换标签
        h.tick(8)
        h.tick(5)
        h.collector.flush()
        self.assertEqual(
            [(e[0], e[1]) for e in h.store.events], [(10000, 10008), (10008, 10013)]
        )

    def test_idle_transition_and_resume(self):
        h = Harness(checkpoint_seconds=0)
        h.collector.sample()                      # Code 从 10000 开始
        for _ in range(7):                        # 模拟常规采样节奏（每 50s 一次）
            h.clock += 50
            h.collector.sample()                  # 到 10350，窗口未变，无事发生
        h.clock, h.idle_ms = 10400, 301_000        # 5 分 01 秒无输入
        h.collector.sample()                       # 判定离开
        h.clock, h.idle_ms = 10460, 361_000
        h.collector.sample()                       # 仍然离开
        h.clock, h.idle_ms = 10500, 5_000           # 恢复输入
        h.collector.sample()
        h.tick(30)
        h.tick(30)
        h.tick(30)
        h.collector.flush()
        self.assertEqual(
            h.store.events,
            [(10000, 10399, "Code.exe", "main.py - Code", "dev"),   # 宽限 300s 记给应用
             (10399, 10495, "", "", "idle"),
             (10495, 10590, "Code.exe", "main.py - Code", "dev")],
        )

    def test_long_session_checkpoints_every_60s(self):
        h = Harness()
        h.collector.sample()                      # Code 从 10000 开始
        for _ in range(4):
            h.tick(20)                            # 10080，期间在 10060 触发一次落盘
        h.collector.flush()
        self.assertEqual(
            [(e[0], e[1]) for e in h.store.events],
            [(10000, 10060), (10060, 10080)],
        )

    def test_checkpoints_can_be_disabled(self):
        h = Harness(checkpoint_seconds=0)
        h.collector.sample()
        for _ in range(4):
            h.tick(20)
        h.collector.flush()
        self.assertEqual([(e[0], e[1]) for e in h.store.events], [(10000, 10080)])

    def test_no_foreground_window_marks_idle(self):
        h = Harness()
        h.collector.sample()
        h.fg = None
        h.tick(2)
        h.tick(30)
        h.collector.flush()
        self.assertEqual(
            [e[4] for e in h.store.events], ["dev", "idle"]
        )
        self.assertEqual(h.store.events[1][3], "")

    def test_privacy_levels(self):
        for level, want in (
            ("default", ""),
            ("hash", None),   # 16 位十六进制
            ("full", "main.py - Code"),
        ):
            h = Harness(privacy=level)
            h.collector.sample()
            h.fg = ("WeChat.exe", "微信", 222)
            h.tick(5)
            title = h.store.events[0][3]
            if want is None:
                self.assertEqual(len(title), 16)
                int(title, 16)  # 能当十六进制解析
            else:
                self.assertEqual(title, want)

    def test_sleep_gap_truncates_segment(self):
        h = Harness()
        h.collector.sample()                      # Code 从 10000 开始
        h.clock, h.idle_ms = 13600, 0              # 一小时没采样（睡眠）
        h.collector.sample()
        h.tick(10)
        h.collector.flush()
        self.assertEqual(
            [(e[0], e[1]) for e in h.store.events], [(10000, 10001), (13600, 13610)]
        )


if __name__ == "__main__":
    unittest.main()
