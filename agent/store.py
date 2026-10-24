"""SQLite 事件存储：一段前台会话 = 一行 events。

线程安全（互斥锁 + WAL），采集线程写入与报表/接口读取可并发。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import List, NamedTuple

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  start_ts INTEGER NOT NULL,
  end_ts INTEGER NOT NULL,
  duration INTEGER NOT NULL,
  exe TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT 'other'
);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_ts);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
"""


class Event(NamedTuple):
    start_ts: int
    end_ts: int
    exe: str
    title: str
    category: str

    @property
    def duration(self) -> int:
        return self.end_ts - self.start_ts


class Store:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def add_event(self, start_ts: float, end_ts: float, exe: str, title: str, category: str) -> None:
        start, end = int(start_ts), int(end_ts)
        if end <= start:
            # 同一秒内的切换抖动，不值得入库
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO events(start_ts, end_ts, duration, exe, title, category) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (start, end, end - start, exe, title, category),
            )
            self._conn.commit()

    def events_between(self, start_ts: int, end_ts: int) -> List[Event]:
        """返回与 [start_ts, end_ts) 相交的事件，按开始时间排序。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT start_ts, end_ts, exe, title, category FROM events "
                "WHERE start_ts < ? AND end_ts > ? ORDER BY start_ts",
                (end_ts, start_ts),
            ).fetchall()
        return [Event(*row) for row in rows]

    def delete_all(self) -> int:
        """清空所有记录并 VACUUM 收回磁盘空间（隐私清除入口）。"""
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            self._conn.execute("DELETE FROM events")
            self._conn.commit()
            self._conn.execute("VACUUM")
        return n

    def close(self) -> None:
        with self._lock:
            self._conn.close()
