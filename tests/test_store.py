"""SQLite 存储测试：使用临时目录里的合成数据。"""

import tempfile
import unittest
from pathlib import Path

from agent.store import Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_add_and_query(self):
        self.store.add_event(1000, 1010, "A.exe", "t", "dev")
        self.store.add_event(1010, 1020, "B.exe", "", "im")
        evs = self.store.events_between(0, 2000)
        self.assertEqual(len(evs), 2)
        self.assertEqual(evs[0].exe, "A.exe")
        self.assertEqual(evs[0].duration, 10)
        self.assertEqual(evs[1].category, "im")

    def test_range_half_open(self):
        self.store.add_event(100, 200, "A.exe", "", "dev")
        self.assertEqual(self.store.events_between(200, 300), [])
        self.assertEqual(len(self.store.events_between(199, 300)), 1)

    def test_zero_or_negative_duration_dropped(self):
        self.store.add_event(1000, 1000, "A.exe", "", "dev")
        self.store.add_event(1001, 1000, "A.exe", "", "dev")
        self.assertEqual(self.store.events_between(0, 9999), [])

    def test_delete_all(self):
        self.store.add_event(1, 2, "A.exe", "", "dev")
        self.store.delete_all()
        self.assertEqual(self.store.events_between(0, 9999), [])


if __name__ == "__main__":
    unittest.main()
